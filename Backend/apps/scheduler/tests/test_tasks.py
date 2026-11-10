from unittest.mock import Mock, patch

import httpx
from celery.exceptions import Retry
from django.test import SimpleTestCase, override_settings

from apps.scheduler.tasks import dispatch_http_job
from project.celery import app


@override_settings(
    SCHEDULER_API_URL="http://backend:8000/",
    SCHEDULER_API_TOKEN="test-secret",
)
class DispatchHTTPJobTests(SimpleTestCase):
    def test_accepts_http_200_and_202(self):
        for status_code in (200, 202):
            with self.subTest(status_code=status_code):
                response = Mock(status_code=status_code)
                with patch("apps.scheduler.tasks.httpx.post", return_value=response) as post:
                    result = dispatch_http_job.apply(
                        kwargs={"job": "check_links"},
                        task_id="dispatch-1",
                        throw=True,
                    ).get()
                self.assertEqual(result["status_code"], status_code)
                self.assertEqual(
                    post.call_args.kwargs["headers"]["Idempotency-Key"],
                    "check_links:dispatch-1",
                )
                self.assertEqual(
                    post.call_args.args[0],
                    "http://backend:8000/api/platforms/check-links-async/",
                )

    def test_retries_http_408_425_429_and_5xx(self):
        for status_code in (408, 425, 429, 500, 503):
            with self.subTest(status_code=status_code):
                with patch(
                    "apps.scheduler.tasks.httpx.post",
                    return_value=Mock(status_code=status_code),
                ) as post:
                    with patch.object(
                        dispatch_http_job,
                        "retry",
                        side_effect=Retry("retry"),
                    ) as retry:
                        with self.assertRaises(Retry):
                            dispatch_http_job.run("check_failed_links")
                self.assertEqual(post.call_count, 1)
                self.assertGreaterEqual(retry.call_args.kwargs["countdown"], 10)
                self.assertLessEqual(retry.call_args.kwargs["countdown"], 15)

    def test_permanent_4xx_fails_without_retry(self):
        response = Mock(status_code=403)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "forbidden",
            request=httpx.Request("POST", "http://backend"),
            response=httpx.Response(403),
        )
        with patch("apps.scheduler.tasks.httpx.post", return_value=response):
            with patch.object(dispatch_http_job, "retry") as retry:
                with self.assertRaises(httpx.HTTPStatusError):
                    dispatch_http_job.run("check_links")
        retry.assert_not_called()

    def test_transport_timeout_retries_with_backoff(self):
        for error in (
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("request timed out"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch("apps.scheduler.tasks.httpx.post", side_effect=error):
                    with patch.object(
                        dispatch_http_job,
                        "retry",
                        side_effect=Retry("retry"),
                    ) as retry:
                        with self.assertRaises(Retry):
                            dispatch_http_job.run("harvesting_due")
                self.assertGreaterEqual(retry.call_args.kwargs["countdown"], 10)
                self.assertLessEqual(retry.call_args.kwargs["countdown"], 15)

    def test_retry_exhaustion_fails_task(self):
        with patch("apps.scheduler.tasks.httpx.post", return_value=Mock(status_code=503)) as post:
            with self.assertRaises(RuntimeError):
                dispatch_http_job.apply(
                    kwargs={"job": "check_links"},
                    task_id="exhausted-dispatch",
                    retries=dispatch_http_job.max_retries,
                    throw=True,
                )
        self.assertEqual(post.call_count, 1)


class BeatScheduleTests(SimpleTestCase):
    def test_schedule_has_three_utc_crontabs_and_utc_next_runs(self):
        self.assertTrue(app.conf.enable_utc)
        self.assertEqual(app.conf.timezone, "UTC")
        schedule = app.conf.beat_schedule
        self.assertEqual(
            set(schedule),
            {
                "harvesting-run-due-every-5m",
                "platforms-check-links-every-4h",
                "platforms-check-failed-links-every-15m",
            },
        )
        expected = {
            "harvesting-run-due-every-5m": ("*/5", "*"),
            "platforms-check-links-every-4h": (0, "*/4"),
            "platforms-check-failed-links-every-15m": ("*/15", "*"),
        }
        for name, (minute, hour) in expected.items():
            with self.subTest(job=name):
                crontab = schedule[name]["schedule"]
                self.assertEqual(crontab._orig_minute, minute)
                self.assertEqual(crontab._orig_hour, hour)
                next_run = app.now() + crontab.remaining_estimate(app.now())
                zone = getattr(next_run.tzinfo, "zone", None) or next_run.tzinfo.key
                self.assertEqual(zone, "UTC")
