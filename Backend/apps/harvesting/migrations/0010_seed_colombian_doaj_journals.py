"""Replay the 650-journal DOAJ harvest produced by the backend endpoints.

The compressed snapshot was generated through the schedule/run-due endpoints,
the real bounded worker and the platform check-links endpoint.  Migrations do
not contact remote services; they replay that endpoint-produced result exactly.
No country or provider-side search filter was used.
"""

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path

from django.db import migrations


DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "migration_data"
    / "doaj_backend_harvest_650.json.gz"
)
DOAJ_URL = "https://doaj.org"
DOAJ_OAI_URL = "https://doaj.org/oai"
DATA_SHA256 = (
    "26635de6374e0467b1f032419e2e3646196407c5a24198e418b08dbc26ddc795"
)


def _timestamp(value):
    return datetime.fromisoformat(value) if value else None


def _snapshot():
    with gzip.open(DATA_FILE, "rb") as stream:
        payload = stream.read()
    if hashlib.sha256(payload).hexdigest() != DATA_SHA256:
        raise RuntimeError("La instantánea DOAJ no coincide con su checksum.")
    return json.loads(payload)


def _restore_named(model, name, user_id):
    value = model.objects.filter(name__iexact=name).first()
    if value is None:
        return model.objects.create(name=name, created_by_id=user_id)
    model.objects.filter(pk=value.pk).update(
        deleted_at=None,
        deleted_by_id=None,
        delete_explanation=None,
    )
    return value


def _active_relation(model, *, user_id, defaults=None, **lookup):
    relation = model.objects.filter(**lookup).first()
    values = {
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
    }
    if defaults:
        values.update(defaults)
    if relation is None:
        return model.objects.create(
            **lookup,
            created_by_id=user_id,
            **values,
        )
    model.objects.filter(pk=relation.pk).update(**values)
    return relation


def seed_doaj_backend_harvest(apps, schema_editor):
    User = apps.get_model("account", "User")
    Editorial = apps.get_model("catalog", "Editorial")
    Language = apps.get_model("catalog", "Language")
    Platform = apps.get_model("platforms", "Platform")
    LinkCheckLog = apps.get_model("platforms", "LinkCheckLog")
    Journal = apps.get_model("journal", "Journal")
    License = apps.get_model("journal", "License")
    JournalLanguage = apps.get_model("journal", "SharedJournalLanguage")
    JournalLicense = apps.get_model("journal", "SharedJournalLicense")
    JournalPlatform = apps.get_model("journal", "SharedJournalPlatform")
    Schedule = apps.get_model("harvesting", "Schedule")
    ScheduleEvent = apps.get_model("harvesting", "ScheduleEvent")
    Harvest = apps.get_model("harvesting", "Harvest")
    HarvestJournal = apps.get_model("harvesting", "HarvestJournal")

    data = _snapshot()
    rows = data["journals"]
    harvest_rows = data["harvests"]
    if len({row["issn"].upper() for row in rows}) != 650:
        raise RuntimeError("La instantánea DOAJ no contiene 650 ISSN únicos.")
    if sum(row["result"] == "added" for row in rows) != 650:
        raise RuntimeError("La instantánea DOAJ no contiene 650 altas.")

    user = User.objects.filter(code=0).first()
    if user is None:
        raise RuntimeError(
            "No se puede reproducir la cosecha DOAJ: falta el usuario code=0."
        )

    platform = Platform.objects.filter(name__iexact="DOAJ").first()
    platform_values = {
        "status": "borrador",
        "base_api_url": DOAJ_OAI_URL,
        "is_harvestable": True,
        "requires_registration": False,
        "has_access_text": True,
        "validated_by_id": None,
        "validated_at": None,
        "deleted_at": None,
        "deleted_by_id": None,
        "delete_explanation": None,
    }
    if platform is None:
        platform = Platform.objects.create(
            name="doaj",
            start_period=_timestamp(harvest_rows[0]["started_at"]).date(),
            url_image=None,
            url_image_thumbnail=None,
            created_by_id=user.pk,
            **platform_values,
        )
    else:
        Platform.objects.filter(pk=platform.pk).update(**platform_values)
        platform.refresh_from_db()

    harvests = []
    for source in harvest_rows:
        started_at = _timestamp(source["started_at"])
        finished_at = _timestamp(source["finished_at"])
        schedule = Schedule.objects.create(
            frequency="once",
            max_quantity=source["max_quantity"],
            stop_after_minutes=None,
            start_date=started_at,
            created_by_id=user.pk,
        )
        schedule.platforms.add(platform)
        event = ScheduleEvent.objects.create(
            schedule_id=schedule.pk,
            scheduled_for=started_at,
            state="completed",
            started_at=started_at,
            finished_at=finished_at,
            created_by_id=user.pk,
        )
        harvest = Harvest.objects.create(
            platform_id=platform.pk,
            schedule_id=schedule.pk,
            event_id=event.pk,
            api_cursor=source["api_cursor"],
            api_marker=source["api_marker"],
            api_page=source["api_page"],
            worker_checkpoint=source["worker_checkpoint"],
            worker_elapsed_milliseconds=source[
                "worker_elapsed_milliseconds"
            ],
            worker_dispatched_at=finished_at,
            max_quantity=source["max_quantity"],
            stop_after_minutes=None,
            state=source["state"],
            records_added=source["records_added"],
            records_updated=source["records_updated"],
            records_failed=source["records_failed"],
            elapsed_seconds=source["elapsed_seconds"],
            started_at=started_at,
            finished_at=finished_at,
            error_message=None,
            created_by_id=user.pk,
        )
        for model, pk in (
            (Schedule, schedule.pk),
            (ScheduleEvent, event.pk),
            (Harvest, harvest.pk),
        ):
            model.objects.filter(pk=pk).update(created_at=started_at)
        harvests.append(harvest)

    journal_platform_by_issn = {}
    first_seen_at = {}
    for row in rows:
        harvested_at = _timestamp(
            harvest_rows[row["harvest_sequence"] - 1]["finished_at"]
        )
        editorial = _restore_named(Editorial, row["editorial"], user.pk)
        journal = Journal.objects.filter(issn__iexact=row["issn"]).first()
        values = {
            "title": row["title"],
            "editorial_id": editorial.pk,
            "has_apc": row["has_apc"],
            "active": False,
            "publication_date": (
                _timestamp(row["publication_date"]).date()
                if row["publication_date"]
                else None
            ),
            "url_image": None,
            "url_image_thumbnail": None,
            "validated_by_id": None,
            "validated_at": None,
            "fetched_at": harvested_at,
            "deleted_at": None,
            "deleted_by_id": None,
            "delete_explanation": None,
        }
        if journal is None:
            journal = Journal.objects.create(
                issn=row["issn"],
                created_by_id=user.pk,
                **values,
            )
            Journal.objects.filter(pk=journal.pk).update(
                created_at=harvested_at
            )
            first_seen_at[row["issn"].upper()] = harvested_at
        else:
            values.update(
                updated_by_id=user.pk,
                updated_at=harvested_at,
            )
            Journal.objects.filter(pk=journal.pk).update(**values)
            journal.refresh_from_db()
            first_seen_at.setdefault(row["issn"].upper(), harvested_at)

        for code in row["languages"]:
            language = Language.objects.filter(
                abbreviation__iexact=code
            ).first()
            if language is None:
                raise RuntimeError(
                    f"Falta el idioma {code!r} requerido por {row['issn']}."
                )
            _active_relation(
                JournalLanguage,
                user_id=user.pk,
                journal_id=journal.pk,
                language_id=language.pk,
            )

        for license_name in row["licenses"]:
            license_obj = _restore_named(License, license_name, user.pk)
            _active_relation(
                JournalLicense,
                user_id=user.pk,
                journal_id=journal.pk,
                license_id=license_obj.pk,
            )

        journal_platform = _active_relation(
            JournalPlatform,
            user_id=user.pk,
            defaults={
                "start_period": platform.start_period,
                "finish_period": None,
                "has_full_text": row["has_full_text"],
            },
            journal_id=journal.pk,
            platform_id=platform.pk,
        )
        journal_platform_by_issn[row["issn"].upper()] = journal_platform
        harvest_link = HarvestJournal.objects.create(
            harvest_id=harvests[row["harvest_sequence"] - 1].pk,
            journal_id=journal.pk,
            result=row["result"],
        )
        HarvestJournal.objects.filter(pk=harvest_link.pk).update(
            created_at=harvested_at
        )

    latest_rows = {}
    for row in rows:
        latest_rows[row["issn"].upper()] = row
    for issn, row in latest_rows.items():
        initial_at = first_seen_at[issn]
        journal_platform = journal_platform_by_issn[issn]
        initial_log = LinkCheckLog.objects.create(
            platform_id=platform.pk,
            journal_platform_id=journal_platform.pk,
            url=row["url"],
            fail_count=0,
            http_status_code=None,
            is_active=False,
            last_check=None,
            created_by_id=user.pk,
        )
        LinkCheckLog.objects.filter(pk=initial_log.pk).update(
            created_at=initial_at
        )
        checked_at = _timestamp(row["url_checked_at"])
        checked_log = LinkCheckLog.objects.create(
            platform_id=platform.pk,
            journal_platform_id=journal_platform.pk,
            url=row["url"],
            fail_count=0 if row["url_available"] else 1,
            http_status_code=row["url_http_status"],
            is_active=row["url_available"],
            last_check=checked_at,
            created_by_id=user.pk,
        )
        LinkCheckLog.objects.filter(pk=checked_log.pk).update(
            created_at=checked_at
        )

    platform_checked_at = max(
        _timestamp(row["url_checked_at"]) for row in latest_rows.values()
    )
    initial_platform_log = LinkCheckLog.objects.create(
        platform_id=platform.pk,
        journal_platform_id=None,
        url=DOAJ_URL,
        fail_count=0,
        http_status_code=None,
        is_active=False,
        last_check=None,
        created_by_id=user.pk,
    )
    LinkCheckLog.objects.filter(pk=initial_platform_log.pk).update(
        created_at=_timestamp(harvest_rows[0]["started_at"])
    )
    platform_log = LinkCheckLog.objects.create(
        platform_id=platform.pk,
        journal_platform_id=None,
        url=DOAJ_URL,
        fail_count=0,
        http_status_code=403,
        is_active=True,
        last_check=platform_checked_at,
        created_by_id=user.pk,
    )
    LinkCheckLog.objects.filter(pk=platform_log.pk).update(
        created_at=platform_checked_at
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0005_single_superadmin_handoff"),
        ("catalog", "0008_seed_countries"),
        ("journal", "0005_journal_url_image_thumbnail"),
        ("platforms", "0011_linkcheckrequest"),
        ("harvesting", "0009_harvestrunrequest"),
    ]

    operations = [
        migrations.RunPython(
            seed_doaj_backend_harvest,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
