"""Consulta de auditoría archivada en AuditCompressor (servicio externo simulado)."""

import datetime as dt
import time
from unittest import mock

import httpx
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.account.models import SuperadminAuditEvent, User
from apps.account.permissions import PERMISSION_MATRIX, normalize_permissions
from apps.audit.archive_client import (
    ArchiveIntegrityError,
    ArchivePage,
    ArchiveUnavailable,
    AuditArchiveClient,
)
from apps.audit.models import AuditLog

API_KEY = "test-audit-compressor-key"
ARCHIVE_SETTINGS = {
    "AUDIT_COMPRESSOR_URL": "http://audit-compressor:8000",
    "AUDIT_COMPRESSOR_API_KEY": API_KEY,
    "AUDIT_COMPRESSOR_TIMEOUT_SECONDS": 5,
}
LOGS_URL = "/api/audit/archived-logs/"
EVENTS_URL = "/api/audit/archived-superadmin-events/"
QUERY = {"start_date": "2025-01-01", "end_date": "2025-07-01"}


@override_settings(**ARCHIVE_SETTINGS)
class AuditArchiveClientTests(SimpleTestCase):
    def client_with(self, handler):
        return AuditArchiveClient(transport=httpx.MockTransport(handler))

    def history(self, handler):
        with self.client_with(handler) as client:
            return client.history("auditlog", dt.date(2025, 1, 1), dt.date(2025, 7, 1), 10, 20)

    def test_sends_api_key_and_range_to_the_source_history(self):
        seen = {}

        def handler(request):
            seen["request"] = request
            return httpx.Response(200, json={"count": 1, "results": [{"id": 7}]})

        page = self.history(handler)

        self.assertEqual(page, ArchivePage(count=1, results=[{"id": 7}]))
        request = seen["request"]
        self.assertEqual(request.url.path, "/sources/auditlog/history")
        self.assertEqual(request.headers["X-API-Key"], API_KEY)
        self.assertEqual(
            dict(request.url.params),
            {"start_date": "2025-01-01", "end_date": "2025-07-01", "limit": "10", "offset": "20"},
        )

    def test_integrity_failure_is_reported_separately(self):
        with self.assertRaises(ArchiveIntegrityError):
            self.history(lambda request: httpx.Response(502))

    def test_other_failures_mean_unavailable_without_exposing_the_key(self):
        def network_error(request):
            raise httpx.ConnectError("sin conexión", request=request)

        for handler in (
            network_error,
            lambda request: httpx.Response(401),
            lambda request: httpx.Response(503),
            lambda request: httpx.Response(200, text="no es json"),
            lambda request: httpx.Response(200, json={"results": []}),
        ):
            with self.subTest(handler=handler), self.assertRaises(ArchiveUnavailable) as raised:
                self.history(handler)
            self.assertNotIn(API_KEY, str(raised.exception))

    @override_settings(AUDIT_COMPRESSOR_API_KEY="")
    def test_missing_configuration_is_unavailable(self):
        with self.assertRaises(ArchiveUnavailable):
            AuditArchiveClient()


class ArchivedAuditPermissionMatrixTests(SimpleTestCase):
    def test_archived_resources_are_view_only_and_assignable(self):
        audit = PERMISSION_MATRIX["audit"]
        self.assertEqual(audit["archived-logs"], {"view": True})
        self.assertEqual(audit["archived-superadmin-events"], {"view": True})
        normalized = normalize_permissions(
            {"audit": {"archived-logs": {"view": True}, "archived-superadmin-events": {"view": True}}}
        )
        self.assertTrue(normalized["audit"]["archived-logs"]["view"])
        with self.assertRaises(ValueError):
            normalize_permissions({"audit": {"archived-logs": {"create": True}}})


@override_settings(**ARCHIVE_SETTINGS)
class ArchivedAuditViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser(
            email="archive-superadmin@example.org",
            password="Archive-superadmin-password-571",
            full_name="Superadmin de prueba",
        )
        cls.auditor = User.objects.create_user(
            email="archive-auditor@example.org",
            password="Archive-auditor-password-571",
            permissions={"audit": {"archived-logs": {"view": True}}},
        )
        cls.live_viewer = User.objects.create_user(
            email="live-viewer@example.org",
            password="Live-viewer-password-571",
            permissions={"audit": {"logs": {"view": True}}},
        )

    def setUp(self):
        patcher = mock.patch("apps.audit.views.AuditArchiveClient")
        self.addCleanup(patcher.stop)
        self.archive = patcher.start().return_value.__enter__.return_value
        self.archive.history.return_value = ArchivePage(
            count=25, results=[{"id": number} for number in range(11, 21)]
        )

    def client_for(self, user, mfa_satisfied=True):
        client = APIClient()
        client.force_authenticate(user)
        session = client.session
        session["superadmin_mfa_satisfied"] = mfa_satisfied
        session["_session_renewed_at"] = int(time.time())
        session.save()
        return client

    def access_logs(self):
        return AuditLog.objects.filter(action=LogEntry.Action.ACCESS).order_by("pk")

    def test_anonymous_users_cannot_query(self):
        response = APIClient().get(LOGS_URL, QUERY)
        self.assertIn(
            response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
        )
        self.archive.history.assert_not_called()

    def test_live_audit_permission_does_not_grant_archived_access(self):
        client = self.client_for(self.live_viewer)
        for url in (LOGS_URL, EVENTS_URL):
            with self.subTest(url=url):
                self.assertEqual(client.get(url, QUERY).status_code, status.HTTP_403_FORBIDDEN)
        self.archive.history.assert_not_called()

    def test_each_permission_opens_only_its_own_archive(self):
        client = self.client_for(self.auditor)
        self.assertEqual(client.get(LOGS_URL, QUERY).status_code, status.HTTP_200_OK)
        self.assertEqual(client.get(EVENTS_URL, QUERY).status_code, status.HTTP_403_FORBIDDEN)

    def test_superadmin_can_query_both_archives_after_mfa(self):
        client = self.client_for(self.superadmin)
        for url, source in ((LOGS_URL, "auditlog"), (EVENTS_URL, "superadmin_events")):
            with self.subTest(url=url):
                self.assertEqual(client.get(url, QUERY).status_code, status.HTTP_200_OK)
                self.assertEqual(self.archive.history.call_args.args[0], source)

    def test_superadmin_without_mfa_cannot_query(self):
        client = self.client_for(self.superadmin, mfa_satisfied=False)
        self.assertEqual(client.get(LOGS_URL, QUERY).status_code, status.HTTP_403_FORBIDDEN)
        self.archive.history.assert_not_called()

    def test_page_matches_the_project_pagination_format(self):
        response = self.client_for(self.auditor).get(LOGS_URL, QUERY | {"page": 2, "page_size": 10})

        data = response.json()
        self.assertEqual(
            {key: data[key] for key in ("current_page", "total_pages", "page_size", "total_items")},
            {"current_page": 2, "total_pages": 3, "page_size": 10, "total_items": 25},
        )
        self.assertIn("page=3", data["next"])
        self.assertNotIn("page=", data["previous"])
        self.assertEqual(data["results"][0], {"item_number": 11, "id": 11})
        self.archive.history.assert_called_once_with(
            "auditlog", dt.date(2025, 1, 1), dt.date(2025, 7, 1), limit=10, offset=10
        )

    def test_page_beyond_the_results_is_not_found(self):
        response = self.client_for(self.auditor).get(LOGS_URL, QUERY | {"page": 4})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_parameters_are_rejected_without_querying_or_logging(self):
        client = self.client_for(self.auditor)
        for params in (
            {"start_date": "2025-07-01", "end_date": "2025-01-01"},
            {"start_date": "2025-01-01", "end_date": "2025-01-01"},
            {"start_date": "2025-01-01"},
            QUERY | {"page_size": 101},
            QUERY | {"page": 0},
        ):
            with self.subTest(params=params):
                self.assertEqual(client.get(LOGS_URL, params).status_code, status.HTTP_400_BAD_REQUEST)
        self.archive.history.assert_not_called()
        self.assertFalse(self.access_logs().exists())

    def test_each_query_is_recorded_as_access_without_the_returned_data(self):
        self.client_for(self.superadmin).get(EVENTS_URL, QUERY)

        (entry,) = self.access_logs()
        self.assertEqual(entry.actor, self.superadmin)
        self.assertEqual(entry.actor_email, self.superadmin.email)
        self.assertEqual(entry.content_type, ContentType.objects.get_for_model(SuperadminAuditEvent))
        self.assertEqual(entry.object_pk, "superadmin_events")
        self.assertEqual(
            entry.additional_data,
            {
                "archive_source": "superadmin_events",
                "start_date": "2025-01-01",
                "end_date": "2025-07-01",
                "page": 1,
                "page_size": 10,
                "outcome": "ok",
                "total_items": 25,
            },
        )

    def test_service_failures_are_reported_and_still_recorded(self):
        client = self.client_for(self.auditor)
        for error, expected, outcome in (
            (ArchiveUnavailable("caído"), status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable"),
            (ArchiveIntegrityError("hash"), status.HTTP_502_BAD_GATEWAY, "integrity_error"),
        ):
            with self.subTest(outcome=outcome):
                self.archive.history.side_effect = error
                response = client.get(LOGS_URL, QUERY)
                self.assertEqual(response.status_code, expected)
                self.assertNotIn(API_KEY, response.content.decode())
                self.assertEqual(self.access_logs().last().additional_data["outcome"], outcome)
