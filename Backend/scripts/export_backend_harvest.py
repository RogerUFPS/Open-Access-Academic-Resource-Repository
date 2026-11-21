#!/usr/bin/env python3
"""Export a harvest produced exclusively by the backend HTTP/worker flow.

This utility is intentionally separate from data migrations: migrations must
not contact remote services.  It creates a disposable SQLite database, calls
the schedule and run-due API actions through DRF, processes the resulting
Harvest with the same bounded worker step used by Celery, optionally calls the
platform check-links API action, and writes a deterministic JSON snapshot.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch


def configure_django(database_path: str) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["DJANGO_TESTING"] = "1"
    import config.settings as project_settings

    project_settings.DATABASES["default"]["NAME"] = database_path
    if "testserver" not in project_settings.ALLOWED_HOSTS:
        project_settings.ALLOWED_HOSTS.append("testserver")

    import django

    django.setup()


def bootstrap_database() -> None:
    from django.core.management import call_command

    # Bring every model used by the runtime code to its current schema.  A
    # targeted harvesting migration alone only follows minimum dependencies,
    # which can leave newer account/catalog columns unapplied.
    for app_label in (
        "contenttypes",
        "auth",
        "sessions",
        "auditlog",
        "account",
        "catalog",
        "journal",
    ):
        call_command("migrate", app_label, interactive=False, verbosity=0)
    call_command(
        "migrate", "platforms", "0011", interactive=False, verbosity=0
    )
    # Stop immediately before the old journal seed.  Its replacement is the
    # snapshot produced by this script.
    call_command("migrate", "harvesting", "0009", interactive=False, verbosity=0)


def create_doaj_platform(user):
    from apps.platforms.models import LinkCheckLog, Platform

    platform = Platform.objects.create(
        name="doaj",
        status=Platform.Status.PUBLICADO,
        base_api_url="https://doaj.org/oai",
        is_harvestable=True,
        start_period=date(2026, 11, 21),
        requires_registration=False,
        has_access_text=True,
        created_by=user,
    )
    LinkCheckLog.objects.create(
        platform=platform,
        url="https://doaj.org",
        is_active=False,
        last_check=None,
        created_by=user,
    )
    return platform


def run_harvest(platform, user, quantity: int, sequence: int):
    from django.utils import timezone
    from rest_framework.test import APIClient

    from apps.harvesting.models import Harvest
    from apps.harvesting.services import process_harvest_worker_step

    user.permissions = {
        "harvesting": {
            "schedules": {
                "view": True,
                "create": True,
                "run_due": True,
            },
            "harvests": {"view": True},
        },
        "platforms": {
            "platforms": {"view": True, "check_link": True},
        },
    }
    user.save(update_fields=["permissions"])

    client = APIClient()
    client.force_authenticate(user=user)
    schedule_response = client.post(
        "/api/harvesting/schedules/",
        {
            "platforms": [platform.pk],
            "frequency": "once",
            "max_quantity": quantity,
            "stop_after_minutes": None,
            "start_date": (timezone.now() - timezone.timedelta(minutes=1)).isoformat(),
        },
        format="json",
    )
    if schedule_response.status_code != 201:
        raise RuntimeError(
            f"Schedule endpoint returned {schedule_response.status_code}: "
            f"{schedule_response.data}"
        )

    # The production endpoint dispatches Celery.  In this disposable database
    # no independent worker can share the temporary SQLite connection, so only
    # broker publication is suppressed; the endpoint still creates the actual
    # ScheduleEvent and Harvest, and the real worker step handles every record.
    with patch(
        "apps.harvesting.services.dispatch_harvest_to_worker",
        side_effect=lambda harvest: harvest,
    ):
        run_response = client.post(
            "/api/harvesting/schedules/run-due/",
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"migration-doaj-{quantity}-{sequence}",
        )
    if run_response.status_code not in {200, 202}:
        raise RuntimeError(
            f"run-due endpoint returned {run_response.status_code}: "
            f"{run_response.data}"
        )

    harvest = Harvest.objects.get(schedule_id=schedule_response.data["id"])
    terminal = {
        Harvest.State.COMPLETED,
        Harvest.State.FAILED,
        Harvest.State.CANCELLED,
    }
    last_reported = -1
    while harvest.state not in terminal:
        process_harvest_worker_step(harvest.pk, harvest.worker_checkpoint)
        harvest.refresh_from_db()
        processed = (
            harvest.records_added
            + harvest.records_updated
            + harvest.records_failed
        )
        if processed // 25 != last_reported // 25:
            print(
                f"processed={processed} added={harvest.records_added} "
                f"updated={harvest.records_updated} failed={harvest.records_failed}",
                file=sys.stderr,
                flush=True,
            )
            last_reported = processed

    if harvest.state != Harvest.State.COMPLETED:
        raise RuntimeError(
            f"Harvest #{harvest.pk} ended as {harvest.state}: {harvest.error_message}"
        )
    return harvest, client


def check_links(platform, client) -> None:
    with patch(
        "apps.platforms.notifications.enqueue_pending_link_failure_notification"
    ):
        response = client.post(
            f"/api/platforms/{platform.pk}/check-links/",
            format="json",
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"check-links endpoint returned {response.status_code}: {response.data}"
        )
    print(
        f"links_checked={response.data['checked']} "
        f"available={response.data['available']} failed={response.data['failed']}",
        file=sys.stderr,
        flush=True,
    )


def verify_snapshot_links(snapshot: dict, platform, user) -> dict:
    from apps.journal.models import Journal, SharedJournalPlatform
    from apps.platforms.models import LinkCheckLog
    from rest_framework.test import APIClient

    user.permissions = {
        "platforms": {
            "platforms": {"view": True, "check_link": True},
        },
    }
    user.save(update_fields=["permissions"])

    latest_rows = {}
    for row in snapshot["journals"]:
        latest_rows[row["issn"]] = row
    journal_by_id = {}
    for index, row in enumerate(latest_rows.values(), start=1):
        # The snapshot rows already passed create_journal (including SSRF/DNS
        # validation) during the real harvest.  Reconstruct only the minimum
        # link context here; check-links performs its own current safety check.
        journal = Journal.objects.create(
            issn=row["issn"],
            title=row["title"],
            active=False,
            created_by=user,
        )
        journal_platform = SharedJournalPlatform.objects.create(
            journal=journal,
            platform=platform,
            created_by=user,
        )
        LinkCheckLog.objects.create(
            platform=platform,
            journal_platform=journal_platform,
            url=row["url"],
            is_active=False,
            last_check=None,
            created_by=user,
        )
        journal_by_id[journal.pk] = row["issn"]
        if index % 25 == 0:
            print(
                f"urls_registered={index}", file=sys.stderr, flush=True
            )

    client = APIClient()
    client.force_authenticate(user=user)
    with patch(
        "apps.platforms.notifications.enqueue_pending_link_failure_notification"
    ):
        response = client.post(
            f"/api/platforms/{platform.pk}/check-links/",
            format="json",
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"check-links endpoint returned {response.status_code}: {response.data}"
        )

    result_by_issn = {
        journal_by_id[result["journal"]]: result
        for result in response.data["results"]
        if result["type"] == "journal" and result["journal"] in journal_by_id
    }
    for row in snapshot["journals"]:
        result = result_by_issn[row["issn"]]
        row["url_http_status"] = result["http_status_code"]
        row["url_available"] = result["is_active"]
        row["url_checked_at"] = result["last_check"]

    snapshot["link_check"] = {
        "checked": response.data["checked"],
        "available": response.data["available"],
        "failed": response.data["failed"],
    }
    print(
        f"links_checked={response.data['checked']} "
        f"available={response.data['available']} failed={response.data['failed']}",
        file=sys.stderr,
        flush=True,
    )
    return snapshot


def iso(value):
    return value.isoformat() if value is not None else None


def harvest_snapshot(harvest) -> dict:
    return {
        "state": harvest.state,
        "max_quantity": harvest.max_quantity,
        "records_added": harvest.records_added,
        "records_updated": harvest.records_updated,
        "records_failed": harvest.records_failed,
        "api_cursor": harvest.api_cursor,
        "api_marker": harvest.api_marker,
        "api_page": harvest.api_page,
        "worker_checkpoint": harvest.worker_checkpoint,
        "worker_elapsed_milliseconds": harvest.worker_elapsed_milliseconds,
        "elapsed_seconds": harvest.elapsed_seconds,
        "started_at": iso(harvest.started_at),
        "finished_at": iso(harvest.finished_at),
    }


def build_snapshot(harvests) -> dict:
    from apps.harvesting.models import HarvestJournal
    from apps.platforms.services import latest_journal_link_log

    final_harvest = harvests[-1]
    rows = []
    records = HarvestJournal.objects.filter(
        harvest__in=harvests
    ).select_related("harvest", "journal__editorial").order_by("pk")
    for record in records:
        journal = record.journal
        platform_link = journal.platform_links.get(
            platform_id=final_harvest.platform_id
        )
        link = latest_journal_link_log(platform_link)
        rows.append(
            {
                "harvest_sequence": harvests.index(record.harvest) + 1,
                "result": record.result,
                "issn": journal.issn,
                "title": journal.title,
                "editorial": journal.editorial.name if journal.editorial_id else None,
                "publication_date": iso(journal.publication_date),
                "has_apc": journal.has_apc,
                "languages": sorted(
                    journal.language_links.values_list(
                        "language__abbreviation", flat=True
                    )
                ),
                "countries": sorted(
                    journal.country_links.values_list(
                        "country__abbreviation", flat=True
                    )
                ),
                "material_types": sorted(
                    journal.material_type_links.values_list(
                        "material_type__name", flat=True
                    )
                ),
                "academic_programs": sorted(
                    journal.academic_program_links.values_list(
                        "academic_program__name", flat=True
                    )
                ),
                "licenses": sorted(
                    journal.license_links.values_list("license__name", flat=True)
                ),
                "has_full_text": platform_link.has_full_text,
                "url": link.url if link else None,
                "url_http_status": link.http_status_code if link else None,
                "url_available": link.is_active if link and link.last_check else None,
                "url_checked_at": iso(link.last_check) if link else None,
            }
        )

    return {
        "provenance": {
            "schedule_endpoint": "/api/harvesting/schedules/",
            "run_endpoint": "/api/harvesting/schedules/run-due/",
            "link_check_endpoint": (
                f"/api/platforms/{final_harvest.platform_id}/check-links/"
            ),
            "provider_endpoint": final_harvest.platform.base_api_url,
            "worker": "apps.harvesting.services.process_harvest_worker_step",
        },
        "harvests": [harvest_snapshot(harvest) for harvest in harvests],
        "journals": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quantity", type=int, default=650)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-links", action="store_true")
    parser.add_argument(
        "--verify-snapshot",
        type=Path,
        help="Verify URLs from an existing endpoint-produced snapshot.",
    )
    args = parser.parse_args()

    descriptor, database_path = tempfile.mkstemp(
        prefix="backend-harvest-", suffix=".sqlite3"
    )
    os.close(descriptor)
    try:
        configure_django(database_path)
        bootstrap_database()

        from apps.account.models import User

        user = User.objects.get(code=0)
        platform = create_doaj_platform(user)
        if args.verify_snapshot:
            snapshot = json.loads(args.verify_snapshot.read_text(encoding="utf-8"))
            snapshot = verify_snapshot_links(snapshot, platform, user)
            args.output.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            return

        harvests = []
        client = None
        remaining = args.quantity
        while remaining:
            harvest, client = run_harvest(
                platform,
                user,
                remaining,
                len(harvests) + 1,
            )
            harvests.append(harvest)
            if harvest.records_added <= 0:
                raise RuntimeError(
                    "El endpoint no produjo nuevas revistas; no es posible "
                    f"completar las {args.quantity} solicitadas."
                )
            remaining -= harvest.records_added
            print(
                f"valid_journals={args.quantity - remaining} remaining={remaining}",
                file=sys.stderr,
                flush=True,
            )
        if args.check_links:
            check_links(platform, client)
        snapshot = build_snapshot(harvests)
        args.output.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        Path(database_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
