import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from app.manifest import Manifest, SnapshotFile, SnapshotRange
from tests.support import END, MICROSECOND, START


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

    def test_dates_are_midnight_in_the_configured_time_zone(self):
        bogota = ZoneInfo("America/Bogota")
        snapshot_range = SnapshotRange.from_dates(dt.date(2026, 1, 1), dt.date(2026, 7, 1), bogota)
        self.assertEqual(snapshot_range.start, dt.datetime(2026, 1, 1, 5, tzinfo=dt.timezone.utc))
        self.assertEqual(snapshot_range.snapshot_id, "20260101T050000Z_20260701T050000Z")

    def test_other_time_zones_are_normalized_to_utc(self):
        bogota = dt.timezone(dt.timedelta(hours=-5))
        snapshot_range = SnapshotRange(
            dt.datetime(2024, 12, 31, 19, tzinfo=bogota), dt.datetime(2025, 6, 30, 19, tzinfo=bogota)
        )
        self.assertEqual(snapshot_range.snapshot_id, "20250101T000000Z_20250701T000000Z")

    def test_period_in_progress_is_not_archivable(self):
        snapshot_range = SnapshotRange(START, END)
        snapshot_range.ensure_closed(END)
        with self.assertRaises(ValueError):
            snapshot_range.ensure_closed(END - MICROSECOND)

    def test_overlap_uses_half_open_bounds(self):
        semester = SnapshotRange(START, END)
        self.assertFalse(semester.overlaps(SnapshotRange(END, END + dt.timedelta(days=1))))
        self.assertTrue(semester.overlaps(SnapshotRange(END - MICROSECOND, END + dt.timedelta(days=1))))


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = Manifest(
            snapshot_id="20250101T000000Z_20250701T000000Z",
            table="public.auditlog_logentry",
            timestamp_column="timestamp",
            range=SnapshotRange(START, END),
            created_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
            files=(
                SnapshotFile(key="a.parquet", sha256="a" * 64, size=10, row_count=7),
                SnapshotFile(key="b.parquet", sha256="b" * 64, size=20, row_count=5),
            ),
        )

    def test_round_trip_preserves_every_field(self):
        self.assertEqual(Manifest.from_dict(self.manifest.to_dict()), self.manifest)

    def test_row_count_adds_all_files(self):
        self.assertEqual(self.manifest.to_dict()["row_count"], 12)

    def test_unknown_format_version_is_rejected(self):
        data = self.manifest.to_dict() | {"format_version": 99}
        with self.assertRaises(ValueError):
            Manifest.from_dict(data)


if __name__ == "__main__":
    unittest.main()
