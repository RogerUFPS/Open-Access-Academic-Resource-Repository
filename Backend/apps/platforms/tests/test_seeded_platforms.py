from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.catalog.models import (
    AcademicProgram,
    Language,
    SharedAcademicProgramKnowledgeArea,
)
from apps.platforms import models, services


class SeededHarvestPlatformTests(TestCase):
    def test_doaj_and_openalex_are_complete_drafts_except_for_image(self):
        expected = {
            "DOAJ": {
                "country": "DK",
                "institution": "DOAJ Foundation",
                "start_year": 2003,
            },
            "OpenAlex": {
                "country": "US",
                "institution": "OpenAlex",
                "start_year": 2022,
            },
        }
        language_count = Language.objects.count()
        program_count = AcademicProgram.objects.count()
        expected_area_ids = set(
            SharedAcademicProgramKnowledgeArea.objects.values_list(
                "knowledge_area_id", flat=True
            )
        )

        for name, metadata in expected.items():
            with self.subTest(platform=name):
                platform = models.Platform.objects.get(name__iexact=name)
                self.assertEqual(platform.status, models.Platform.Status.BORRADOR)
                self.assertIsNone(platform.validated_at)
                self.assertIsNone(platform.validated_by_id)
                self.assertIsNone(platform.url_image)
                self.assertEqual(platform.start_period.year, metadata["start_year"])
                self.assertTrue(platform.is_harvestable)
                self.assertIsNotNone(platform.valid_sintaxis_id)

                self.assertTrue(
                    models.SharedPlatformCountry.objects.filter(
                        platform=platform,
                        country__abbreviation=metadata["country"],
                        is_manual=True,
                    ).exists()
                )
                self.assertTrue(
                    models.SharedPlatformSupport.objects.filter(
                        platform=platform,
                        institution__name=metadata["institution"],
                        is_manual=True,
                    ).exists()
                )
                self.assertEqual(
                    models.SharedPlatformLanguage.objects.filter(
                        platform=platform,
                        is_manual=True,
                    ).count(),
                    language_count,
                )
                self.assertEqual(
                    models.SharedPlatformAcademicProgram.objects.filter(
                        platform=platform,
                        is_manual=True,
                    ).count(),
                    program_count,
                )
                self.assertEqual(
                    set(
                        models.SharedPlatformKnowledgeArea.objects.filter(
                            platform=platform,
                            is_derived=True,
                        ).values_list("knowledge_area_id", flat=True)
                    ),
                    expected_area_ids,
                )

                with self.assertRaises(ValidationError) as raised:
                    services.validate_platform_for_publication(platform)
                self.assertEqual(set(raised.exception.detail), {"url_image"})
