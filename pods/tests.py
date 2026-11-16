from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from .models import Pod, PodMember


class PodPageTests(TestCase):
    def setUp(self):
        self.leader = CustomUser.objects.create_user(
            username='pod-leader',
            password='test-password',
        )
        self.member = CustomUser.objects.create_user(
            username='pod-member',
            password='test-password',
        )
        self.pod = Pod.objects.create(name='Test Pod', leader=self.leader)
        PodMember.objects.create(pod=self.pod, user=self.leader, role='LEADER')
        PodMember.objects.create(pod=self.pod, user=self.member, role='MEMBER')

    def test_pod_list_renders_for_member(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('pod_list'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Pod')

    def test_member_can_open_pod_detail(self):
        self.client.force_login(self.member)

        response = self.client.get(
            reverse('pod_detail', args=[self.pod.pk]),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pod Members')
