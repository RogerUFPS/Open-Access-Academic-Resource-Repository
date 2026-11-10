import logging
import random

import httpx
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

JOBS = {
    "harvesting_due": "/api/harvesting/schedules/run-due/",
    "check_links": "/api/platforms/check-links-async/",
    "check_failed_links": "/api/platforms/check-failed-links/",
}
RETRYABLE_STATUSES = {408, 425, 429}


@shared_task(
    bind=True,
    max_retries=5,
    acks_late=True,
    soft_time_limit=75,
    time_limit=90,
    name="apps.scheduler.tasks.dispatch_http_job",
)
def dispatch_http_job(self, job):
    path = JOBS[job]
    endpoint = f"{settings.SCHEDULER_API_URL.rstrip('/')}{path}"
    headers = {"Idempotency-Key": f"{job}:{self.request.id}"}
    scheduler_token = settings.SCHEDULER_API_TOKEN.strip()
    if scheduler_token:
        headers["Authorization"] = f"Bearer {scheduler_token}"
    elif job != "harvesting_due":
        raise RuntimeError(f"SCHEDULER_API_TOKEN is required for scheduler job {job}.")
    timeout = httpx.Timeout(connect=3, read=60, write=5, pool=5)

    try:
        response = httpx.post(endpoint, headers=headers, timeout=timeout)
    except httpx.TransportError as exc:
        return _retry(self, job, exc)

    if response.status_code in RETRYABLE_STATUSES or response.status_code >= 500:
        return _retry(
            self,
            job,
            RuntimeError(f"Retryable scheduler response: HTTP {response.status_code}"),
            status_code=response.status_code,
        )
    if response.status_code not in {200, 202}:
        response.raise_for_status()
        raise RuntimeError(f"Unexpected scheduler response: HTTP {response.status_code}")

    logger.info(
        "Scheduler dispatch accepted job=%s status=%s task_id=%s",
        job,
        response.status_code,
        self.request.id,
    )
    return {"job": job, "status_code": response.status_code}


def _retry(task, job, error, *, status_code=None):
    retries = task.request.retries
    countdown = min(300, 10 * (2**retries)) + random.uniform(0, 5)
    logger.warning(
        "Scheduler dispatch failed job=%s status=%s retry=%s error_type=%s",
        job,
        status_code,
        retries,
        type(error).__name__,
    )
    raise task.retry(exc=error, countdown=countdown)
