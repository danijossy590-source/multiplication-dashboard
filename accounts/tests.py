import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core import mail
from django.test import TestCase, override_settings
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


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='reset-user',
            email='reset-user@example.com',
            password='Old-password-1',
        )

    def test_password_reset_changes_password_with_valid_email_link(self):
        response = self.client.post(
            reverse('password_reset'),
            {'email': self.user.email},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('password_reset_done'),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)

        reset_url = next(
            line for line in mail.outbox[0].body.splitlines()
            if '/accounts/password-reset/' in line
        )
        response = self.client.get(reset_url, secure=True, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose a new password')

        confirm_path = response.request['PATH_INFO']
        response = self.client.post(
            confirm_path,
            {
                'new_password1': 'New-strong-password-123!',
                'new_password2': 'New-strong-password-123!',
            },
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('password_reset_complete'),
            fetch_redirect_response=False,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-strong-password-123!'))

    def test_password_reset_response_does_not_disclose_unknown_email(self):
        response = self.client.post(
            reverse('password_reset'),
            {'email': 'unknown@example.com'},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('password_reset_done'),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 0)


class ProfileEditTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="profile-user",
            email="old@example.com",
            password="User-password-1",
            first_name="Old",
            last_name="Name",
        )
        self.client.force_login(self.user)

    def test_profile_page_links_to_edit_profile(self):
        response = self.client.get(reverse("profile"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("edit_profile"))

    def test_member_navigation_links_to_each_main_section(self):
        response = self.client.get(reverse("multiplication_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)
        for route_name in ("multiplication_dashboard", "profile", "pod_list", "lesson_list", "question_list", "notifications"):
            self.assertContains(response, reverse(route_name))

    def test_edit_profile_updates_allowed_fields(self):
        response = self.client.post(
            reverse("edit_profile"),
            {
                "first_name": "New",
                "last_name": "Person",
                "email": "new@example.com",
                "phone_number": "123456789",
                "bio": "Updated bio",
            },
            secure=True,
        )

        self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "New")
        self.assertEqual(self.user.last_name, "Person")
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.phone_number, "123456789")
        self.assertEqual(self.user.bio, "Updated bio")

    def test_edit_profile_rejects_invalid_email(self):
        response = self.client.post(
            reverse("edit_profile"),
            {
                "first_name": "New",
                "last_name": "Person",
                "email": "not-an-email",
                "phone_number": "",
                "bio": "",
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address")


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

    def test_changing_admin_role_to_mentor_revokes_admin_access(self):
        response = self.client.post(
            reverse("admin_users"),
            {"user_id": self.admin.pk, "action": "make_mentor"},
            secure=True,
        )

        self.assertRedirects(response, reverse("admin_users"), fetch_redirect_response=False)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "mentor")
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)
        self.assertEqual(self.client.get(reverse("admin_dashboard"), secure=True).status_code, 302)

    def test_changing_admin_role_to_mentee_revokes_admin_access(self):
        self.client.post(
            reverse("admin_users"),
            {"user_id": self.admin.pk, "action": "make_mentee"},
            secure=True,
        )

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "mentee")
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)
        self.assertEqual(self.client.get(reverse("admin_dashboard"), secure=True).status_code, 302)

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

    def test_granting_admin_access_requires_confirmation(self):
        user = CustomUser.objects.create_user(
            username="new-admin",
            password="User-password-1",
        )

        confirmation = self.client.post(
            reverse("admin_users"),
            {"user_id": user.pk, "action": "make_admin"},
            secure=True,
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "Grant admin access")
        user.refresh_from_db()
        self.assertFalse(user.is_staff)

        response = self.client.post(
            reverse("admin_users"),
            {
                "user_id": user.pk,
                "action": "make_admin",
                "confirm_action": "yes",
            },
            secure=True,
        )
        self.assertRedirects(response, reverse("admin_users"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_admin_portal_uses_admin_workspace_not_member_actions(self):
        response = self.client.get(reverse("admin_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform operations")
        self.assertNotContains(response, "Upload New Lesson")
        self.assertContains(response, reverse("admin_users"))
        self.assertContains(response, reverse("admin:index"))
        self.assertContains(response, reverse("multiplication_dashboard"))
        self.assertContains(response, reverse("pod_list"))
        self.assertContains(response, reverse("lesson_list"))
        self.assertContains(response, reverse("question_list"))

        users_response = self.client.get(reverse("admin_users"), secure=True)
        self.assertEqual(users_response.status_code, 200)
        self.assertContains(users_response, "Manage users")
        self.assertContains(users_response, reverse("admin_dashboard"))


class DjangoAdminIntegrationTests(TestCase):
    def test_superuser_account_has_frontend_admin_rights_and_shared_content_admin(self):
        admin_user = CustomUser.objects.create_user(
            username="django-superuser",
            password="Django-admin-password-1",
            role="mentee",
            is_superuser=True,
        )

        self.assertEqual(admin_user.role, "admin")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)

        self.client.force_login(admin_user)
        portal_response = self.client.get(reverse("admin_dashboard"), secure=True)
        django_admin_response = self.client.get(reverse("admin:index"), secure=True)

        self.assertEqual(portal_response.status_code, 200)
        self.assertEqual(django_admin_response.status_code, 200)
        self.assertContains(django_admin_response, reverse("admin_dashboard"))
        self.assertContains(
            django_admin_response,
            reverse("admin:curriculum_course_changelist"),
        )
        self.assertContains(
            django_admin_response,
            reverse("admin:curriculum_lesson_changelist"),
        )

    def test_django_admin_can_create_an_admin_with_portal_rights(self):
        root_admin = CustomUser.objects.create_superuser(
            username="django-root",
            email="django-root@example.com",
            password="Django-root-password-1",
        )
        self.client.force_login(root_admin)

        response = self.client.post(
            reverse("admin:accounts_customuser_add"),
            {
                "username": "backend-created-admin",
                "email": "backend-admin@example.com",
                "role": "admin",
                "phone_number": "",
                "bio": "",
                "password1": "Complex-unrelated-Password-753!",
                "password2": "Complex-unrelated-Password-753!",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
            response.context["adminform"].form.errors if response.status_code == 200 else "",
        )
        created_admin = CustomUser.objects.get(username="backend-created-admin")
        self.assertEqual(created_admin.role, "admin")
        self.assertTrue(created_admin.is_staff)
        self.assertTrue(created_admin.is_superuser)


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
