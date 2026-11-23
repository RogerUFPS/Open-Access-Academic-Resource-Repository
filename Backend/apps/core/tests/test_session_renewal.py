from datetime import timedelta
from importlib import import_module
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.core.middleware import (
    SESSION_RENEWED_AT_KEY,
    ThrottledSessionRenewalMiddleware,
)

NOW = 1_800_000_000


def reading_view(request):
    # Simula una vista autenticada: lee la sesión sin modificarla.
    request.session.get("_auth_user_id")
    return HttpResponse("ok")


def untouched_view(request):
    return HttpResponse("ok")


def logout_view(request):
    request.session.flush()
    return HttpResponse("ok")


@override_settings(SESSION_SAVE_EVERY_REQUEST=False, SESSION_RENEWAL_INTERVAL=60)
class ThrottledSessionRenewalMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        store = import_module(settings.SESSION_ENGINE).SessionStore()
        store["_auth_user_id"] = "1"
        store[SESSION_RENEWED_AT_KEY] = NOW
        store.create()
        self.session_key = store.session_key
        self.expiring_soon = timezone.now() + timedelta(minutes=5)
        Session.objects.filter(session_key=self.session_key).update(
            expire_date=self.expiring_soon,
        )

    def request(self, view, at):
        stack = SessionMiddleware(ThrottledSessionRenewalMiddleware(view))
        request = self.factory.get("/")
        request.COOKIES[settings.SESSION_COOKIE_NAME] = self.session_key
        with patch("apps.core.middleware.time.time", return_value=at):
            return stack(request)

    def stored_session(self):
        return Session.objects.filter(session_key=self.session_key).first()

    def test_does_not_write_session_within_interval(self):
        response = self.request(reading_view, at=NOW + 59)

        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(self.stored_session().expire_date, self.expiring_soon)

    def test_renews_expiration_after_interval(self):
        response = self.request(reading_view, at=NOW + 60)

        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie.value, self.session_key)
        self.assertEqual(cookie["max-age"], settings.SESSION_COOKIE_AGE)
        session = self.stored_session()
        self.assertGreater(session.expire_date, self.expiring_soon)
        self.assertEqual(session.get_decoded()[SESSION_RENEWED_AT_KEY], NOW + 60)

    def test_session_without_marker_is_renewed(self):
        store = import_module(settings.SESSION_ENGINE).SessionStore(
            session_key=self.session_key,
        )
        del store[SESSION_RENEWED_AT_KEY]
        store.save()

        response = self.request(reading_view, at=NOW)

        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(
            self.stored_session().get_decoded()[SESSION_RENEWED_AT_KEY], NOW,
        )

    def test_unaccessed_session_is_not_written(self):
        response = self.request(untouched_view, at=NOW + 3600)

        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(self.stored_session().expire_date, self.expiring_soon)

    def test_flushed_session_is_not_recreated(self):
        self.request(logout_view, at=NOW + 3600)

        self.assertIsNone(self.stored_session())
        self.assertEqual(Session.objects.count(), 0)

    @override_settings(SESSION_RENEWAL_INTERVAL=0)
    def test_zero_interval_renews_every_request(self):
        response = self.request(reading_view, at=NOW)

        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertGreater(self.stored_session().expire_date, self.expiring_soon)
