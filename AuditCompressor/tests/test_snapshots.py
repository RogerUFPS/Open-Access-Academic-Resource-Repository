import datetime as dt
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb

from app.config import ConfigurationError, DatabaseSettings, Settings, StorageSettings
from app.duckdb_session import ENCRYPTION_CONFIG, register_parquet_key
from app.manifest import Manifest, SnapshotRange
from app.snapshots import (
    SnapshotConflictError,
    SnapshotIntegrityError,
    archive_audit_range,
    create_snapshot,
    export_range,
    sha256_file,
    source_with_inet_text,
)
from tests.support import ARCHIVE, END, START, TEST_KEY, FakeStorage, audit_connection

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
MANIFEST_KEY = "auditlog/20250101T000000Z_20250701T000000Z/manifest.json"
PART_KEY = "auditlog/20250101T000000Z_20250701T000000Z/part-0001.parquet"


class ExportRangeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.destination = Path(self.directory.name) / "snapshot.parquet"
        self.connection = audit_connection()
        self.addCleanup(self.connection.close)

    def export(self, source="audit"):
        return export_range(
            self.connection, source, ARCHIVE, SnapshotRange(START, END), self.destination
        )

    def test_includes_start_and_excludes_end(self):
        self.assertEqual(self.export(), 3)
        exported = self.connection.execute(
            f"SELECT id, changes FROM read_parquet('{self.destination}')"
        ).fetchall()
        self.assertEqual(
            exported,
            [(2, None), (3, '{"nested": {"a": [1, 2]}}'), (4, '{"last": "inside"}')],
        )

    def test_refuses_to_overwrite_existing_file(self):
        self.destination.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(self.destination.read_bytes(), b"existing")

    def test_failed_copy_leaves_no_files(self):
        with self.assertRaises(duckdb.Error):
            self.export(source="missing_table")
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])


class InetTextTests(unittest.TestCase):
    def test_matches_postgres_text_for_inet_values(self):
        connection = duckdb.connect()
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE ips (id INTEGER, ip VARCHAR)")
        connection.executemany(
            "INSERT INTO ips VALUES (?, ?)",
            [
                (1, "172.27.0.5/32"),
                (2, "10.0.0.0/24"),
                (3, "::1/128"),
                (4, "2001:db8::/32"),
                (5, None),
            ],
        )
        source = source_with_inet_text("ips", ["ip"])
        values = connection.execute(f"SELECT ip FROM {source} ORDER BY id").fetchall()
        self.assertEqual(
            [value for (value,) in values],
            ["172.27.0.5", "10.0.0.0/24", "::1", "2001:db8::/32", None],
        )

    def test_without_inet_columns_the_table_is_used_as_is(self):
        self.assertEqual(source_with_inet_text("pg.public.audit", []), "pg.public.audit")


class CreateSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.connection = audit_connection()
        self.addCleanup(self.connection.close)
        register_parquet_key(self.connection, TEST_KEY)
        self.storage = FakeStorage()

    def create(self, snapshot_range=None):
        return create_snapshot(
            self.connection,
            "audit",
            self.storage,
            ARCHIVE,
            snapshot_range or SnapshotRange(START, END),
            NOW,
        )

    def test_uploads_part_and_writes_verified_manifest(self):
        manifest = self.create()

        self.assertEqual(sorted(self.storage.objects), [MANIFEST_KEY, PART_KEY])
        stored = Manifest.from_dict(self.storage.get_json(MANIFEST_KEY))
        self.assertEqual(stored, manifest)
        self.assertEqual(manifest.row_count, 3)
        (part,) = manifest.files
        self.assertEqual(part.key, PART_KEY)
        self.assertEqual(part.sha256, hashlib.sha256(self.storage.objects[PART_KEY]).hexdigest())
        self.assertEqual(part.size, len(self.storage.objects[PART_KEY]))

    def test_stored_part_is_encrypted_and_needs_the_key(self):
        self.assertTrue(self.create().encrypted)
        content = self.storage.objects[PART_KEY]
        self.assertNotIn(b"nested", content)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.parquet"
            path.write_bytes(content)
            reader = duckdb.connect()
            self.addCleanup(reader.close)
            with self.assertRaises(duckdb.Error):
                reader.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()
            register_parquet_key(reader, TEST_KEY)
            count = reader.execute(
                f"SELECT count(*) FROM read_parquet('{path}', encryption_config = {ENCRYPTION_CONFIG})"
            ).fetchone()[0]
        self.assertEqual(count, 3)

    def test_corrupted_upload_does_not_produce_a_manifest(self):
        self.storage.corrupt = True
        with self.assertRaises(SnapshotIntegrityError):
            self.create()
        self.assertNotIn(MANIFEST_KEY, self.storage.objects)

    def test_failed_attempt_can_be_retried(self):
        self.storage.corrupt = True
        with self.assertRaises(SnapshotIntegrityError):
            self.create()
        self.storage.corrupt = False
        self.assertEqual(self.create().row_count, 3)

    def test_overlapping_range_is_rejected_without_uploading(self):
        self.create()
        before = dict(self.storage.objects)
        overlapping = SnapshotRange(START + dt.timedelta(days=30), END + dt.timedelta(days=30))
        with self.assertRaises(SnapshotConflictError):
            self.create(overlapping)
        self.assertEqual(self.storage.objects, before)

    def test_adjacent_range_is_a_new_snapshot(self):
        self.create()
        following = self.create(SnapshotRange(END, END + dt.timedelta(days=1)))
        self.assertEqual(following.row_count, 1)
        self.assertEqual(len(self.storage.objects), 4)

    def test_period_without_records_is_archived_empty(self):
        empty = SnapshotRange(END + dt.timedelta(days=1), END + dt.timedelta(days=2))
        self.assertEqual(self.create(empty).row_count, 0)


class ArchiveAuditRangeTests(unittest.TestCase):
    def test_period_in_progress_fails_before_connecting(self):
        settings = Settings(
            api_key="",
            database=DatabaseSettings("postgres", 5432, "db", "user", "secret"),
            storage=StorageSettings("http://rustfs:9000", "auditorias", "us-east-1", "a", "b"),
            archive=ARCHIVE,
        )
        with (
            mock.patch("app.snapshots.postgres_session") as session,
            mock.patch("app.snapshots.SnapshotStorage") as storage,
        ):
            with self.assertRaises(ValueError):
                archive_audit_range(settings, SnapshotRange(START, END), now=START)
        session.assert_not_called()
        storage.from_settings.assert_not_called()

    def test_missing_encryption_key_fails_before_connecting(self):
        settings = Settings(
            api_key="",
            database=DatabaseSettings("postgres", 5432, "db", "user", "secret"),
            storage=StorageSettings("http://rustfs:9000", "auditorias", "us-east-1", "a", "b"),
            archive=ARCHIVE,
        )
        with (
            mock.patch("app.snapshots.postgres_session") as session,
            mock.patch("app.snapshots.SnapshotStorage") as storage,
        ):
            with self.assertRaises(ConfigurationError):
                archive_audit_range(settings, SnapshotRange(START, END), now=END)
        session.assert_not_called()
        storage.from_settings.assert_not_called()


class Sha256FileTests(unittest.TestCase):
    def test_hashes_real_file_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.bin"
            content = b"audit" * 1000
            path.write_bytes(content)
            self.assertEqual(sha256_file(path), hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    unittest.main()
