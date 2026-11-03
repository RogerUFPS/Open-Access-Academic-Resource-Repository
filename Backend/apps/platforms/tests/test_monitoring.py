from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient, APITestCase

from apps.account.email import EmailDeliveryError
from apps.account.models import AccessPreset, User
from apps.journal.models import Journal, SharedJournalPlatform
from apps.platforms import filters, models, notifications, services, tasks


CHECK_PERMISSION = {"platforms": {"platforms": {"check_link": True}}}


class MonitorFixtures:
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="monitor@example.org", is_superadmin=True,
        )
        self.platform = models.Platform.objects.create(name="Monitor", created_by=self.user)

    def log(self, platform=None, *, count=0, checked=False, **kwargs):
        return models.LinkCheckLog.objects.create(
            platform=platform or self.platform,
            url=kwargs.pop("url", "https://8.8.8.8/public"),
            fail_count=count, last_check=timezone.now() if checked else None,
            created_by=self.user, **kwargs,
        )

    def another_platform(self, number):
        return models.Platform.objects.create(name=f"Monitor {number}", created_by=self.user)


class CurrentLinksTests(MonitorFixtures, TestCase):
    def test_new_unverified_url_replaces_checked_history(self):
        old = self.log(count=4, checked=True)
        new = self.log(url="https://8.8.8.8/new")
        self.assertEqual(list(services.current_link_logs()), [new])
        self.assertFalse(services.pending_link_retries().exists())
        self.assertNotEqual(services.latest_platform_link_log(self.platform), old)

    def test_general_and_journal_current_urls(self):
        public = self.log()
        journal = Journal.objects.create(issn="1234-5678", title="Monitor", created_by=self.user)
        relation = SharedJournalPlatform.objects.create(
            platform=self.platform, journal=journal, created_by=self.user,
        )
        self.log(journal_platform=relation, checked=True, count=5)
        current = self.log(journal_platform=relation, url="https://8.8.8.8/journal")
        self.assertSetEqual(set(services.current_link_logs()), {public, current})
        for target in (relation, journal, self.platform):
            with self.subTest(deleted=type(target).__name__):
                target.deleted_at = timezone.now()
                target.save(update_fields=["deleted_at"])
                self.assertFalse(services.current_link_logs().filter(pk=current.pk).exists())
                target.deleted_at = None
                target.save(update_fields=["deleted_at"])

    def test_retry_boundaries_and_unverified(self):
        eligible = set()
        for count in range(8):
            log = self.log(self.another_platform(count), count=count, checked=True)
            if 0 < count < services.LINK_FAILURE_THRESHOLD:
                eligible.add(log.pk)
        self.log(count=3, checked=False)
        self.assertSetEqual(set(services.pending_link_retries().values_list("pk", flat=True)), eligible)

    def test_confirmed_filter_only_current_live_contexts(self):
        self.log(count=7, checked=True)
        current = self.log(count=5, checked=True)
        available = self.log(self.another_platform(1), checked=True, is_active=True)
        unverified = self.log(self.another_platform(2))
        dead = self.log(self.another_platform(3), count=5, checked=True, deleted_at=timezone.now())
        result = filters.LinkCheckLogFilter(
            {"failure_confirmed": "true"}, queryset=models.LinkCheckLog.objects.all(),
        ).qs
        self.assertEqual(list(result), [current])
        complement = filters.LinkCheckLogFilter(
            {"failure_confirmed": "false"}, queryset=models.LinkCheckLog.objects.all(),
        ).qs
        self.assertSetEqual(set(complement), {available, unverified})
        self.assertNotIn(dead, result)


class CheckStateTests(MonitorFixtures, TestCase):
    @patch("apps.platforms.services._validate_safe_http_url")
    @patch("apps.platforms.services._perform_link_check", return_value=(503, False))
    def test_five_failures_recovery_and_new_incident(self, check, _safe):
        self.log()
        with patch("apps.platforms.notifications.email.send_email") as send:
            for count in range(1, 6):
                result = services.check_link_context(platform=self.platform, user=self.user)
                self.assertEqual(result.fail_count, count)
                self.assertFalse(result.is_active)
                self.assertEqual(services.confirmed_link_failures().exists(), count == 5)
                self.assertEqual(services.pending_link_retries().exists(), count < 5)
            result.failure_notified_at = timezone.now()
            result.save(update_fields=["failure_notified_at"])
            sixth = services.check_link_context(platform=self.platform, user=self.user)
            self.assertEqual(sixth.fail_count, 6)
            self.assertIsNotNone(sixth.failure_notified_at)
            check.return_value = (200, True)
            success = services.check_link_context(platform=self.platform, user=self.user)
            self.assertEqual(success.fail_count, 0)
            self.assertTrue(success.is_active)
            self.assertIsNone(success.failure_notified_at)
            self.assertFalse(services.confirmed_link_failures().exists())
            check.return_value = (500, False)
            for _ in range(5):
                next_incident = services.check_link_context(platform=self.platform, user=self.user)
            self.assertEqual(next_incident.fail_count, 5)
            self.assertIsNone(next_incident.failure_notified_at)
            send.assert_not_called()

    @patch("apps.platforms.services._validate_safe_http_url")
    @patch("apps.platforms.services._perform_link_check", return_value=(200, True))
    def test_recovery_from_one_or_four_failures(self, _check, _safe):
        for count in (1, 4):
            with self.subTest(count=count):
                self.log(count=count, checked=True)
                result = services.check_link_context(platform=self.platform, user=self.user)
                self.assertEqual(result.fail_count, 0)
                self.assertTrue(result.is_active)

    @patch("apps.platforms.services._validate_safe_http_url")
    @patch("apps.platforms.services._perform_link_check")
    def test_url_changed_during_http_is_not_overwritten(self, check, _safe):
        old = self.log()
        def change_url(url):
            self.log(url="https://8.8.8.8/replacement")
            return 500, False
        check.side_effect = change_url
        current = services.check_link_context(platform=self.platform, user=self.user, expected_log_id=old.pk)
        self.assertEqual(current.url, "https://8.8.8.8/replacement")
        self.assertIsNone(current.last_check)
        self.assertEqual(models.LinkCheckLog.objects.count(), 2)


class MonitorAPITests(MonitorFixtures, APITestCase):
    @patch("apps.platforms.views.dispatch_link_checks.delay")
    @patch("apps.platforms.services._perform_link_check")
    def test_triggers_accept_without_http(self, check, enqueue):
        enqueue.return_value.id = "task-123"
        self.user.is_superadmin = False
        self.user.permissions = CHECK_PERMISSION
        self.user.save()
        self.client.force_authenticate(self.user)
        for endpoint, mode in (("check-links-async", "all"), ("check-failed-links", "failed")):
            response = self.client.post(f"/api/platforms/{endpoint}/", {}, format="json")
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.data["mode"], mode)
            self.assertEqual(response.data["task_id"], "task-123")
            enqueue.assert_called_with(response.data["run_id"])
            self.assertEqual(models.LinkCheckRun.objects.get(pk=response.data["run_id"]).requested_by, self.user)
        check.assert_not_called()

    @patch("apps.platforms.views.dispatch_link_checks.delay")
    def test_anonymous_and_missing_permission_cannot_enqueue(self, enqueue):
        for endpoint in ("check-links-async", "check-failed-links"):
            self.client.force_authenticate(None)
            response = self.client.post(f"/api/platforms/{endpoint}/")
            self.assertIn(response.status_code, (401, 403))
            denied = User.objects.create_user(email=f"{endpoint}@example.org")
            self.client.force_authenticate(denied)
            self.assertEqual(self.client.post(f"/api/platforms/{endpoint}/").status_code, 403)
        enqueue.assert_not_called()

    @patch("apps.platforms.views.dispatch_link_checks.delay", side_effect=OperationalError("broker down"))
    def test_broker_failure_is_not_reported_as_accepted(self, _enqueue):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/platforms/check-links-async/")
        self.assertEqual(response.status_code, 503)

    @patch("apps.platforms.views.services.check_all_current_links")
    @patch("apps.platforms.views.services.check_platform_links")
    def test_legacy_actions_use_local_verification_permission(self, check_platform, check_all):
        self.user.is_superadmin = False
        self.user.permissions = {"platforms": {"platforms": {"create": True, "view": True}}}
        self.user.save()
        self.client.force_authenticate(self.user)
        paths = (
            "/api/platforms/check-links/",
            f"/api/platforms/{self.platform.pk}/check-links/",
        )
        for path in paths:
            self.assertEqual(self.client.post(path).status_code, 403)
        check_platform.assert_not_called()
        check_all.assert_not_called()
        self.user.permissions = {"platforms": {"platforms": {"check_link": True, "view": True}}}
        self.user.save()
        self.assertEqual(self.client.post(paths[0]).status_code, 204)
        check_all.assert_called_once()
        check_platform.return_value = {
            "platform": self.platform.pk, "checked": 0, "available": 0, "failed": 0, "results": [],
        }
        self.assertEqual(self.client.post(paths[1]).status_code, 200)
        check_platform.assert_called_once()

    @patch("apps.platforms.views.services.check_all_current_links")
    def test_legacy_global_endpoint_keeps_204(self, check):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post("/api/platforms/check-links/").status_code, 204)
        check.assert_called_once()

    @patch("apps.platforms.views.dispatch_link_checks.delay")
    def test_session_trigger_requires_csrf(self, enqueue):
        self.user.set_password("Monitor-password-91826")
        self.user.save()
        client = APIClient(enforce_csrf_checks=True)
        token = client.get("/api/accounts/auth/csrf/").cookies["csrftoken"].value
        response = client.post("/api/accounts/auth/login/", {
            "email": self.user.email, "password": "Monitor-password-91826",
        }, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post("/api/platforms/check-links-async/").status_code, 403)
        enqueue.assert_not_called()


class MonitorTaskTests(MonitorFixtures, TestCase):
    @override_settings(LINK_CHECK_BATCH_SIZE=2)
    @patch("apps.platforms.tasks.check_link_batch.delay")
    def test_dispatch_chunks_and_can_repeat_without_duplicate_batches(self, enqueue):
        for index in range(5):
            self.log(self.another_platform(index))
        run = models.LinkCheckRun.objects.create(mode="all", requested_by=self.user)
        tasks.dispatch_link_checks.run(run.pk)
        self.assertEqual([len(b.link_ids) for b in run.batches.order_by("pk")], [2, 2, 1])
        self.assertEqual(enqueue.call_count, 3)
        tasks.dispatch_link_checks.run(run.pk)
        self.assertEqual(run.batches.count(), 3)

    @patch("apps.platforms.tasks.check_link_batch.delay")
    def test_retry_dispatch_only_pending_current(self, enqueue):
        pending = self.log(count=4, checked=True)
        self.log(self.another_platform(1), count=5, checked=True)
        self.log(self.another_platform(2))
        run = models.LinkCheckRun.objects.create(mode="failed", requested_by=self.user)
        tasks.dispatch_link_checks.run(run.pk)
        self.assertEqual(run.batches.get().link_ids, [pending.pk])
        enqueue.assert_called_once()

    @patch("apps.platforms.tasks.notify_link_failures.delay")
    @patch("apps.platforms.services._validate_safe_http_url")
    @patch("apps.platforms.services._perform_link_check", return_value=(503, False))
    def test_batch_reuses_checker_and_redelivery_does_not_increment(self, check, _safe, notify):
        log = self.log(count=4, checked=True)
        run = models.LinkCheckRun.objects.create(mode="failed", requested_by=self.user, planned=True)
        batch = models.LinkCheckBatch.objects.create(run=run, link_ids=[log.pk])
        with self.captureOnCommitCallbacks(execute=True):
            tasks.check_link_batch.run(batch.pk)
        self.assertEqual(services.latest_platform_link_log(self.platform).fail_count, 5)
        self.assertEqual(notify.call_count, 1)
        with self.captureOnCommitCallbacks(execute=True):
            tasks.check_link_batch.run(batch.pk)
        check.assert_called_once()
        self.assertEqual(services.latest_platform_link_log(self.platform).fail_count, 5)

    @patch("apps.platforms.tasks.notify_link_failures.delay")
    def test_notification_waits_for_last_batch(self, notify):
        run = models.LinkCheckRun.objects.create(mode="all", requested_by=self.user, planned=True)
        first = models.LinkCheckBatch.objects.create(run=run, link_ids=[])
        second = models.LinkCheckBatch.objects.create(run=run, link_ids=[])
        with self.captureOnCommitCallbacks(execute=True):
            tasks.check_link_batch.run(first.pk)
        notify.assert_not_called()
        with self.captureOnCommitCallbacks(execute=True):
            tasks.check_link_batch.run(second.pk)
        notify.assert_called_once()

    @patch("apps.platforms.services.check_link_context")
    def test_invalid_or_replaced_batch_ids_are_skipped(self, checker):
        old = self.log(checked=True, count=4)
        self.log(url="https://8.8.8.8/new")
        run = models.LinkCheckRun.objects.create(mode="failed", requested_by=self.user, planned=True)
        batch = models.LinkCheckBatch.objects.create(run=run, link_ids=[old.pk])
        tasks.check_link_batch.run(batch.pk)
        checker.assert_not_called()


@override_settings(LINK_FAILURE_FRONTEND_URL="https://repository.example/admin/alertas")
class NotificationTests(MonitorFixtures, TestCase):
    def test_recipients_use_direct_and_preset_permissions_and_superadmin(self):
        direct = User.objects.create_user(email="direct@example.org", permissions=CHECK_PERMISSION)
        preset_user = User.objects.create_user(email="preset@example.org")
        preset = AccessPreset.objects.create(name="Enlaces", permissions=CHECK_PERMISSION, created_by=self.user)
        preset_user.presets.add(preset)
        User.objects.create_user(email="inactive@example.org", permissions=CHECK_PERMISSION, is_active=False)
        User.objects.create_user(email="denied@example.org")
        invalid = User.objects.create_user(email="invalid@example.org", permissions=CHECK_PERMISSION)
        User.objects.filter(pk=invalid.pk).update(email="")
        deleted = User.objects.create_user(email="deleted@example.org", permissions=CHECK_PERMISSION)
        deleted.deleted_at = timezone.now()
        deleted.save()
        self.assertSetEqual(set(notifications.failure_recipients()), {self.user.email, direct.email, preset_user.email})

    @patch("apps.platforms.notifications.email.send_email")
    def test_grouped_summary_exact_total_limit_and_all_marked(self, send):
        for index in range(13):
            self.log(self.another_platform(index), count=5, checked=True)
        self.assertEqual(notifications.notify_confirmed_failures(), 13)
        send.assert_called_once()
        html = send.call_args.args[2]
        self.assertIn("13 enlaces con fallos confirmados", html)
        self.assertEqual(html.count("<li>"), 10)
        self.assertIn("3 enlaces adicionales", html)
        self.assertIn("https://repository.example/admin/alertas?current=true&amp;failure_confirmed=true", html)
        self.assertEqual(send.call_args.kwargs["bcc"], [self.user.email])
        self.assertEqual(models.LinkCheckLog.objects.filter(failure_notified_at__isnull=False).count(), 13)
        self.assertEqual(notifications.notify_confirmed_failures(), 0)
        send.assert_called_once()

    @patch("apps.platforms.notifications.email.send_email")
    def test_small_summary_only_new_confirmed_failures_in_deterministic_order(self, send):
        confirmed = []
        for index in range(4):
            confirmed.append(self.log(self.another_platform(index), count=5, checked=True))
        for count in range(1, 5):
            self.log(self.another_platform(count + 10), count=count, checked=True)
        self.log(count=8, checked=True, failure_notified_at=timezone.now())
        self.assertEqual(notifications.notify_confirmed_failures(), 4)
        html = send.call_args.args[2]
        self.assertEqual(html.count("<li>"), 4)
        self.assertNotIn("adicionales", html)
        expected = sorted(confirmed, key=lambda log: (log.last_check, log.pk), reverse=True)
        positions = [html.index(escape_name.platform.name) for escape_name in expected]
        self.assertEqual(positions, sorted(positions))

    @patch("apps.platforms.notifications.email.send_email", side_effect=EmailDeliveryError("failed"))
    def test_delivery_error_does_not_mark(self, _send):
        log = self.log(count=5, checked=True)
        with self.assertRaises(EmailDeliveryError):
            notifications.notify_confirmed_failures()
        log.refresh_from_db()
        self.assertIsNone(log.failure_notified_at)

    @patch("apps.platforms.notifications.email.send_email")
    def test_overlapping_round_does_not_notify_partial_results(self, send):
        run = models.LinkCheckRun.objects.create(mode="all", requested_by=self.user, planned=True)
        batch = models.LinkCheckBatch.objects.create(run=run, link_ids=[])
        log = self.log(count=5, checked=True, check_batch=batch)
        self.assertEqual(notifications.notify_confirmed_failures(), 0)
        send.assert_not_called()
        run.finished_at = timezone.now()
        run.save(update_fields=["finished_at"])
        self.assertEqual(notifications.notify_confirmed_failures(), 1)
        log.refresh_from_db()
        self.assertIsNotNone(log.failure_notified_at)

    @patch("apps.platforms.notifications.email.send_email")
    def test_no_recipients_or_no_failures_does_not_send(self, send):
        self.assertEqual(notifications.notify_confirmed_failures(), 0)
        log = self.log(count=5, checked=True)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(notifications.notify_confirmed_failures(), 0)
        log.refresh_from_db()
        self.assertIsNone(log.failure_notified_at)
        send.assert_not_called()

    @override_settings(LINK_FAILURE_FRONTEND_URL="")
    @patch("apps.platforms.notifications.email.send_email")
    def test_missing_frontend_configuration_does_not_invent_url(self, send):
        self.log(count=5, checked=True)
        notifications.notify_confirmed_failures()
        html = send.call_args.args[2]
        self.assertNotIn("href=", html)
        self.assertIn("pendiente de configuración", html)


class MonitorConcurrencyTests(MonitorFixtures, TransactionTestCase):
    def in_thread(self, callback):
        close_old_connections()
        try:
            return callback()
        finally:
            connection.close()

    @skipUnlessDBFeature("has_select_for_update")
    @patch("apps.platforms.services._validate_safe_http_url")
    def test_concurrent_manual_checks_do_not_lose_increments_or_hold_http_transaction(self, _safe):
        self.log()
        barrier = Barrier(2)
        def http(url):
            self.assertFalse(connection.in_atomic_block)
            barrier.wait(timeout=10)
            return 503, False
        def check():
            return services.check_link_context(
                platform=models.Platform.objects.get(pk=self.platform.pk), user=self.user,
            ).fail_count
        with patch("apps.platforms.services._perform_link_check", side_effect=http):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.in_thread, check) for _ in range(2)]
                counts = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(counts), [1, 2])
        self.assertEqual(services.latest_platform_link_log(self.platform).fail_count, 2)

    @skipUnlessDBFeature("has_select_for_update")
    @patch("apps.platforms.notifications.email.send_email")
    def test_concurrent_notifiers_send_once(self, send):
        self.log(count=5, checked=True)
        barrier = Barrier(2)
        def notify():
            barrier.wait(timeout=10)
            return notifications.notify_confirmed_failures()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.in_thread, notify) for _ in range(2)]
            counts = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(counts), [0, 1])
        send.assert_called_once()
