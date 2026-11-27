import datetime as dt
import unittest
from unittest import mock

from app.anomalies import (
    ExpectedRowsMismatchError,
    SnapshotNotOffloadedError,
    compress_leftovers,
    delete_leftovers,
    list_closed_snapshots,
    purge_duplicates,
)
from app.duckdb_session import register_parquet_key
from app.history import query_history
from app.manifest import Manifest, SnapshotRange
from app.offload import offload_snapshot
from app.snapshots import create_snapshot
from tests.support import END, SOURCE, START, TEST_KEY, FakeStorage, audit_connection

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
DAY = dt.timedelta(days=1)
CLOSED = SnapshotRange(START, END)
MANIFEST_KEY = f"auditlog/{CLOSED.snapshot_id}/manifest.json"


class AnomalyTestCase(unittest.TestCase):
    """2026: el semestre CLOSED (ids 2, 3 y 4) ya está archivado y borrado de la base."""

    def setUp(self):
        self.connection = audit_connection()
        self.addCleanup(self.connection.close)
        register_parquet_key(self.connection, TEST_KEY)
        self.storage = FakeStorage()
        create_snapshot(self.connection, "audit", self.storage, SOURCE, CLOSED, NOW)
        offload_snapshot(
            self.connection, "audit", "audit", self.storage, SOURCE, CLOSED.snapshot_id, NOW
        )

    def insert(self, row_id, timestamp, changes=None):
        self.connection.execute("INSERT INTO audit VALUES (?, ?, ?)", [row_id, timestamp, changes])

    def ids_in_database(self):
        rows = self.connection.execute("SELECT id FROM audit ORDER BY id").fetchall()
        return [row_id for (row_id,) in rows]

    def manifest(self):
        return Manifest.from_dict(self.storage.get_json(MANIFEST_KEY))

    def history(self):
        page = query_history(self.storage, SOURCE, CLOSED, 100, 0, TEST_KEY)
        return [(row["id"], row["late_addition"]) for row in page.results]

    def purge(self):
        return purge_duplicates(self.connection, "audit", self.storage, SOURCE, CLOSED.snapshot_id)

    def compress(self, expected_rows, snapshot_id=CLOSED.snapshot_id):
        return compress_leftovers(
            self.connection, "audit", "audit", self.storage, SOURCE, snapshot_id, expected_rows
        )

    def delete(self, expected_rows, snapshot_id=CLOSED.snapshot_id):
        return delete_leftovers(
            self.connection, "audit", self.storage, SOURCE, snapshot_id, expected_rows
        )


class ClosedSnapshotTests(AnomalyTestCase):
    def test_only_offloaded_snapshots_are_closed(self):
        create_snapshot(self.connection, "audit", self.storage, SOURCE, SnapshotRange(END, END + DAY), NOW)
        closed = list_closed_snapshots(self.storage, SOURCE)
        self.assertEqual([manifest.snapshot_id for manifest in closed], [CLOSED.snapshot_id])

    def test_operations_refuse_semesters_without_offload(self):
        pending = SnapshotRange(END, END + DAY)
        create_snapshot(self.connection, "audit", self.storage, SOURCE, pending, NOW)
        for operation in (
            lambda: purge_duplicates(self.connection, "audit", self.storage, SOURCE, pending.snapshot_id),
            lambda: self.compress(1, pending.snapshot_id),
            lambda: self.delete(1, pending.snapshot_id),
        ):
            with self.assertRaises(SnapshotNotOffloadedError):
                operation()
        self.assertEqual(self.ids_in_database(), [1, 5])


class DuplicateTests(AnomalyTestCase):
    def test_only_ids_already_archived_are_deleted(self):
        self.insert(3, START + 30 * DAY, '{"reinserted": "with other content"}')
        self.insert(6, START + DAY)

        result = self.purge()

        self.assertEqual((result.deleted_rows, result.sample_ids), (1, [3]))
        self.assertEqual(self.ids_in_database(), [1, 5, 6])
        self.assertEqual(self.manifest().row_count, 3)

    def test_without_duplicates_nothing_is_deleted(self):
        self.insert(6, START + DAY)
        self.assertEqual(self.purge().deleted_rows, 0)
        self.assertEqual(self.ids_in_database(), [1, 5, 6])


class DeleteTests(AnomalyTestCase):
    def test_deletes_every_row_in_the_closed_semester(self):
        self.insert(6, START + DAY)
        self.insert(7, END - dt.timedelta(microseconds=1))
        result = self.delete(expected_rows=2)
        self.assertEqual((result.action, result.removed_rows), ("delete", 2))
        self.assertEqual(self.ids_in_database(), [1, 5])

    def test_changed_count_deletes_nothing(self):
        self.insert(6, START + DAY)
        self.insert(7, START + 2 * DAY)
        with self.assertRaises(ExpectedRowsMismatchError):
            self.delete(expected_rows=1)
        self.assertEqual(self.ids_in_database(), [1, 5, 6, 7])


class CompressTests(AnomalyTestCase):
    def test_new_rows_become_a_late_part_and_duplicates_are_discarded(self):
        self.insert(6, START + DAY, '{"late": true}')
        self.insert(3, START + 30 * DAY, '{"reinserted": true}')

        result = self.compress(expected_rows=2)

        self.assertEqual((result.compressed_rows, result.removed_rows), (1, 2))
        self.assertEqual(self.ids_in_database(), [1, 5])
        files = self.manifest().files
        self.assertEqual([file.key.rsplit("/", 1)[1] for file in files],
                         ["part-0001.parquet", "part-0002.parquet"])
        self.assertEqual(files[1].row_count, 1)
        self.assertEqual(
            self.history(), [(2, False), (6, True), (3, False), (4, False)]
        )

    def test_original_part_is_never_modified(self):
        original = self.storage.objects[self.manifest().files[0].key]
        self.insert(6, START + DAY)
        self.compress(expected_rows=1)
        self.assertEqual(self.storage.objects[self.manifest().files[0].key], original)

    def test_only_duplicates_creates_no_new_part(self):
        self.insert(3, START + 30 * DAY)
        result = self.compress(expected_rows=1)
        self.assertEqual((result.compressed_rows, result.removed_rows), (0, 1))
        self.assertEqual(len(self.manifest().files), 1)

    def test_changed_count_compresses_nothing(self):
        self.insert(6, START + DAY)
        self.insert(7, START + 2 * DAY)
        with self.assertRaises(ExpectedRowsMismatchError):
            self.compress(expected_rows=1)
        self.assertEqual(len(self.manifest().files), 1)
        self.assertEqual(self.ids_in_database(), [1, 5, 6, 7])

    def test_a_late_addition_reinserted_later_is_a_duplicate(self):
        self.insert(6, START + DAY)
        self.compress(expected_rows=1)
        self.insert(6, START + DAY)
        self.assertEqual(self.purge().deleted_rows, 1)
        self.assertEqual([row_id for row_id, _ in self.history()].count(6), 1)

    def test_failed_delete_is_recovered_as_duplicates_without_repeating_data(self):
        self.insert(6, START + DAY)
        with mock.patch("app.anomalies._in_transaction", side_effect=RuntimeError("caída")):
            with self.assertRaises(RuntimeError):
                self.compress(expected_rows=1)
        self.assertEqual(self.ids_in_database(), [1, 5, 6])
        self.assertEqual(len(self.manifest().files), 2)

        self.assertEqual(self.purge().deleted_rows, 1)
        self.assertEqual(self.ids_in_database(), [1, 5])
        self.assertEqual([row_id for row_id, _ in self.history()].count(6), 1)


if __name__ == "__main__":
    unittest.main()
