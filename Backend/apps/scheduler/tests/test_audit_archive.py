"""Archivado semestral automático (AuditCompressor simulado)."""

import datetime as dt
import json
from unittest import mock
from zoneinfo import ZoneInfo

import httpx
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings

from apps.account.models import SuperadminAuditEvent, User
from apps.scheduler.audit_archive import (
    SOURCES,
    ArchiveServiceError,
    AuditCompressorOrchestrator,
    Semester,
    SemesterArchiveError,
    new_report,
    run_audit_archive,
)
from apps.scheduler.tasks import archive_audit_semesters, notify_audit_archive_report

BOGOTA = ZoneInfo("America/Bogota")
UTC = dt.timezone.utc
ARCHIVE_SETTINGS = {
    "AUDIT_COMPRESSOR_URL": "http://audit-compressor:8000",
    "AUDIT_COMPRESSOR_API_KEY": "test-key",
    "AUDIT_COMPRESSOR_TIMEOUT_SECONDS": 5,
    "AUDIT_ARCHIVE_TIMEZONE": "America/Bogota",
    "AUDIT_ARCHIVE_GRACE_DAYS": 7,
}


def local(year, month, day=15, hour=12):
    return dt.datetime(year, month, day, hour, tzinfo=BOGOTA)


def semester(year, half):
    return Semester.containing(local(year, 1 if half == 1 else 7), BOGOTA)


class FakeAuditCompressor:
    """Mismo contrato que AuditCompressorOrchestrator; borra con el ORM como el servicio."""

    def __init__(self):
        self.calls = []
        self.archived_ids = {}
        self.offloaded = set()
        self.failing_archives = set()
        self.unavailable_sources = set()
        self.offload_policy = {"auditlog": True, "superadmin_events": True}

    def sources(self):
        return dict(self.offload_policy)

    @staticmethod
    def _rows(source, snapshot_id):
        start, end = (
            dt.datetime.strptime(part, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            for part in snapshot_id.split("_")
        )
        return SOURCES[source].objects.filter(timestamp__gte=start, timestamp__lt=end)

    def archive(self, source, semester_):
        self.calls.append(("archive", source, semester_.label))
        if semester_.snapshot_id in self.failing_archives:
            raise SemesterArchiveError("fallo del semestre", 502)
        if (source, semester_.snapshot_id) in self.archived_ids:
            raise SemesterArchiveError("solapado", 409)
        rows = self._rows(source, semester_.snapshot_id)
        self.archived_ids[(source, semester_.snapshot_id)] = set(rows.values_list("pk", flat=True))
        return {}

    def offload(self, source, snapshot_id):
        self.calls.append(("offload", source, snapshot_id))
        if source in self.unavailable_sources:
            raise ArchiveServiceError("caído")
        key = (source, snapshot_id)
        if key not in self.archived_ids:
            return None
        if key in self.offloaded:
            return {"already_offloaded": True}
        self._rows(source, snapshot_id).delete()
        self.offloaded.add(key)
        return {"already_offloaded": False}

    def purge_duplicates(self, source, snapshot_id):
        self.calls.append(("purge_duplicates", source, snapshot_id))
        duplicates = self._rows(source, snapshot_id).filter(
            pk__in=self.archived_ids[(source, snapshot_id)]
        )
        ids = sorted(duplicates.values_list("pk", flat=True))
        duplicates.delete()
        return {"deleted_rows": len(ids), "sample_ids": ids}

    def close(self, source, semester_, ids):
        self.archived_ids[(source, semester_.snapshot_id)] = set(ids)
        self.offloaded.add((source, semester_.snapshot_id))


class SemesterTests(SimpleTestCase):
    def test_semesters_follow_colombian_midnight(self):
        cases = (
            (local(2026, 6, 30, 23), "2026-I"),
            (dt.datetime(2026, 7, 1, tzinfo=BOGOTA), "2026-II"),
            (local(2025, 12, 31, 22), "2025-II"),
            (dt.datetime(2026, 7, 1, 4, tzinfo=UTC), "2026-I"),  # 30-jun 23:00 en Colombia
        )
        for moment, label in cases:
            with self.subTest(moment=moment):
                self.assertEqual(Semester.containing(moment, BOGOTA).label, label)

    def test_snapshot_id_matches_audit_compressor(self):
        self.assertEqual(semester(2026, 1).snapshot_id, "20260101T050000Z_20260701T050000Z")


@override_settings(**ARCHIVE_SETTINGS)
class RunAuditArchiveTests(TestCase):
    def setUp(self):
        LogEntry.objects.all().delete()
        SuperadminAuditEvent.objects.all().delete()
        self.content_type = ContentType.objects.get_for_model(User)
        self.archive = FakeAuditCompressor()
        self.report = new_report()

    def log_at(self, timestamp, pk=None):
        return LogEntry.objects.create(
            pk=pk,
            content_type=self.content_type,
            object_pk="1",
            object_repr="demo",
            action=LogEntry.Action.UPDATE,
            timestamp=timestamp,
        )

    def run_archive(self, now=None):
        return run_audit_archive(self.archive, now or local(2026, 11, 26), self.report)

    def archived(self, source="auditlog"):
        return [label for call, src, label in self.archive.calls if call == "archive" and src == source]

    def test_archives_every_pending_semester_in_order_and_skips_the_current_one(self):
        for timestamp in (local(2025, 10), local(2025, 3), local(2026, 2), local(2026, 8)):
            self.log_at(timestamp)

        self.run_archive()

        self.assertEqual(self.archived(), ["2025-I", "2025-II", "2026-I"])
        self.assertEqual(list(LogEntry.objects.values_list("timestamp", flat=True)), [local(2026, 8)])

    def test_waits_the_grace_days_after_the_semester_ends(self):
        self.log_at(local(2026, 3))
        self.run_archive(now=local(2026, 7, 3))
        self.assertEqual(self.archived(), [])
        self.run_archive(now=local(2026, 7, 9))
        self.assertEqual(self.archived(), ["2026-I"])

    def test_semesters_without_records_are_skipped(self):
        self.log_at(local(2024, 2))
        self.log_at(local(2026, 2))
        self.run_archive()
        self.assertEqual(self.archived(), ["2024-I", "2026-I"])

    def test_nothing_pending_does_nothing(self):
        self.log_at(local(2026, 9))
        self.run_archive()
        self.assertEqual(self.archive.calls, [])
        self.assertEqual(self.report, new_report())

    def test_superadmin_events_are_archived_too(self):
        SuperadminAuditEvent.objects.create(action="login_succeeded", timestamp=local(2026, 3))
        self.run_archive()
        self.assertEqual(self.archived("superadmin_events"), ["2026-I"])
        self.assertFalse(SuperadminAuditEvent.objects.exists())

    def test_anomaly_deletes_duplicates_and_leaves_new_records_for_the_user(self):
        closed = semester(2026, 1)
        self.archive.close("auditlog", closed, ids={500})
        self.log_at(local(2026, 4), pk=500)  # ya archivado
        self.log_at(local(2026, 5), pk=600)  # nuevo

        self.run_archive()

        self.assertNotIn(("archive", "auditlog", "2026-I"), self.archive.calls)
        self.assertEqual(list(LogEntry.objects.values_list("pk", flat=True)), [600])
        self.assertEqual(
            self.report["duplicates_deleted"],
            [{"source": "auditlog", "semester": "2026-I", "snapshot_id": closed.snapshot_id,
              "deleted_rows": 1, "sample_ids": [500]}],
        )
        self.assertEqual(
            self.report["pending"],
            [{"source": "auditlog", "semester": "2026-I", "snapshot_id": closed.snapshot_id,
              "records": 1}],
        )

    def test_source_without_offload_is_archived_once_and_kept_in_the_database(self):
        self.archive.offload_policy["superadmin_events"] = False
        SuperadminAuditEvent.objects.create(action="logout", timestamp=local(2026, 3))

        self.run_archive()
        self.run_archive()

        self.assertEqual(self.archived("superadmin_events"), ["2026-I", "2026-I"])
        self.assertNotIn("offload", [call for call, src, _ in self.archive.calls if src == "superadmin_events"])
        self.assertEqual(SuperadminAuditEvent.objects.count(), 1)
        self.assertEqual(self.report, new_report())

    def test_source_unknown_to_audit_compressor_is_skipped(self):
        del self.archive.offload_policy["superadmin_events"]
        SuperadminAuditEvent.objects.create(action="logout", timestamp=local(2026, 3))
        self.run_archive()
        self.assertEqual(self.archived("superadmin_events"), [])

    def test_a_failing_semester_does_not_block_later_ones(self):
        self.archive.failing_archives.add(semester(2025, 2).snapshot_id)
        self.log_at(local(2025, 10))
        self.log_at(local(2026, 2))

        self.run_archive()

        self.assertEqual(self.archived(), ["2025-II", "2026-I"])
        self.assertEqual(list(LogEntry.objects.values_list("timestamp", flat=True)), [local(2025, 10)])

    def test_unavailable_service_stops_the_run_but_keeps_the_report(self):
        self.archive.close("auditlog", semester(2026, 1), ids=set())
        self.log_at(local(2026, 4))
        SuperadminAuditEvent.objects.create(action="logout", timestamp=local(2026, 3))
        self.archive.unavailable_sources.add("superadmin_events")

        with self.assertRaises(ArchiveServiceError):
            self.run_archive()

        self.assertEqual(len(self.report["pending"]), 1)
        self.assertTrue(SuperadminAuditEvent.objects.exists())


@override_settings(**ARCHIVE_SETTINGS)
class OrchestratorClientTests(SimpleTestCase):
    def client_for(self, handler):
        return AuditCompressorOrchestrator(transport=httpx.MockTransport(handler))

    def test_archive_sends_the_local_dates_with_the_api_key(self):
        seen = {}

        def handler(request):
            seen["request"] = request
            return httpx.Response(201, json={})

        with self.client_for(handler) as client:
            client.archive("auditlog", semester(2026, 1))

        request = seen["request"]
        self.assertEqual(request.url.path, "/sources/auditlog/snapshots")
        self.assertEqual(request.headers["X-API-Key"], "test-key")
        self.assertEqual(
            json.loads(request.content), {"start_date": "2026-01-01", "end_date": "2026-07-01"}
        )

    def test_reads_the_offload_policy_of_each_source(self):
        payload = {"sources": [{"name": "auditlog", "offload": True},
                               {"name": "superadmin_events", "offload": False}]}
        with self.client_for(lambda request: httpx.Response(200, json=payload)) as client:
            self.assertEqual(client.sources(), {"auditlog": True, "superadmin_events": False})

    def test_missing_snapshot_on_offload_is_not_an_error(self):
        with self.client_for(lambda request: httpx.Response(404)) as client:
            self.assertIsNone(client.offload("auditlog", semester(2026, 1).snapshot_id))

    def test_semester_errors_and_service_errors_are_distinguished(self):
        def network_error(request):
            raise httpx.ConnectError("sin conexión", request=request)

        for handler, error in (
            (lambda request: httpx.Response(409, json={"detail": "solapado"}), SemesterArchiveError),
            (lambda request: httpx.Response(502), SemesterArchiveError),
            (lambda request: httpx.Response(500), SemesterArchiveError),
            (lambda request: httpx.Response(503), ArchiveServiceError),
            (lambda request: httpx.Response(401), ArchiveServiceError),
            (network_error, ArchiveServiceError),
        ):
            with self.subTest(error=error.__name__), self.assertRaises(error):
                with self.client_for(handler) as client:
                    client.purge_duplicates("auditlog", semester(2026, 1).snapshot_id)

    @override_settings(AUDIT_COMPRESSOR_API_KEY="")
    def test_missing_configuration_is_a_service_error(self):
        with self.assertRaises(ArchiveServiceError):
            AuditCompressorOrchestrator()


class AuditArchiveTaskTests(TestCase):
    REPORT = {
        "pending": [{"source": "auditlog", "semester": "2026-I", "snapshot_id": "x", "records": 3}],
        "duplicates_deleted": [{"source": "auditlog", "semester": "2026-I", "snapshot_id": "x",
                                "deleted_rows": 2, "sample_ids": [7, 8]}],
    }

    def test_report_is_sent_even_if_the_run_fails(self):
        def failing_run(client, now, report):
            report["pending"].extend(self.REPORT["pending"])
            raise ArchiveServiceError("caído")

        with (
            mock.patch("apps.scheduler.tasks.AuditCompressorOrchestrator"),
            mock.patch("apps.scheduler.tasks.run_audit_archive", side_effect=failing_run),
            mock.patch("apps.scheduler.tasks.notify_audit_archive_report") as notify,
        ):
            with self.assertRaises(ArchiveServiceError):
                archive_audit_semesters()
        notify.delay.assert_called_once_with(
            {"pending": self.REPORT["pending"], "duplicates_deleted": []}
        )

    def test_runs_without_anomalies_send_nothing(self):
        with (
            mock.patch("apps.scheduler.tasks.AuditCompressorOrchestrator"),
            mock.patch("apps.scheduler.tasks.run_audit_archive", return_value={}),
            mock.patch("apps.scheduler.tasks.notify_audit_archive_report") as notify,
        ):
            archive_audit_semesters()
        notify.delay.assert_not_called()

    def test_report_goes_only_to_the_active_superadmin(self):
        superadmin = User.objects.create_superuser(
            email="archive-notify@example.org",
            password="Archive-notify-password-571",
            full_name="Superadmin",
        )
        User.objects.create_user(email="operator@example.org", password="Operator-password-571")

        with mock.patch("apps.scheduler.tasks.send_email") as send:
            self.assertEqual(notify_audit_archive_report.run(self.REPORT), 3)

        self.assertEqual(send.call_args.kwargs["bcc"], [superadmin.email])
        self.assertIn("3 registros", send.call_args.args[1])
        body = send.call_args.args[2]
        self.assertIn("comprimen dentro del semestre o se eliminan", body)
        self.assertIn("7, 8", body)

    def test_without_superadmin_nothing_is_sent(self):
        with mock.patch("apps.scheduler.tasks.send_email") as send:
            self.assertEqual(notify_audit_archive_report.run(self.REPORT), 0)
        send.assert_not_called()
