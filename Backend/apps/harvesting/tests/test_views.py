from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.account.models import User
from apps.harvesting.models import (
    Harvest,
    HarvestJournal,
    HarvestRunRequest,
    Schedule,
    ScheduleEvent,
)
from apps.journal.models import Journal
from apps.platforms.models import Platform


class HarvestingViewsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.get(code=0)
        cls.user.permissions = {
            "harvesting": {
                "schedules": {
                    "view": True,
                    "create": True,
                    "update": True,
                    "delete": True,
                    "restore": True,
                    "run_due": True,
                },
                "events": {"view": True, "create": True},
                "harvests": {
                    "view": True,
                    "create": True,
                    "pause": True,
                    "resume": True,
                },
            },
        }
        cls.user.save(update_fields=["permissions"])
        cls.platform = Platform.objects.create(
            name="OpenAlex Test",
            base_api_url="https://api.openalex.org",
            is_harvestable=True,
            created_by=cls.user,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_schedule_crud_operations(self):
        payload = {
            "platforms": [self.platform.pk],
            "frequency": "weekly",
            "max_quantity": 250,
            "start_date": timezone.now().isoformat(),
        }
        response = self.client.post("/api/harvesting/schedules/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        schedule_id = response.data["id"]
        self.assertEqual(response.data["platforms"], [self.platform.pk])
        self.assertEqual(response.data["platform_names"], [self.platform.name])

        response = self.client.get(f"/api/harvesting/schedules/{schedule_id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["frequency"], "weekly")

        response = self.client.patch(
            f"/api/harvesting/schedules/{schedule_id}/",
            {"frequency": "monthly"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["frequency"], "monthly")

    def test_schedule_requires_initial_datetime(self):
        response = self.client.post(
            "/api/harvesting/schedules/",
            {
                "platforms": [self.platform.pk],
                "frequency": "daily",
                "max_quantity": 10,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_date", response.data)

    def test_schedule_rejects_non_harvestable_platform(self):
        self.platform.is_harvestable = False
        self.platform.save(update_fields=["is_harvestable"])

        response = self.client.post(
            "/api/harvesting/schedules/",
            {
                "platforms": [self.platform.pk],
                "frequency": "daily",
                "max_quantity": 10,
                "start_date": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("platforms", response.data)
        self.assertIn(self.platform.name, str(response.data["platforms"]))
        self.assertFalse(Schedule.objects.filter(platforms=self.platform).exists())

    @patch("apps.harvesting.views.services.run_scheduled_harvests", return_value=[])
    def test_run_due_rejects_anonymous_request(self, run_scheduled):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/harvesting/schedules/run-due/",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        run_scheduled.assert_not_called()

    @patch("apps.harvesting.views.services.run_scheduled_harvests", return_value=[])
    def test_run_due_replays_the_persisted_response_for_the_same_key(self, run_scheduled):
        headers = {"HTTP_IDEMPOTENCY_KEY": "harvesting_due:task-123"}

        first = self.client.post("/api/harvesting/schedules/run-due/", **headers)
        second = self.client.post("/api/harvesting/schedules/run-due/", **headers)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data, first.data)
        run_scheduled.assert_called_once_with()
        request = HarvestRunRequest.objects.get(idempotency_key="harvesting_due:task-123")
        self.assertEqual(request.state, HarvestRunRequest.State.COMPLETED)
        self.assertEqual(request.response_body, [])

    @patch(
        "apps.harvesting.views.services.run_scheduled_harvests",
        side_effect=RuntimeError("broker unavailable"),
    )
    def test_run_due_failure_releases_key_for_a_safe_retry(self, run_scheduled):
        response = self.client.post(
            "/api/harvesting/schedules/run-due/",
            HTTP_IDEMPOTENCY_KEY="retryable-key",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(HarvestRunRequest.objects.filter(idempotency_key="retryable-key").exists())
        run_scheduled.assert_called_once_with()

    @patch("apps.harvesting.views.services.run_scheduled_harvests")
    def test_run_due_reports_an_in_flight_duplicate_as_retryable(self, run_scheduled):
        HarvestRunRequest.objects.create(idempotency_key="in-flight-key")

        response = self.client.post(
            "/api/harvesting/schedules/run-due/",
            HTTP_IDEMPOTENCY_KEY="in-flight-key",
        )

        self.assertEqual(response.status_code, status.HTTP_425_TOO_EARLY)
        self.assertEqual(response["Retry-After"], "5")
        run_scheduled.assert_not_called()

    def test_harvest_and_event_endpoints_are_read_only(self):
        schedule = Schedule.objects.create(
            frequency=Schedule.Frequency.ONCE,
            max_quantity=100,
            start_date=timezone.now(),
            created_by=self.user,
        )
        schedule.platforms.add(self.platform)
        event = ScheduleEvent.objects.create(
            schedule=schedule,
            scheduled_for=timezone.now(),
            created_by=self.user,
        )
        harvest = Harvest.objects.create(
            platform=self.platform,
            schedule=schedule,
            event=event,
            max_quantity=100,
            created_by=self.user,
        )

        response = self.client.post(
            "/api/harvesting/harvests/",
            {"platform": self.platform.pk, "max_quantity": 100},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.get(f"/api/harvesting/harvests/{harvest.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["event"], event.pk)

        response = self.client.post(
            f"/api/harvesting/harvests/{harvest.pk}/execute/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.post(
            f"/api/harvesting/events/{event.pk}/",
            {"state": "completed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_harvest_journals_returns_only_journals_added_by_that_harvest(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            created_by=self.user,
        )
        added_journal = Journal.objects.create(
            issn="1234-5678",
            title="Revista nueva de cosecha",
            created_by=self.user,
        )
        updated_journal = Journal.objects.create(
            issn="2345-6789",
            title="Revista actualizada",
            created_by=self.user,
        )
        other_harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            state=Harvest.State.COMPLETED,
            created_by=self.user,
        )
        other_journal = Journal.objects.create(
            issn="3456-7890",
            title="Revista de otra cosecha",
            created_by=self.user,
        )
        HarvestJournal.objects.create(
            harvest=harvest,
            journal=added_journal,
            result=HarvestJournal.Result.ADDED,
        )
        HarvestJournal.objects.create(
            harvest=harvest,
            journal=updated_journal,
            result=HarvestJournal.Result.UPDATED,
        )
        HarvestJournal.objects.create(
            harvest=other_harvest,
            journal=other_journal,
            result=HarvestJournal.Result.ADDED,
        )

        response = self.client.get(
            f"/api/harvesting/harvests/{harvest.pk}/journals/",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(
            [journal["id"] for journal in response.data["results"]],
            [added_journal.pk],
        )
        self.assertEqual(
            response.data["results"][0]["title"],
            added_journal.title,
        )

    def test_harvest_journals_returns_404_for_unknown_harvest(self):
        response = self.client.get("/api/harvesting/harvests/999999/journals/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_harvest_journals_query_count_does_not_grow_per_journal(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=10,
            created_by=self.user,
        )
        journals = [
            Journal.objects.create(
                issn=f"9876-{index:04}",
                title=f"Revista rendimiento cosecha {index:02}",
                created_by=self.user,
            )
            for index in range(5)
        ]
        HarvestJournal.objects.bulk_create([
            HarvestJournal(
                harvest=harvest,
                journal=journal,
                result=HarvestJournal.Result.ADDED,
            )
            for journal in journals
        ])

        with CaptureQueriesContext(connection) as single:
            one = self.client.get(
                f"/api/harvesting/harvests/{harvest.pk}/journals/",
                {"page_size": 1},
            )
        with CaptureQueriesContext(connection) as multiple:
            five = self.client.get(
                f"/api/harvesting/harvests/{harvest.pk}/journals/",
                {"page_size": 5},
            )

        self.assertEqual(one.status_code, status.HTTP_200_OK)
        self.assertEqual(five.status_code, status.HTTP_200_OK)
        self.assertEqual(len(one.data["results"]), 1)
        self.assertEqual(len(five.data["results"]), 5)
        self.assertEqual(len(single), len(multiple))

    def test_pending_harvest_can_be_paused_and_queued_to_resume(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            api_cursor="openalex-cursor-123",
            created_by=self.user,
        )
        response = self.client.post(
            f"/api/harvesting/harvests/{harvest.pk}/pause/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], Harvest.State.PAUSED)

        with patch(
            "apps.harvesting.views.services.dispatch_harvest_to_worker",
            side_effect=lambda item: item,
        ) as dispatch_harvest:
            response = self.client.post(
                f"/api/harvesting/harvests/{harvest.pk}/resume/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["state"], Harvest.State.PENDING)
        self.assertEqual(dispatch_harvest.call_args.args[0].pk, harvest.pk)

    def test_running_harvest_pause_returns_accepted_while_page_finishes(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            state=Harvest.State.RUNNING,
            created_by=self.user,
        )
        response = self.client.post(
            f"/api/harvesting/harvests/{harvest.pk}/pause/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["state"], Harvest.State.PAUSING)

    def test_resume_rejects_harvest_that_is_not_paused(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            created_by=self.user,
        )
        response = self.client.post(
            f"/api/harvesting/harvests/{harvest.pk}/resume/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resume_replays_success_for_the_same_idempotency_key(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            state=Harvest.State.PAUSED,
            created_by=self.user,
        )
        headers = {"HTTP_IDEMPOTENCY_KEY": "resume-harvest-once"}
        with patch(
            "apps.harvesting.views.services.dispatch_harvest_to_worker",
            side_effect=lambda item: item,
        ) as dispatch:
            first = self.client.post(
                f"/api/harvesting/harvests/{harvest.pk}/resume/",
                **headers,
            )
            second = self.client.post(
                f"/api/harvesting/harvests/{harvest.pk}/resume/",
                **headers,
            )

        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.data, first.data)
        dispatch.assert_called_once()

    def test_resume_broker_failure_restores_paused_state_and_releases_key(self):
        harvest = Harvest.objects.create(
            platform=self.platform,
            max_quantity=100,
            state=Harvest.State.PAUSED,
            created_by=self.user,
        )
        with patch(
            "apps.harvesting.views.services.dispatch_harvest_to_worker",
            side_effect=RuntimeError("broker unavailable"),
        ):
            response = self.client.post(
                f"/api/harvesting/harvests/{harvest.pk}/resume/",
                HTTP_IDEMPOTENCY_KEY="resume-after-broker-failure",
            )

        harvest.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(harvest.state, Harvest.State.PAUSED)
        self.assertFalse(
            HarvestRunRequest.objects.filter(
                idempotency_key="resume-after-broker-failure",
            ).exists()
        )

    def test_filter_options_contract(self):
        response = self.client.get("/api/harvesting/schedules/filter-options/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data["openalex"]), {"country"})
        self.assertEqual(response.data["openalex"]["country"]["catalog_endpoint"], "/api/catalog/countries/")
        self.assertEqual(response.data["openalex"]["country"]["value_field"], "id")
        self.assertEqual(response.data["doaj"]["publisher"]["catalog_endpoint"], "/api/catalog/editorials/")
        self.assertEqual(response.data["doaj"]["language"]["catalog_endpoint"], "/api/catalog/languages/")
        self.assertIn("subject", response.data["doaj"])
        self.assertEqual(response.data["combination"], "AND")

    def test_harvest_list_filters_global_and_selected_streams(self):
        from apps.harvesting.selection import filter_key
        global_run = Harvest.objects.create(platform=self.platform, max_quantity=1, state="completed", created_by=self.user)
        filters = {"country_code": "CO"}
        selected = Harvest.objects.create(platform=self.platform, max_quantity=1, state="completed", selection_filters=filters, filter_key=filter_key(filters), created_by=self.user)
        for params, expected in [({"is_global": "true"}, global_run), ({"filter_key": selected.filter_key}, selected)]:
            response = self.client.get("/api/harvesting/harvests/", {"platform": self.platform.pk, **params})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual([row["id"] for row in response.data["results"]], [expected.pk])

    @patch("apps.harvesting.views.services.run_scheduled_harvests", return_value=[])
    def test_run_due_accepts_scheduler_token_with_specific_permission(self, run_scheduled):
        from django.test import override_settings
        service_user = User.objects.create_user(email="harvest-scheduler@example.org", permissions={"harvesting": {"schedules": {"run_due": True}}})
        self.client.force_authenticate(None)
        with override_settings(SCHEDULER_API_TOKEN="harvest-test-token", SCHEDULER_SERVICE_USER_ID=str(service_user.pk)):
            response = self.client.post("/api/harvesting/schedules/run-due/", HTTP_AUTHORIZATION="Bearer harvest-test-token")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            service_user.permissions = {}
            service_user.save(update_fields=["permissions"])
            denied = self.client.post("/api/harvesting/schedules/run-due/", HTTP_AUTHORIZATION="Bearer harvest-test-token")
            self.assertEqual(denied.status_code, status.HTTP_401_UNAUTHORIZED)
            invalid = self.client.post("/api/harvesting/schedules/run-due/", HTTP_AUTHORIZATION="Bearer wrong-token")
            self.assertEqual(invalid.status_code, status.HTTP_401_UNAUTHORIZED)
        run_scheduled.assert_called_once()

    def test_retired_openalex_filters_are_rejected(self):
        for key in ("is_oa", "is_in_doaj"):
            response = self.client.post("/api/harvesting/schedules/", {
                "platforms": [self.platform.pk], "max_quantity": 10,
                "start_date": timezone.now().isoformat(),
                "selection_filters": {key: True},
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("selection_filters", response.data)

    def test_country_catalog_id_can_be_used_as_selection(self):
        from apps.catalog.models import Country
        country = Country.objects.create(name="País del selector de cosecha", abbreviation="QZ", created_by=self.user)
        response = self.client.get("/api/catalog/countries/", {"search": country.name, "ordering": "name", "page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        listed_country = next(item for item in response.data["results"] if item["id"] == country.pk)
        response = self.client.post("/api/harvesting/schedules/", {
            "platforms": [self.platform.pk], "max_quantity": 10,
            "start_date": timezone.now().isoformat(),
            "selection_filters": {"country": listed_country["id"]},
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["selection_filters"], {"country": country.pk})

    def test_doaj_uses_ids_listed_by_editorial_and_language_endpoints(self):
        from apps.catalog.models import Editorial, Language
        editorial = Editorial.objects.create(name="Editorial para selector HTTP", created_by=self.user)
        language = Language.objects.get(abbreviation="es")
        platform = Platform.objects.create(name="DOAJ Catalog Views", base_api_url="https://doaj.org/oai", is_harvestable=True, created_by=self.user)
        selected = {}
        for field, endpoint, entry in (("publisher", "editorials", editorial), ("language", "languages", language)):
            response = self.client.get(f"/api/catalog/{endpoint}/", {"search": entry.name})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            selected[field] = next(row["id"] for row in response.data["results"] if row["id"] == entry.pk)
        payload = {"platforms": [platform.pk], "max_quantity": 10, "start_date": timezone.now().isoformat(), "selection_filters": selected}
        response = self.client.post("/api/harvesting/schedules/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["selection_filters"], selected)
        Editorial.objects.filter(pk=editorial.pk).update(deleted_at=timezone.now())
        response = self.client.post("/api/harvesting/schedules/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("publisher", response.data["selection_filters"])
