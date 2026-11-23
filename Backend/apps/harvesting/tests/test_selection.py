import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.account.models import User
from apps.catalog.models import Country, Editorial, Language
from apps.platforms.models import Platform
from apps.harvesting.models import Harvest, HarvestSourceRecord
from apps.harvesting.selection import normalize_filters, resolve_filters, filter_key, openalex_filter
from apps.harvesting.serializers import ScheduleSerializer
from apps.harvesting.services import (
    get_latest_harvest_progress, process_harvest_worker_step,
    _import_unless_unchanged, _validate_openalex_endpoint, DoajHarvester,
    run_scheduled_harvests,
)


class SelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.get(code=0)
        cls.country = Country.objects.get(abbreviation="CO")
        cls.language = Language.objects.get(abbreviation="es")
        cls.editorial = Editorial.objects.create(name="Editorial de selección", created_by=cls.user)
        cls.platform = Platform.objects.create(name="OpenAlex Selection Tests", base_api_url="https://api.openalex.org", is_harvestable=True, created_by=cls.user)

    def harvest(self, **kwargs):
        if "selection_filters" in kwargs and "resolved_filters" not in kwargs:
            kwargs["resolved_filters"] = kwargs["selection_filters"]
        return Harvest.objects.create(platform=self.platform, max_quantity=2, created_by=self.user, **kwargs)

    def test_country_normalization(self):
        filters = normalize_filters({"country": self.country.pk})
        self.assertEqual(filters, {"country": self.country.pk})
        resolved = resolve_filters(filters)
        self.assertEqual(resolved, {"country_code": "CO"})
        self.assertEqual(openalex_filter(resolved), "type:journal,country_code:CO")
        self.assertEqual(filter_key({"country_code": "co"}), filter_key(resolved))
        self.assertEqual(filter_key({}), "")

    def test_reject_raw_query_and_invalid_values(self):
        for value in [{"filter": "x"}, {"country_code": "CO"}, {"country": False}, {"country": "1"}, {"language": "es"}, {"publisher": "Editorial"}, {"is_oa": True}, {"is_in_doaj": False}, [], {"subject": " "}]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_filters(value)

    def test_incompatible_provider_and_partial_updates(self):
        data = {"platforms": [self.platform.pk], "max_quantity": 10, "start_date": timezone.now(), "selection_filters": {"language": self.language.pk}}
        serializer = ScheduleSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        data["selection_filters"] = {"country": self.country.pk}
        serializer = ScheduleSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        schedule = serializer.save(created_by=self.user)
        serializer = ScheduleSerializer(schedule, data={"max_quantity": 20}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save().selection_filters, {"country": self.country.pk})

    def test_global_and_filtered_progress_are_independent(self):
        self.harvest(state="completed", api_cursor="global", api_page='{"results": []}', api_marker=1)
        filters = {"country_code": "CO"}
        self.harvest(state="completed", selection_filters=filters, filter_key=filter_key(filters), api_cursor="colombia", source_exhausted=True)
        self.assertEqual(get_latest_harvest_progress(self.platform)["api_cursor"], "global")
        self.assertEqual(get_latest_harvest_progress(self.platform)["api_marker"], 1)
        self.assertTrue(get_latest_harvest_progress(self.platform, filters)["source_exhausted"])
        self.assertEqual(get_latest_harvest_progress(self.platform, {"country_code": "US"})["api_cursor"], "*")

    @patch("apps.harvesting.services.OpenAlexHarvester._get_client")
    @patch("apps.harvesting.services.OpenAlexHarvester._process_single_source", return_value=True)
    def test_batch_checkpoint_cached_and_stale_delivery(self, process, get_client):
        client = MagicMock()
        client.get.return_value.status_code = 200
        client.get.return_value.json.return_value = {"results": [{"id": "S1"}, {"id": "S2"}], "meta": {"next_cursor": "next"}}
        get_client.return_value = client
        harvest = self.harvest(api_cursor="*")
        process_harvest_worker_step(harvest.pk, 0)
        harvest.refresh_from_db()
        self.assertEqual(harvest.api_marker, 1)
        self.assertTrue(harvest.api_page)
        process_harvest_worker_step(harvest.pk, 0)
        self.assertEqual(process.call_count, 1)
        process_harvest_worker_step(harvest.pk, 1)
        harvest.refresh_from_db()
        self.assertEqual(harvest.api_cursor, "next")
        self.assertEqual(harvest.api_page, "")
        self.assertEqual(client.get.call_count, 1)
        self.assertEqual(client.get.call_args.kwargs["params"]["per-page"], 100)
        self.assertEqual(HarvestSourceRecord.objects.filter(platform=self.platform).count(), 2)

    def test_unchanged_record_skipped_but_changed_record_imported(self):
        harvest = self.harvest()
        process = MagicMock(return_value=True)
        _import_unless_unchanged(harvest, "S1", "original", process)
        _import_unless_unchanged(harvest, "S1", "original", process)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(harvest.records_skipped, 1)
        _import_unless_unchanged(harvest, "S1", "changed", process)
        self.assertEqual(process.call_count, 2)

    @patch("apps.harvesting.services.OpenAlexHarvester._get_client")
    def test_exhausted_stream_does_not_restart(self, client):
        harvest = self.harvest(source_exhausted=True)
        process_harvest_worker_step(harvest.pk, 0)
        client.assert_not_called()
        harvest.refresh_from_db()
        self.assertEqual(harvest.state, "completed")

    def test_provider_urls_and_xml_declarations(self):
        for url in ["http://api.openalex.org", "https://api.openalex.org.evil.test", "https://localhost", "https://api.openalex.org?api_key=x"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                _validate_openalex_endpoint(url)
        with self.assertRaises(RuntimeError):
            DoajHarvester._records_and_token('<!DOCTYPE x [<!ENTITY a "x">]><x/>')

    @patch("apps.harvesting.services.DoajHarvester._process_record", return_value=True)
    def test_doaj_filters_skip_and_advance_without_importing(self, process):
        from apps.harvesting.services import _worker_doaj_step
        xml = '''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/"><ListRecords><record><header><identifier>oai:test</identifier></header><metadata><oai_dc:dc><dc:language>en</dc:language><dc:subject>Medicine</dc:subject></oai_dc:dc></metadata></record><resumptionToken>next</resumptionToken></ListRecords></OAI-PMH>'''
        platform = Platform.objects.create(name="DOAJ Selection Tests", base_api_url="https://doaj.org/oai", is_harvestable=True, created_by=self.user)
        harvest = Harvest.objects.create(platform=platform, max_quantity=10, created_by=self.user, selection_filters={"language": self.language.pk}, resolved_filters={"language": "es"}, api_page=xml)
        with patch("apps.harvesting.services.DoajHarvester._get_client") as client:
            _worker_doaj_step(harvest, self.user)
        process.assert_not_called()
        client.return_value.get.assert_not_called()
        self.assertEqual(harvest.records_skipped, 1)
        self.assertEqual(harvest.api_cursor, "next")
        self.assertEqual(harvest.api_page, "")

    def test_failed_import_is_not_marked_seen(self):
        harvest = self.harvest()
        def failed():
            harvest.records_failed += 1
            return True
        _import_unless_unchanged(harvest, "S-failed", "payload", failed)
        self.assertFalse(HarvestSourceRecord.objects.filter(platform=self.platform).exists())

    def test_deduplication_is_shared_between_filter_streams(self):
        global_run = self.harvest(state="completed")
        process = MagicMock(return_value=True)
        _import_unless_unchanged(global_run, "S-overlap", "payload", process)
        filtered_run = self.harvest(selection_filters={"country_code": "CO"}, filter_key=filter_key({"country_code": "CO"}))
        _import_unless_unchanged(filtered_run, "S-overlap", "payload", process)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(filtered_run.records_skipped, 1)

    def test_irrelevant_statistics_do_not_trigger_updates(self):
        from apps.harvesting.services import _openalex_payload
        original = {"id": "S1", "display_name": "Journal", "cited_by_count": 1}
        changed = {**original, "cited_by_count": 500}
        self.assertEqual(_openalex_payload(original), _openalex_payload(changed))
        self.assertNotEqual(_openalex_payload(original), _openalex_payload({**original, "display_name": "New title"}))

    @patch("apps.harvesting.services.dispatch_harvest_to_worker", side_effect=lambda harvest: harvest)
    def test_scheduler_snapshots_selection_and_resumes_its_page(self, dispatch):
        from apps.harvesting.models import Schedule
        from apps.harvesting.services import run_scheduled_harvests
        filters = {"country_code": "CO"}
        previous = self.harvest(state="completed", selection_filters=filters, filter_key=filter_key(filters), api_cursor="co-cursor", api_page=json.dumps({"results": [{"id": "S1"}, {"id": "S2"}]}), api_marker=1)
        schedule = Schedule.objects.create(start_date=timezone.now(), max_quantity=2, selection_filters={"country": self.country.pk}, created_by=self.user)
        schedule.platforms.add(self.platform)
        run_scheduled_harvests()
        harvest = schedule.harvests.get()
        self.assertEqual(harvest.selection_filters, {"country": self.country.pk})
        self.assertEqual(harvest.resolved_filters, filters)
        self.assertEqual(harvest.filter_key, previous.filter_key)
        self.assertEqual(harvest.api_cursor, previous.api_cursor)
        self.assertEqual(harvest.api_page, previous.api_page)
        self.assertEqual(harvest.api_marker, 1)

    @patch("apps.harvesting.services.OpenAlexHarvester._get_client")
    def test_retired_selection_preserves_history_and_fails_before_consuming_cached_page(self, client):
        retired = {"is_in_doaj": True}
        harvest = self.harvest(selection_filters=retired, filter_key=filter_key(retired), api_page=json.dumps({"results": [{"id": "S1"}]}))
        process_harvest_worker_step(harvest.pk, 0)
        harvest.refresh_from_db()
        self.assertEqual(harvest.state, "failed")
        self.assertEqual(harvest.api_marker, 0)
        client.assert_not_called()
        self.assertEqual(get_latest_harvest_progress(self.platform, retired)["api_page"], harvest.api_page)

    def test_resolve_all_catalog_fields(self):
        self.assertEqual(resolve_filters({"publisher": self.editorial.pk, "language": self.language.pk}), {
            "publisher_exact": "editorial de selección", "language": "es",
        })

    def test_missing_archived_or_invalid_catalog_values_are_rejected(self):
        for selection in ({"country": 9223372036854775807}, {"language": 9223372036854775807}, {"publisher": 9223372036854775807}):
            with self.subTest(selection=selection), self.assertRaises(ValidationError):
                resolve_filters(selection)
        Editorial.objects.filter(pk=self.editorial.pk).update(deleted_at=timezone.now())
        with self.assertRaises(ValidationError):
            resolve_filters({"publisher": self.editorial.pk})
        Country.objects.filter(pk=self.country.pk).update(abbreviation="invalid")
        with self.assertRaises(ValidationError):
            resolve_filters({"country": self.country.pk})
        Language.objects.filter(pk=self.language.pk).update(abbreviation="es:foo")
        with self.assertRaises(ValidationError):
            resolve_filters({"language": self.language.pk})

    def test_doaj_publisher_and_language_match_catalog_snapshot_exactly(self):
        import xml.etree.ElementTree as ET
        from apps.harvesting.selection import doaj_matches
        harvest = self.harvest(resolved_filters=resolve_filters({"publisher": self.editorial.pk, "language": self.language.pk}))
        harvester = DoajHarvester(harvest)
        def record(publisher, language):
            return ET.fromstring(f'''<record xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><oai_dc:dc><dc:publisher>{publisher}</dc:publisher><dc:language>{language}</dc:language></oai_dc:dc></metadata></record>''')
        self.assertTrue(doaj_matches(harvester, record("EDITORIAL DE SELECCIÓN", "ES")))
        self.assertFalse(doaj_matches(harvester, record("Editorial de selección otra", "es")))
        self.assertFalse(doaj_matches(harvester, record("Editorial de selección", "en")))
        Editorial.objects.filter(pk=self.editorial.pk).update(name="Nuevo nombre")
        self.assertTrue(doaj_matches(harvester, record("Editorial de selección", "es")))
        with self.assertNumQueries(0):
            doaj_matches(harvester, record("Editorial de selección", "es"))

    @patch("apps.harvesting.services.OpenAlexHarvester._process_single_source", return_value=True)
    def test_openalex_wrong_or_missing_country_is_skipped_without_import(self, process):
        for source in ({"id": "S-wrong", "country_code": "US"}, {"id": "S-missing"}):
            harvest = self.harvest(state="running", selection_filters={"country": self.country.pk}, resolved_filters={"country_code": "CO"}, api_page=json.dumps({"results": [source], "meta": {"next_cursor": "next"}}))
            process_harvest_worker_step(harvest.pk, 0)
            harvest.refresh_from_db()
            self.assertEqual(harvest.records_skipped, 1)
            self.assertEqual(harvest.api_cursor, "next")
            self.assertEqual(harvest.api_marker, 0)
            harvest.state = "completed"
            harvest.save(update_fields=["state"])
        process.assert_not_called()
        self.assertFalse(HarvestSourceRecord.objects.filter(platform=self.platform).exists())

    @patch("apps.harvesting.services.dispatch_harvest_to_worker", side_effect=lambda harvest: harvest)
    def test_catalog_changed_after_validation_fails_only_affected_schedule(self, dispatch):
        from apps.harvesting.models import Schedule
        bad = Schedule.objects.create(start_date=timezone.now(), max_quantity=1, selection_filters={"country": 9223372036854775807}, created_by=self.user)
        bad.platforms.add(self.platform)
        good = Schedule.objects.create(start_date=timezone.now(), max_quantity=1, created_by=self.user)
        good.platforms.add(self.platform)
        run_scheduled_harvests()
        self.assertEqual(bad.harvests.get().state, "failed")
        self.assertNotEqual(bad.harvests.get().filter_key, "")
        self.assertEqual(good.harvests.get().state, "pending")

    @patch("apps.harvesting.services.dispatch_harvest_to_worker", side_effect=lambda harvest: harvest)
    def test_catalog_snapshot_uses_effective_values_for_pointer(self, dispatch):
        from apps.harvesting.models import Schedule
        resolved = resolve_filters({"country": self.country.pk})
        old = self.harvest(state="completed", resolved_filters=resolved, filter_key=filter_key(resolved), api_cursor="saved-country-cursor")
        schedule = Schedule.objects.create(start_date=timezone.now(), max_quantity=1, selection_filters={"country": self.country.pk}, created_by=self.user)
        schedule.platforms.add(self.platform)
        run_scheduled_harvests()
        harvest = schedule.harvests.get()
        self.assertEqual(harvest.api_cursor, old.api_cursor)
        Country.objects.filter(pk=self.country.pk).update(abbreviation="QY")
        harvest.refresh_from_db()
        self.assertEqual(harvest.resolved_filters, {"country_code": "CO"})
        self.assertNotEqual(filter_key(resolve_filters(schedule.selection_filters)), harvest.filter_key)

    @patch("apps.harvesting.services.OpenAlexHarvester._process_single_source", return_value=True)
    def test_direct_harvester_also_resolves_catalog_ids(self, process):
        from apps.harvesting.services import OpenAlexHarvester
        client = MagicMock()
        client.get.return_value.status_code = 200
        client.get.return_value.json.return_value = {"results": [], "meta": {"next_cursor": None}}
        harvest = Harvest.objects.create(platform=self.platform, max_quantity=1, selection_filters={"country": self.country.pk}, created_by=self.user)
        OpenAlexHarvester(harvest, client=client).harvest_records()
        harvest.refresh_from_db()
        self.assertEqual(harvest.resolved_filters, {"country_code": "CO"})
        self.assertEqual(client.get.call_args.kwargs["params"]["filter"], "type:journal,country_code:CO")
