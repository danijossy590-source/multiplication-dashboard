from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from .models import ApprenticeOversight, Pod, PodMeeting, PodMember, PodMessage, PodMentor


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

    def test_admin_can_create_pod_with_leader_and_mentors(self):
        admin = CustomUser.objects.create_user(
            username='pod-admin',
            password='test-password',
            is_staff=True,
        )
        mentor = CustomUser.objects.create_user(
            username='pod-mentor',
            password='test-password',
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse('pod_create'),
            {
                'name': 'Admin Pod',
                'description': 'Created by admin',
                'leader': self.leader.pk,
                'mentors': [mentor.pk],
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        pod = Pod.objects.get(name='Admin Pod')
        self.assertEqual(pod.leader, self.leader)
        self.assertTrue(PodMember.objects.filter(pod=pod, user=self.leader, role='LEADER').exists())
        self.assertTrue(PodMentor.objects.filter(pod=pod, mentor=mentor).exists())

    def test_admin_can_add_members_and_assign_mentors(self):
        admin = CustomUser.objects.create_user(
            username='pod-admin',
            password='test-password',
            is_staff=True,
        )
        mentor = CustomUser.objects.create_user(
            username='pod-mentor',
            password='test-password',
        )
        self.client.force_login(admin)

        add_member_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'add_member': '1', 'username': 'pod-admin', 'role': 'MEMBER'},
            secure=True,
        )
        assign_mentor_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'assign_mentors': '1', 'mentors': [mentor.pk]},
            secure=True,
        )

        self.assertEqual(add_member_response.status_code, 302)
        self.assertEqual(assign_mentor_response.status_code, 302)
        self.assertTrue(PodMember.objects.filter(pod=self.pod, user=admin).exists())
        self.assertTrue(PodMentor.objects.filter(pod=self.pod, mentor=mentor).exists())

        self.client.force_login(mentor)
        mentor_message_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'send_message': '1', 'body': 'Checking in as the pod mentor.'},
            secure=True,
        )
        self.assertEqual(mentor_message_response.status_code, 302)
        self.assertTrue(PodMessage.objects.filter(pod=self.pod, author=mentor).exists())

    def test_pod_member_can_chat_and_schedule_meeting(self):
        self.client.force_login(self.member)

        message_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'send_message': '1', 'body': 'See you all soon!'},
            secure=True,
        )
        meeting_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {
                'schedule_meeting': '1',
                'title': 'Weekly check-in',
                'details': 'Bring your reflections.',
                'scheduled_at': '2027-01-15T18:30',
                'meeting_url': 'https://example.com/meeting',
            },
            secure=True,
        )

        self.assertEqual(message_response.status_code, 302)
        self.assertEqual(meeting_response.status_code, 302)
        self.assertTrue(PodMessage.objects.filter(pod=self.pod, author=self.member, body='See you all soon!').exists())
        self.assertTrue(PodMeeting.objects.filter(pod=self.pod, title='Weekly check-in').exists())

    def test_apprentice_oversight_is_read_only_for_chat(self):
        mentor = CustomUser.objects.create_user(
            username='oversight-mentor',
            password='test-password',
        )
        ApprenticeOversight.objects.create(mentor=mentor, apprentice_pod=self.pod)
        self.client.force_login(mentor)

        response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'send_message': '1', 'body': 'This should not be posted.'},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PodMessage.objects.filter(pod=self.pod).exists())
