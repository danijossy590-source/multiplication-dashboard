from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from growth.models import Assignment


class ReflectionFormTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='reflection-learner',
            password='test-password',
        )
        self.assignment = Assignment.objects.create(
            title='First challenge',
            instruction='Write about what you learned.',
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_invalid_reflection_shows_error_and_cancel_action(self):
        response = self.client.post(
            reverse('reflection_submit', args=[self.assignment.pk]),
            {'written_content': ''},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your reflection was not submitted')
        self.assertContains(response, 'This field is required.')
        self.assertContains(response, 'Cancel')
        self.assertFalse(self.assignment.reflections.exists())
