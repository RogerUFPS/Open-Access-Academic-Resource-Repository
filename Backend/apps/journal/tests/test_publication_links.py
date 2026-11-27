"""Publicación y visibilidad pública de una revista según sus enlaces.

Regla: una asociación Journal–Platform "sirve" si la plataforma está publicada
y tanto su URL pública como la URL de la revista en esa plataforma están
verificadas y disponibles. Basta una asociación que sirva para publicar; la
ficha pública y el filtro público solo muestran las asociaciones que sirven.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.catalog.models import (
    AcademicProgram,
    Country,
    Editorial,
    Institution,
    Language,
    MaterialType,
)
from apps.journal import models, serializers
from apps.journal.services import (
    validate_journal_for_publication,
    with_latest_platform_links,
)
from apps.platforms.models import LinkCheckLog, Platform
from apps.platforms import models as platform_models
from apps.platforms.services import journal_platform_is_serving

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
UNVERIFIED = "unverified"


class PublicationLinksMixin:
    @classmethod
    def create_base(cls):
        cls.user = User.objects.create_user(
            email="publicacion-enlaces@test.local",
            password="Contrasena-Fuerte-2026",
            full_name="Publicación enlaces",
            permissions={"journals": {"journals": {"view": True, "publish": True}}},
        )
        cls.editorial = Editorial.objects.create(
            name="Editorial publicación enlaces", created_by=cls.user,
        )
        cls.relations = (
            (
                models.SharedJournalLanguage, "language",
                Language.objects.create(
                    name="Idioma publicación enlaces", abbreviation="jpl",
                    created_by=cls.user,
                ),
            ),
            (
                models.SharedJournalCountry, "country",
                Country.objects.create(
                    name="País publicación enlaces", abbreviation="jpl",
                    emoji_flag="🏳️", created_by=cls.user,
                ),
            ),
            (
                models.SharedJournalMaterialType, "material_type",
                MaterialType.objects.create(
                    name="Material publicación enlaces", created_by=cls.user,
                ),
            ),
            (
                models.SharedJournalAcademicProgram, "academic_program",
                AcademicProgram.objects.create(
                    name="Programa publicación enlaces", created_by=cls.user,
                ),
            ),
            (
                models.SharedJournalLicense, "license",
                models.License.objects.create(
                    name="Licencia publicación enlaces", created_by=cls.user,
                ),
            ),
        )

    @classmethod
    def platform(cls, name, *, status=Platform.Status.PUBLICADO, public=AVAILABLE):
        platform = Platform.objects.create(name=name, status=status, created_by=cls.user)
        if public is not None:
            cls.log(platform, f"https://8.8.8.8/{platform.pk}", public)
        return platform

    @classmethod
    def journal(cls, issn, *, active=False):
        journal = models.Journal.objects.create(
            issn=issn,
            title=f"Revista {issn}",
            editorial=cls.editorial,
            url_image="https://example.org/journal.png",
            publication_date=timezone.localdate(),
            active=active,
            validated_by=cls.user if active else None,
            validated_at=timezone.now() if active else None,
            created_by=cls.user,
        )
        for through, field, related in cls.relations:
            through.objects.create(
                journal=journal, **{field: related}, created_by=cls.user,
            )
        return journal

    @classmethod
    def associate(cls, journal, platform, journal_link=AVAILABLE):
        relation = models.SharedJournalPlatform.objects.create(
            journal=journal, platform=platform, created_by=cls.user
        )
        if journal_link is not None:
            cls.log(
                platform,
                f"https://8.8.8.8/{platform.pk}/{journal.pk}",
                journal_link,
                journal_platform=relation,
            )
        return relation

    @classmethod
    def log(cls, platform, url, state, *, journal_platform=None):
        checked = state != UNVERIFIED
        return LinkCheckLog.objects.create(
            platform=platform,
            journal_platform=journal_platform,
            url=url,
            is_active=state == AVAILABLE,
            last_check=timezone.now() if checked else None,
            fail_count=1 if state == UNAVAILABLE else 0,
            created_by=cls.user,
        )


class JournalPublicationLinkRuleTests(PublicationLinksMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_base()

    def platform_errors(self, journal):
        """Comprueba que la ficha completa solo pueda fallar por sus enlaces."""
        try:
            validate_journal_for_publication(journal)
        except ValidationError as exc:
            self.assertEqual(set(exc.detail), {"platforms"})
            return exc.detail["platforms"]
        return None

    def test_one_serving_association_is_enough(self):
        journal = self.journal("1111-0001")
        self.associate(journal, self.platform("Sirve"))
        self.associate(journal, self.platform("Caída"), journal_link=UNAVAILABLE)
        self.associate(journal, self.platform("Sin verificar"), journal_link=UNVERIFIED)

        validate_journal_for_publication(journal)

    def test_unverified_journal_url_blocks_publication(self):
        journal = self.journal("1111-0002")
        self.associate(journal, self.platform("Plataforma"), journal_link=UNVERIFIED)

        self.assertIn("verificadas y disponibles", str(self.platform_errors(journal)))

    def test_unavailable_journal_url_blocks_publication(self):
        journal = self.journal("1111-0003")
        self.associate(journal, self.platform("Plataforma"), journal_link=UNAVAILABLE)

        self.assertIsNotNone(self.platform_errors(journal))

    def test_platform_public_url_must_also_serve(self):
        for number, state in enumerate((UNVERIFIED, UNAVAILABLE, None)):
            with self.subTest(public=state):
                journal = self.journal(f"1111-010{number}")
                self.associate(journal, self.platform(f"Pública {state}", public=state))

                self.assertIsNotNone(self.platform_errors(journal))

    def test_serving_links_on_unpublished_platform_do_not_count(self):
        journal = self.journal("1111-0004")
        self.associate(journal, self.platform("Borrador", status=Platform.Status.BORRADOR))

        self.assertIn("ninguna se encuentra publicada", str(self.platform_errors(journal)))

    def test_latest_check_decides_after_recovery_or_failure(self):
        platform = self.platform("Historial")
        journal = self.journal("1111-0005")
        relation = self.associate(journal, platform, journal_link=AVAILABLE)
        url = f"https://8.8.8.8/{platform.pk}/{journal.pk}"

        self.log(platform, url, UNAVAILABLE, journal_platform=relation)
        self.assertIsNotNone(self.platform_errors(journal))

        self.log(platform, url, AVAILABLE, journal_platform=relation)
        self.assertIsNone(self.platform_errors(journal))

    def test_new_unverified_url_replaces_historical_success(self):
        journal = self.journal("1111-0006")
        platform = self.platform("URL reemplazada")
        relation = self.associate(journal, platform)
        self.log(
            platform, "https://8.8.8.8/new-journal-url", UNVERIFIED,
            journal_platform=relation,
        )

        self.assertIsNotNone(self.platform_errors(journal))

    def test_publication_query_count_does_not_grow_per_association(self):
        journal = self.journal("1111-0007")
        self.associate(journal, self.platform("Consultas 0"))
        with CaptureQueriesContext(connection) as single:
            validate_journal_for_publication(journal)

        for index in range(1, 10):
            self.associate(journal, self.platform(f"Consultas {index}"))
        with CaptureQueriesContext(connection) as multiple:
            validate_journal_for_publication(journal)

        self.assertEqual(len(single), len(multiple))

    def test_prefetch_keeps_only_latest_event_in_each_context(self):
        journal = self.journal("1111-0008")
        platform = self.platform("Historial precargado")
        relation = self.associate(journal, platform)
        for index in range(3):
            public_log = self.log(
                platform, f"https://8.8.8.8/public/{index}", AVAILABLE,
            )
            journal_log = self.log(
                platform, f"https://8.8.8.8/journal/{index}", AVAILABLE,
                journal_platform=relation,
            )

        loaded = with_latest_platform_links(
            models.SharedJournalPlatform.objects.filter(pk=relation.pk)
        ).get()
        self.assertEqual(
            [log.pk for log in loaded.platform._public_link_logs], [public_log.pk],
        )
        self.assertEqual(
            [log.pk for log in loaded._journal_link_logs], [journal_log.pk],
        )
        with self.assertNumQueries(0):
            self.assertTrue(journal_platform_is_serving(loaded))


class JournalPublicPlatformsTests(PublicationLinksMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_base()
        cls.serving = cls.platform("A sirve")
        cls.down = cls.platform("B caída")
        cls.public_down = cls.platform("C pública caída", public=UNAVAILABLE)
        cls.draft = cls.platform("D borrador", status=Platform.Status.BORRADOR)

        cls.published = cls.journal("2222-0001", active=True)
        cls.associate(cls.published, cls.serving)
        cls.associate(cls.published, cls.down, journal_link=UNAVAILABLE)
        cls.associate(cls.published, cls.public_down)
        cls.associate(cls.published, cls.draft)

    def test_public_detail_lists_only_serving_associations(self):
        data = serializers.JournalPublicSerializer(self.published).data

        self.assertEqual([item["id"] for item in data["platforms"]], [self.serving.pk])

    def test_public_list_lists_only_serving_associations(self):
        response = self.client.get(
            "/api/journals/public/", {"issn": self.published.issn},
        )

        self.assertEqual(response.status_code, 200)
        (item,) = [row for row in response.data["results"] if row["id"] == self.published.pk]
        self.assertEqual([platform["id"] for platform in item["platforms"]], [self.serving.pk])

    def test_public_platform_filter_requires_serving_association(self):
        expected = {
            self.serving: [self.published.pk],
            self.down: [],
            self.public_down: [],
            self.draft: [],
        }
        for platform, ids in expected.items():
            with self.subTest(platform=platform.name):
                response = self.client.get("/api/journals/public/", {"platform": platform.pk})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.data["results"]], ids)

    def test_publish_endpoint_accepts_one_serving_association(self):
        # La publicación recalcula Platform y vuelve a validar su ficha.
        # Completar también sus requisitos propios evita un fixture publicado
        # que producción devolvería correctamente a borrador.
        self.serving.url_image = "https://example.org/platform.png"
        self.serving.valid_sintaxis = platform_models.ValidSintaxis.objects.create(
            name="Sintaxis publicación enlaces", created_by=self.user,
        )
        self.serving.save(update_fields=["url_image", "valid_sintaxis"])
        institution = Institution.objects.create(
            name="Institución publicación enlaces", created_by=self.user,
        )
        platform_models.SharedPlatformSupport.objects.create(
            platform=self.serving, institution=institution,
            is_manual=True, created_by=self.user,
        )
        journal = self.journal("2222-0002")
        self.associate(journal, self.serving)
        self.associate(journal, self.down, journal_link=UNAVAILABLE)
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/journals/{journal.pk}/publish/", {}, format="json",
        )

        self.assertEqual(response.status_code, 200)
        journal.refresh_from_db()
        self.assertTrue(journal.active)
        self.assertEqual(journal.validated_by_id, self.user.pk)
        self.assertIsNotNone(journal.validated_at)
        self.serving.refresh_from_db()
        self.assertEqual(self.serving.status, Platform.Status.PUBLICADO)
        public = self.client.get(f"/api/journals/public/{journal.pk}/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(
            [item["id"] for item in public.data["platforms"]], [self.serving.pk],
        )

    def test_all_links_failing_keeps_published_journal_visible(self):
        relation = self.published.platform_links.get(platform=self.serving)
        self.log(
            self.serving, "https://8.8.8.8/failed", UNAVAILABLE,
            journal_platform=relation,
        )

        response = self.client.get(f"/api/journals/public/{self.published.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["platforms"], [])
        self.published.refresh_from_db()
        self.assertTrue(self.published.active)
        self.assertIsNotNone(self.published.validated_at)

    def test_unverified_replacement_is_hidden_by_serializer_and_filter(self):
        relation = self.published.platform_links.get(platform=self.serving)
        for context in (relation, None):
            with self.subTest(context="journal" if context else "platform"):
                self.log(
                    self.serving, "https://8.8.8.8/restored", AVAILABLE,
                    journal_platform=relation,
                )
                self.log(
                    self.serving, "https://8.8.8.8/new", UNVERIFIED,
                    journal_platform=context,
                )
                detail = self.client.get(
                    f"/api/journals/public/{self.published.pk}/",
                )
                filtered = self.client.get(
                    "/api/journals/public/",
                    {"issn": self.published.issn, "platform": self.serving.pk},
                )

                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.data["platforms"], [])
                self.assertEqual(filtered.status_code, 200)
                self.assertEqual(filtered.data["results"], [])
