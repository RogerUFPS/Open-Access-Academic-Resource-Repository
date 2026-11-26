import datetime as dt
import unittest
from dataclasses import replace
from unittest import mock

from fastapi.testclient import TestClient

from app import main
from app.config import ConfigurationError, DatabaseSettings, Settings, StorageSettings, get_settings
from app.history import HistoryPage
from app.manifest import Manifest, SnapshotFile, SnapshotRange
from app.snapshots import SnapshotConflictError, SnapshotIntegrityError
from tests.support import END, SOURCE, START

API_KEY = "test-api-key"
HEADERS = {"X-API-Key": API_KEY}
BODY = {"start_date": "2025-01-01", "end_date": "2025-07-01"}
EVENTS = replace(SOURCE, name="superadmin_events")
SETTINGS = Settings(
    api_key=API_KEY,
    database=DatabaseSettings("postgres", 5432, "db", "user", "secret"),
    storage=StorageSettings("http://rustfs:9000", "auditorias", "us-east-1", "a", "b"),
    sources={"auditlog": SOURCE, "superadmin_events": EVENTS},
)
MANIFEST = Manifest(
    snapshot_id="20250101T000000Z_20250701T000000Z",
    table="public.auditlog_logentry",
    timestamp_column="timestamp",
    range=SnapshotRange(START, END),
    created_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
    files=(SnapshotFile(key="auditlog/x/part-0001.parquet", sha256="a" * 64, size=10, row_count=3),),
)


class EndpointTestCase(unittest.TestCase):
    target = ""

    def setUp(self):
        self.settings = SETTINGS
        main.app.dependency_overrides[get_settings] = lambda: self.settings
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client = TestClient(main.app)

    def patch(self, name, **kwargs):
        patcher = mock.patch(f"app.main.{name}", **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()


class SnapshotEndpointTests(EndpointTestCase):
    def setUp(self):
        super().setUp()
        self.archive = self.patch("archive_range", return_value=MANIFEST)

    def post(self, body=BODY, headers=HEADERS, source="auditlog"):
        return self.client.post(f"/sources/{source}/snapshots", json=body, headers=headers)

    def test_health_does_not_require_api_key(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "audit-compressor"})

    def test_creates_snapshot_for_the_requested_source_and_range(self):
        for name, source in (("auditlog", SOURCE), ("superadmin_events", EVENTS)):
            with self.subTest(source=name):
                response = self.post(source=name)
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json(), MANIFEST.to_dict())
                _, archived_source, snapshot_range, _ = self.archive.call_args.args
                self.assertEqual(archived_source, source)
                self.assertEqual(snapshot_range, SnapshotRange(START, END))

    def test_unknown_source_is_not_found(self):
        self.assertEqual(self.post(source="users").status_code, 404)
        self.archive.assert_not_called()

    def test_requires_a_valid_api_key_before_revealing_sources(self):
        for source in ("auditlog", "users"):
            for headers in ({}, {"X-API-Key": "wrong"}):
                with self.subTest(source=source, headers=headers):
                    self.assertEqual(self.post(headers=headers, source=source).status_code, 401)
        self.archive.assert_not_called()

    def test_unconfigured_api_key_disables_the_endpoint(self):
        self.settings = replace(SETTINGS, api_key="")
        self.assertEqual(self.post().status_code, 503)
        self.archive.assert_not_called()

    def test_invalid_or_unfinished_ranges_are_rejected(self):
        future = (dt.date.today() + dt.timedelta(days=2)).isoformat()
        bodies = (
            {"start_date": "2025-07-01", "end_date": "2025-01-01"},
            {"start_date": "2025-01-01", "end_date": "2025-01-01"},
            {"start_date": "2025-01-01", "end_date": future},
            {"start_date": "2025-13-01", "end_date": "2025-07-01"},
            {"start_date": "2025-01-01"},
        )
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(self.post(body=body).status_code, 422)
        self.archive.assert_not_called()

    def test_archiving_errors_map_to_http_statuses(self):
        cases = (
            (SnapshotConflictError("solapado"), 409),
            (SnapshotIntegrityError("hash distinto"), 502),
            (ConfigurationError("Faltan variables de entorno: S3_BUCKET."), 503),
        )
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.archive.side_effect = error
                self.assertEqual(self.post().status_code, expected)

    def test_concurrent_order_is_rejected(self):
        self.assertTrue(main._archive_lock.acquire(blocking=False))
        try:
            self.assertEqual(self.post().status_code, 409)
        finally:
            main._archive_lock.release()
        self.archive.assert_not_called()

    def test_lock_is_released_after_a_failed_order(self):
        self.archive.side_effect = SnapshotIntegrityError("hash distinto")
        self.assertEqual(self.post().status_code, 502)
        self.archive.side_effect = None
        self.assertEqual(self.post().status_code, 201)


class HistoryEndpointTests(EndpointTestCase):
    QUERY = {"start_date": "2025-01-01", "end_date": "2025-07-01"}

    def setUp(self):
        super().setUp()
        self.read = self.patch(
            "read_history", return_value=HistoryPage(count=1, results=[{"id": 2}])
        )

    def get(self, params=None, headers=HEADERS, source="auditlog"):
        return self.client.get(
            f"/sources/{source}/history", params=params or self.QUERY, headers=headers
        )

    def test_returns_a_page_for_the_requested_source_and_range(self):
        response = self.get(self.QUERY | {"limit": 10, "offset": 20}, source="superadmin_events")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"count": 1, "limit": 10, "offset": 20, "results": [{"id": 2}]}
        )
        _, source, snapshot_range, limit, offset = self.read.call_args.args
        self.assertEqual(source, EVENTS)
        self.assertEqual((snapshot_range, limit, offset), (SnapshotRange(START, END), 10, 20))

    def test_unknown_source_is_not_found(self):
        self.assertEqual(self.get(source="users").status_code, 404)
        self.read.assert_not_called()

    def test_requires_a_valid_api_key(self):
        self.assertEqual(self.get(headers={}).status_code, 401)
        self.read.assert_not_called()

    def test_invalid_parameters_are_rejected(self):
        for params in (
            {"start_date": "2025-07-01", "end_date": "2025-01-01"},
            {"start_date": "2025-01-01"},
            self.QUERY | {"limit": 0},
            self.QUERY | {"limit": 1001},
            self.QUERY | {"offset": -1},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.get(params).status_code, 422)
        self.read.assert_not_called()

    def test_errors_map_to_http_statuses(self):
        for error, expected in (
            (SnapshotIntegrityError("hash distinto"), 502),
            (ConfigurationError("Faltan variables de entorno: S3_BUCKET."), 503),
        ):
            with self.subTest(error=type(error).__name__):
                self.read.side_effect = error
                self.assertEqual(self.get().status_code, expected)


if __name__ == "__main__":
    unittest.main()
