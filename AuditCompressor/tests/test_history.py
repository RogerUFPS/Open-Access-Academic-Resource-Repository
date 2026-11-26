import datetime as dt
import unittest

from app.config import ConfigurationError
from app.duckdb_session import register_parquet_key
from app.history import query_history
from app.manifest import SnapshotRange
from app.snapshots import SnapshotIntegrityError, create_snapshot
from tests.support import SOURCE, END, START, TEST_KEY, FakeStorage, audit_connection

DAY = dt.timedelta(days=1)
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
FIRST = SnapshotRange(START, END)
SECOND = SnapshotRange(END, END + DAY)
FIRST_PART = f"auditlog/{FIRST.snapshot_id}/part-0001.parquet"
SECOND_PART = f"auditlog/{SECOND.snapshot_id}/part-0001.parquet"


class QueryHistoryTests(unittest.TestCase):
    """Dos snapshots contiguos: FIRST contiene los ids 2, 3 y 4; SECOND, el id 5."""

    def setUp(self):
        connection = audit_connection()
        self.addCleanup(connection.close)
        register_parquet_key(connection, TEST_KEY)
        self.storage = FakeStorage()
        for snapshot_range in (FIRST, SECOND):
            create_snapshot(connection, "audit", self.storage, SOURCE, snapshot_range, NOW)

    def query(self, start, end, limit=100, offset=0, key=TEST_KEY):
        return query_history(
            self.storage, SOURCE, SnapshotRange(start, end), limit, offset, key
        )

    @staticmethod
    def ids(page):
        return [row["id"] for row in page.results]

    def test_combines_snapshots_crossing_their_boundary(self):
        page = self.query(END - DAY, END + DAY)
        self.assertEqual((page.count, self.ids(page)), (2, [4, 5]))

    def test_reads_only_snapshots_that_overlap_the_range(self):
        page = self.query(START, START + DAY)
        self.assertEqual(self.ids(page), [2])
        self.assertEqual(self.storage.downloaded, [FIRST_PART])

    def test_paginates_over_the_combined_result(self):
        page = self.query(START, END + DAY, limit=2, offset=1)
        self.assertEqual((page.count, self.ids(page)), (4, [3, 4]))

    def test_serializes_timestamps_and_json_columns(self):
        first, second = self.query(START, START + 31 * DAY).results
        self.assertEqual(first["timestamp"], "2025-01-01T00:00:00.000000+00:00")
        self.assertIsNone(first["changes"])
        self.assertEqual(second["changes"], {"nested": {"a": [1, 2]}})

    def test_range_without_snapshots_is_empty(self):
        page = self.query(END + 2 * DAY, END + 3 * DAY)
        self.assertEqual((page.count, page.results), (0, []))
        self.assertEqual(self.storage.downloaded, [])

    def test_corrupted_snapshot_is_never_read(self):
        self.storage.objects[SECOND_PART] += b"tampered"
        with self.assertRaises(SnapshotIntegrityError):
            self.query(START, END + DAY)

    def test_encrypted_snapshots_require_the_key(self):
        with self.assertRaises(ConfigurationError):
            self.query(START, END, key="")

    def test_rejects_invalid_pagination(self):
        for limit, offset in ((0, 0), (1001, 0), (10, -1)):
            with self.subTest(limit=limit, offset=offset), self.assertRaises(ValueError):
                self.query(START, END, limit, offset)


if __name__ == "__main__":
    unittest.main()
