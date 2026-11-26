import base64
import datetime as dt
import unittest

from app.duckdb_session import register_parquet_key
from app.manifest import SnapshotRange
from app.offload import (
    OffloadReceipt,
    OffloadVerificationError,
    SnapshotNotFoundError,
    offload_snapshot,
)
from app.snapshots import SnapshotIntegrityError, create_snapshot
from tests.support import END, SOURCE, START, TEST_KEY, FakeStorage, audit_connection

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
SNAPSHOT = SnapshotRange(START, END)
PREFIX = f"auditlog/{SNAPSHOT.snapshot_id}"
ALL_IDS = [1, 2, 3, 4, 5]
OUTSIDE_SNAPSHOT = [1, 5]


class OffloadSnapshotTests(unittest.TestCase):
    """El snapshot contiene los ids 2, 3 y 4; 1 y 5 están fuera de su rango."""

    def setUp(self):
        self.connection = audit_connection()
        self.addCleanup(self.connection.close)
        register_parquet_key(self.connection, TEST_KEY)
        self.storage = FakeStorage()
        create_snapshot(self.connection, "audit", self.storage, SOURCE, SNAPSHOT, NOW)

    def offload(self, snapshot_id=SNAPSHOT.snapshot_id, connection=None):
        return offload_snapshot(
            connection or self.connection, "audit", "audit", self.storage, SOURCE, snapshot_id, NOW
        )

    def remaining_ids(self, connection=None):
        rows = (connection or self.connection).execute("SELECT id FROM audit ORDER BY id")
        return [row_id for (row_id,) in rows.fetchall()]

    def assert_nothing_deleted(self, error, connection=None):
        with self.assertRaises(error):
            self.offload(connection=connection)
        self.assertEqual(self.remaining_ids(connection), ALL_IDS)
        self.assertNotIn(f"{PREFIX}/offload.json", self.storage.objects)

    def test_deletes_only_the_archived_rows_and_leaves_a_receipt(self):
        result = self.offload()

        self.assertFalse(result.already_offloaded)
        self.assertEqual(result.receipt.deleted_rows, 3)
        self.assertEqual(self.remaining_ids(), OUTSIDE_SNAPSHOT)
        stored = OffloadReceipt.from_dict(self.storage.get_json(f"{PREFIX}/offload.json"))
        self.assertEqual(stored, result.receipt)

    def test_manifest_is_not_modified(self):
        manifest_before = self.storage.objects[f"{PREFIX}/manifest.json"]
        self.offload()
        self.assertEqual(self.storage.objects[f"{PREFIX}/manifest.json"], manifest_before)

    def test_repeating_returns_the_existing_receipt(self):
        first = self.offload()
        second = self.offload()
        self.assertTrue(second.already_offloaded)
        self.assertEqual(second.receipt, first.receipt)
        self.assertEqual(self.remaining_ids(), OUTSIDE_SNAPSHOT)

    def test_lost_receipt_is_recovered_without_deleting_anything_else(self):
        self.offload()
        del self.storage.objects[f"{PREFIX}/offload.json"]
        retry = self.offload()
        self.assertFalse(retry.already_offloaded)
        self.assertEqual(retry.receipt.deleted_rows, 0)
        self.assertEqual(self.remaining_ids(), OUTSIDE_SNAPSHOT)
        self.assertIn(f"{PREFIX}/offload.json", self.storage.objects)

    def test_missing_snapshot_deletes_nothing(self):
        with self.assertRaises(SnapshotNotFoundError):
            self.offload("20240101T000000Z_20240701T000000Z")
        self.assertEqual(self.remaining_ids(), ALL_IDS)

    def test_snapshot_without_manifest_deletes_nothing(self):
        del self.storage.objects[f"{PREFIX}/manifest.json"]
        self.assert_nothing_deleted(SnapshotNotFoundError)

    def test_corrupted_archive_deletes_nothing(self):
        self.storage.objects[f"{PREFIX}/part-0001.parquet"] += b"tampered"
        self.assert_nothing_deleted(SnapshotIntegrityError)

    def test_archive_unreadable_with_the_current_key_deletes_nothing(self):
        other = audit_connection()
        self.addCleanup(other.close)
        register_parquet_key(other, base64.b64encode(bytes(32)).decode())
        self.assert_nothing_deleted(OffloadVerificationError, connection=other)

    def test_row_changed_after_archiving_deletes_nothing(self):
        self.connection.execute("UPDATE audit SET changes = '{\"edited\": true}' WHERE id = 3")
        self.assert_nothing_deleted(OffloadVerificationError)

    def test_row_added_to_the_range_after_archiving_deletes_nothing(self):
        self.connection.execute(
            "INSERT INTO audit VALUES (6, ?, NULL)", [START + dt.timedelta(days=1)]
        )
        with self.assertRaises(OffloadVerificationError):
            self.offload()
        self.assertEqual(self.remaining_ids(), [*ALL_IDS, 6])

    def test_rejects_identifiers_that_are_not_snapshot_ids(self):
        for snapshot_id in ("../auditlog", "20250101_20250701", ""):
            with self.subTest(snapshot_id=snapshot_id), self.assertRaises(ValueError):
                self.offload(snapshot_id)
        self.assertEqual(self.remaining_ids(), ALL_IDS)


if __name__ == "__main__":
    unittest.main()
