from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from pods.models import Pod, PodMember


class CurriculumVisibilityTests(TestCase):
    def setUp(self):
        self.member = CustomUser.objects.create_user(
            username='curriculum-member',
            password='test-password',
        )
        self.leader = CustomUser.objects.create_user(
            username='curriculum-leader',
            password='test-password',
        )
        pod = Pod.objects.create(name='Curriculum Pod', leader=self.leader)
        PodMember.objects.create(pod=pod, user=self.leader, role='LEADER')
        PodMember.objects.create(pod=pod, user=self.member, role='MEMBER')

    def test_regular_member_does_not_see_upload_lesson_action(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('lesson_list'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Upload New Lesson')

    def test_pod_leader_sees_upload_lesson_action(self):
        self.client.force_login(self.leader)

        response = self.client.get(reverse('lesson_list'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload New Lesson')

    def test_non_leader_cannot_open_lesson_creation(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('lesson_create'), secure=True)

        self.assertRedirects(
            response,
            reverse('lesson_list'),
            fetch_redirect_response=False,
        )
