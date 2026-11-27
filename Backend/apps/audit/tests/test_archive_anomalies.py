"""Anomalías de archivado: ver y resolver registros en semestres ya comprimidos."""

import datetime as dt
import time
from unittest import mock

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.account.models import User
from apps.account.permissions import PERMISSION_MATRIX, normalize_permissions
from apps.audit.archive_client import ArchiveConflict, ArchiveUnavailable
from apps.audit.models import AuditLog

UTC = dt.timezone.utc
# Semestre 2026-I en hora de Colombia (UTC-5).
SNAPSHOT_ID = "20260101T050000Z_20260701T050000Z"
CLOSED = {"snapshot_id": SNAPSHOT_ID, "start": "2026-01-01T05:00:00+00:00", "end": "2026-07-01T05:00:00+00:00"}
LIST_URL = "/api/audit/archive-anomalies/"
RESOLVE_URL = "/api/audit/archive-anomalies/resolve/"
RECORDS_URL = f"/api/audit/archive-anomalies/auditlog/{SNAPSHOT_ID}/records/"
RESOLVE_BODY = {"source": "auditlog", "snapshot_id": SNAPSHOT_ID, "action": "compress", "expected_rows": 2}


class ArchiveAnomalyPermissionMatrixTests(SimpleTestCase):
    def test_anomalies_can_be_viewed_and_resolved(self):
        self.assertEqual(PERMISSION_MATRIX["audit"]["archive-anomalies"], {"view": True, "resolve": True})
        normalized = normalize_permissions({"audit": {"archive-anomalies": {"resolve": True}}})
        self.assertEqual(normalized["audit"]["archive-anomalies"], {"resolve": True, "view": True})


class ArchiveAnomalyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser(
            email="anomaly-superadmin@example.org",
            password="Anomaly-superadmin-password-571",
            full_name="Superadmin",
        )
        cls.viewer = User.objects.create_user(
            email="anomaly-viewer@example.org",
            password="Anomaly-viewer-password-571",
            permissions={"audit": {"archive-anomalies": {"view": True}}},
        )
        cls.resolver = User.objects.create_user(
            email="anomaly-resolver@example.org",
            password="Anomaly-resolver-password-571",
            permissions={"audit": {"archive-anomalies": {"view": True, "resolve": True}}},
        )
        cls.outsider = User.objects.create_user(
            email="anomaly-outsider@example.org",
            password="Anomaly-outsider-password-571",
            permissions={"audit": {"logs": {"view": True}}},
        )

    def setUp(self):
        LogEntry.objects.all().delete()
        self.content_type = ContentType.objects.get_for_model(User)
        patcher = mock.patch("apps.audit.views.AuditArchiveClient")
        self.addCleanup(patcher.stop)
        self.archive = patcher.start().return_value.__enter__.return_value
        self.archive.closed_snapshots.side_effect = (
            lambda source: [CLOSED] if source == "auditlog" else []
        )
        self.archive.resolve_leftovers.return_value = {
            "snapshot_id": SNAPSHOT_ID, "action": "compress", "compressed_rows": 1, "removed_rows": 2,
        }

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        session = client.session
        session["superadmin_mfa_satisfied"] = True
        session["_session_renewed_at"] = int(time.time())
        session.save()
        return client

    def log_at(self, timestamp):
        return LogEntry.objects.create(
            content_type=self.content_type,
            object_pk="1",
            object_repr="insertado a mano",
            action=LogEntry.Action.UPDATE,
            timestamp=timestamp,
        )

    def test_lists_closed_semesters_that_have_records(self):
        self.log_at(dt.datetime(2026, 3, 1, tzinfo=UTC))
        self.log_at(dt.datetime(2026, 4, 1, tzinfo=UTC))
        self.log_at(dt.datetime(2026, 9, 1, tzinfo=UTC))  # semestre actual: no es anomalía

        response = self.client_for(self.viewer).get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [{**CLOSED, "source": "auditlog", "records": 2}])

    def test_closed_semesters_without_records_are_not_anomalies(self):
        response = self.client_for(self.viewer).get(LIST_URL)
        self.assertEqual(response.json(), [])

    def test_records_are_shown_paginated_for_review(self):
        for day in range(1, 13):
            self.log_at(dt.datetime(2026, 3, day, tzinfo=UTC))

        response = self.client_for(self.viewer).get(RECORDS_URL, {"page_size": 5})

        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((data["total_items"], data["total_pages"]), (12, 3))
        self.assertIn("action_name", data["results"][0])
        self.assertIn("changes", data["results"][0])

    def test_unknown_source_or_snapshot_is_not_found(self):
        client = self.client_for(self.viewer)
        self.assertEqual(
            client.get(f"/api/audit/archive-anomalies/users/{SNAPSHOT_ID}/records/").status_code, 404
        )
        self.assertEqual(
            client.get("/api/audit/archive-anomalies/auditlog/bad-id/records/").status_code, 404
        )

    def test_other_audit_permissions_do_not_open_anomalies(self):
        client = self.client_for(self.outsider)
        self.assertEqual(client.get(LIST_URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(client.get(RECORDS_URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_viewing_does_not_allow_resolving(self):
        response = self.client_for(self.viewer).post(RESOLVE_URL, RESOLVE_BODY, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.archive.resolve_leftovers.assert_not_called()

    def test_resolver_and_superadmin_can_resolve_and_the_decision_is_recorded(self):
        for user in (self.resolver, self.superadmin):
            with self.subTest(user=user.email):
                response = self.client_for(user).post(RESOLVE_URL, RESOLVE_BODY, format="json")
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.archive.resolve_leftovers.assert_called_with("auditlog", SNAPSHOT_ID, "compress", 2)
                entry = AuditLog.objects.filter(object_pk=SNAPSHOT_ID).latest("pk")
                self.assertEqual(entry.actor, user)
                self.assertEqual(entry.action, LogEntry.Action.UPDATE)
                self.assertEqual(entry.additional_data["compressed_rows"], 1)
                self.assertEqual(entry.additional_data["expected_rows"], 2)

    def test_delete_is_recorded_as_deletion(self):
        self.archive.resolve_leftovers.return_value = {
            "snapshot_id": SNAPSHOT_ID, "action": "delete", "compressed_rows": 0, "removed_rows": 2,
        }
        body = RESOLVE_BODY | {"action": "delete"}
        self.client_for(self.resolver).post(RESOLVE_URL, body, format="json")
        entry = AuditLog.objects.filter(object_pk=SNAPSHOT_ID).latest("pk")
        self.assertEqual(entry.action, LogEntry.Action.DELETE)

    def test_invalid_decisions_are_rejected_without_calling_the_service(self):
        client = self.client_for(self.resolver)
        for body in (
            RESOLVE_BODY | {"action": "archive"},
            RESOLVE_BODY | {"expected_rows": 0},
            RESOLVE_BODY | {"source": "users"},
            RESOLVE_BODY | {"snapshot_id": "../x"},
        ):
            with self.subTest(body=body):
                response = client.post(RESOLVE_URL, body, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.archive.resolve_leftovers.assert_not_called()

    def test_service_answers_are_translated(self):
        client = self.client_for(self.resolver)
        for error, expected in (
            (ArchiveConflict("Hay 3 registros y se esperaban 2."), status.HTTP_409_CONFLICT),
            (ArchiveUnavailable("caído"), status.HTTP_503_SERVICE_UNAVAILABLE),
        ):
            with self.subTest(error=type(error).__name__):
                self.archive.resolve_leftovers.side_effect = error
                response = client.post(RESOLVE_URL, RESOLVE_BODY, format="json")
                self.assertEqual(response.status_code, expected)
        self.assertFalse(AuditLog.objects.filter(object_pk=SNAPSHOT_ID).exists())
