import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from accounts.models import CustomUser


class EnsureAdminsCommandTests(TestCase):
    def test_creates_configured_administrator(self):
        environment = {
            "DJANGO_ADMIN_1_USERNAME": "admin-one",
            "DJANGO_ADMIN_1_EMAIL": "admin-one@example.com",
            "DJANGO_ADMIN_1_PASSWORD": "Strong-password-1",
            "DJANGO_ADMIN_2_USERNAME": "",
            "DJANGO_ADMIN_2_EMAIL": "",
            "DJANGO_ADMIN_2_PASSWORD": "",
        }
        output = StringIO()

        with patch.dict(os.environ, environment, clear=False):
            call_command("ensure_admins", stdout=output)

        user = CustomUser.objects.get(username="admin-one")
        self.assertEqual(user.email, "admin-one@example.com")
        self.assertEqual(user.role, "admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("Strong-password-1"))

    def test_updates_existing_administrator(self):
        user = CustomUser.objects.create_user(
            username="admin-one",
            email="old@example.com",
            password="old-password",
        )
        environment = {
            "DJANGO_ADMIN_1_USERNAME": "admin-one",
            "DJANGO_ADMIN_1_EMAIL": "new@example.com",
            "DJANGO_ADMIN_1_PASSWORD": "new-password",
            "DJANGO_ADMIN_2_USERNAME": "",
            "DJANGO_ADMIN_2_EMAIL": "",
            "DJANGO_ADMIN_2_PASSWORD": "",
        }

        with patch.dict(os.environ, environment, clear=False):
            call_command("ensure_admins", stdout=StringIO())

        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password("new-password"))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
