import os
import runpy
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "CapstoneProject" / "settings.py"


class SettingsTests(SimpleTestCase):
    def load_settings(self, environment):
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch("dotenv.load_dotenv"):
            return runpy.run_path(str(SETTINGS_FILE))

    def test_production_requires_explicit_secret(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            self.load_settings({})

    def test_production_rejects_weak_secret_and_wildcard_hosts(self):
        for environment in (
            {"DJANGO_SECRET_KEY": "short", "DJANGO_ALLOWED_HOSTS": "example.com"},
            {"DJANGO_SECRET_KEY": "long-disposable-test-value-" * 3, "DJANGO_ALLOWED_HOSTS": "*"},
        ):
            with self.subTest(environment=list(environment)):
                with self.assertRaises(ImproperlyConfigured):
                    self.load_settings(environment)

    def test_production_is_https_and_ai_is_opt_in(self):
        settings = self.load_settings(
            {
                "DJANGO_SECRET_KEY": "long-disposable-test-value-" * 3,
                "DJANGO_ALLOWED_HOSTS": "example.com",
            }
        )
        self.assertFalse(settings["DEBUG"])
        self.assertFalse(settings["AI_ENABLED"])
        self.assertTrue(settings["SESSION_COOKIE_SECURE"])
        self.assertTrue(settings["CSRF_COOKIE_SECURE"])
        self.assertTrue(settings["SECURE_SSL_REDIRECT"])
