import datetime as dt
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb

from app.config import ConfigurationError, DatabaseSettings
from app.snapshots import (
    SnapshotRange,
    export_audit_range,
    export_range,
    sha256_file,
)

UTC = dt.timezone.utc
START = dt.datetime(2025, 1, 1, tzinfo=UTC)
END = dt.datetime(2025, 7, 1, tzinfo=UTC)
MICROSECOND = dt.timedelta(microseconds=1)


class SnapshotRangeTests(unittest.TestCase):
    def test_from_dates_uses_utc_midnight(self):
        snapshot_range = SnapshotRange.from_dates(dt.date(2025, 1, 1), dt.date(2025, 7, 1))
        self.assertEqual((snapshot_range.start, snapshot_range.end), (START, END))

    def test_rejects_empty_or_inverted_range(self):
        for start, end in ((START, START), (END, START)):
            with self.assertRaises(ValueError):
                SnapshotRange(start, end)

    def test_rejects_naive_datetimes(self):
        with self.assertRaises(ValueError):
            SnapshotRange(dt.datetime(2025, 1, 1), END)

    def test_period_in_progress_is_not_archivable(self):
        snapshot_range = SnapshotRange(START, END)
        snapshot_range.ensure_closed(END)
        with self.assertRaises(ValueError):
            snapshot_range.ensure_closed(END - MICROSECOND)


class ExportRangeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.destination = Path(self.directory.name) / "snapshot.parquet"
        self.connection = duckdb.connect()
        self.addCleanup(self.connection.close)
        self.connection.execute("SET TimeZone = 'UTC'")
        self.connection.execute(
            'CREATE TABLE audit (id INTEGER, "timestamp" TIMESTAMPTZ, changes VARCHAR)'
        )
        rows = [
            (1, START - MICROSECOND, '{"before": "start"}'),
            (4, END - MICROSECOND, '{"last": "inside"}'),
            (2, START, None),
            (3, START + dt.timedelta(days=30), '{"nested": {"a": [1, 2]}}'),
            (5, END, '{"after": "end"}'),
        ]
        self.connection.executemany("INSERT INTO audit VALUES (?, ?, ?)", rows)

    def test_includes_start_and_excludes_end(self):
        count = export_range(self.connection, "audit", SnapshotRange(START, END), self.destination)
        exported = self.connection.execute(
            f"SELECT id, changes FROM read_parquet('{self.destination}')"
        ).fetchall()
        self.assertEqual(count, 3)
        self.assertEqual(
            exported,
            [(2, None), (3, '{"nested": {"a": [1, 2]}}'), (4, '{"last": "inside"}')],
        )

    def test_refuses_to_overwrite_existing_file(self):
        self.destination.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            export_range(self.connection, "audit", SnapshotRange(START, END), self.destination)
        self.assertEqual(self.destination.read_bytes(), b"existing")

    def test_failed_copy_leaves_no_files(self):
        with self.assertRaises(duckdb.Error):
            export_range(self.connection, "missing_table", SnapshotRange(START, END), self.destination)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])


class ExportAuditRangeTests(unittest.TestCase):
    def test_period_in_progress_fails_before_connecting(self):
        database = DatabaseSettings("postgres", 5432, "db", "user", "secret")
        with mock.patch("app.snapshots.postgres_session") as session:
            with self.assertRaises(ValueError):
                export_audit_range(
                    database, SnapshotRange(START, END), Path("unused.parquet"), now=START
                )
        session.assert_not_called()

    def test_missing_database_settings_are_named_without_values(self):
        database = DatabaseSettings("", 5432, "db", "user", "")
        with self.assertRaises(ConfigurationError) as raised:
            database.ensure_complete()
        self.assertIn("DATABASE_HOST", str(raised.exception))
        self.assertIn("DATABASE_PASSWORD", str(raised.exception))


class Sha256FileTests(unittest.TestCase):
    def test_hashes_real_file_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.bin"
            content = b"audit" * 1000
            path.write_bytes(content)
            self.assertEqual(sha256_file(path), hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    unittest.main()
