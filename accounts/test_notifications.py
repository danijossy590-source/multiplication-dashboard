from django.core.management import call_command
from django.test import TestCase

from accounts.models import CustomUser, Mentorship
from accounts.utils import notify_user, build_discipleship_tree, get_multiplication_stats
from curriculum.models import Lesson
from growth.models import Assignment, Reflection
from pods.models import Pod


class NotificationFlowTests(TestCase):
    def test_notify_user_creates_unread_notification(self):
        user = CustomUser.objects.create_user(username='demo-user', email='demo@example.com', password='Pass1234!')

        notify_user(user, 'Welcome', 'You are now a Multiply member.', '/profile/')

        notification = user.notifications.get()
        self.assertEqual(notification.title, 'Welcome')
        self.assertFalse(notification.is_read)

    def test_seed_demo_data_creates_demo_records(self):
        call_command('seed_demo_data')

        self.assertTrue(CustomUser.objects.filter(username='campadmin').exists())
        self.assertTrue(CustomUser.objects.filter(username='mentorone').exists())
        self.assertTrue(CustomUser.objects.filter(username='menteeone').exists())
        self.assertTrue(Pod.objects.filter(name='Faith Walk Pod').exists())
        self.assertTrue(Lesson.objects.filter(title='Foundations of Prayer').exists())
        self.assertTrue(Assignment.objects.filter(title='Pray daily with a partner').exists())

    def test_build_discipleship_tree_uses_mentorship_relationships(self):
        mentor = CustomUser.objects.create_user(username='mentor', email='mentor@example.com', password='Pass1234!')
        mentee = CustomUser.objects.create_user(username='mentee', email='mentee@example.com', password='Pass1234!')
        Mentorship.objects.create(mentor=mentor, mentee=mentee)

        assignment = Assignment.objects.create(
            title='Test challenge',
            instruction='Do the test',
            created_by=mentor,
        )
        Reflection.objects.create(
            assignment=assignment,
            user=mentee,
            written_content='I learned something.',
            is_approved=True,
            status='approved',
        )

        tree = build_discipleship_tree(mentor)
        stats = get_multiplication_stats(mentor)

        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]['generation'], 1)
        self.assertEqual(tree[0]['completed_challenges'], 1)
        self.assertEqual(stats['gen_1_count'], 1)
        self.assertEqual(stats['total_footprint'], 1)
