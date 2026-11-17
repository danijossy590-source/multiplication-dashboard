import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser


class SignupRoleTests(TestCase):
    def test_landing_page_displays_orientation_content(self):
        response = self.client.get(reverse("landing"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Guidelines for Every Lesson")
        self.assertContains(response, "Our Commitment to You")
        self.assertContains(response, "Ocheni Josiah O.")

    def test_signup_always_creates_mentee_even_if_role_is_submitted(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-mentee",
                "email": "new-mentee@example.com",
                "password1": "Strong-password-123!",
                "password2": "Strong-password-123!",
                "role": "admin",
            },
            secure=True,
        )

        self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)
        user = CustomUser.objects.get(username="new-mentee")
        self.assertEqual(user.role, "mentee")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_signup_page_does_not_show_role_selection(self):
        response = self.client.get(reverse("signup"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="role"')


class AdminRolePreservationTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="platform-admin",
            password="Admin-password-1",
            role="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_changing_admin_role_to_mentor_keeps_admin_access(self):
        response = self.client.post(
            reverse("admin_users"),
            {"user_id": self.admin.pk, "action": "make_mentor"},
            secure=True,
        )

        self.assertRedirects(response, reverse("admin_users"), fetch_redirect_response=False)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "mentor")
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.is_superuser)

    def test_changing_admin_role_to_mentee_keeps_admin_access(self):
        self.client.post(
            reverse("admin_users"),
            {"user_id": self.admin.pk, "action": "make_mentee"},
            secure=True,
        )

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "mentee")
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.is_superuser)

    def test_changing_regular_user_role_does_not_grant_admin_access(self):
        user = CustomUser.objects.create_user(
            username="regular-user",
            password="User-password-1",
            role="mentee",
        )

        self.client.post(
            reverse("admin_users"),
            {"user_id": user.pk, "action": "make_mentor"},
            secure=True,
        )

        user.refresh_from_db()
        self.assertEqual(user.role, "mentor")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_admin_portal_uses_admin_workspace_not_member_actions(self):
        response = self.client.get(reverse("admin_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform operations")
        self.assertNotContains(response, "Upload New Lesson")


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
