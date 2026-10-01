from django.test import TestCase
from django.contrib.auth import get_user_model
from pods.models import Pod, Mentorship
from growth.models import Reflection, Assignment
from accounts.utils import build_discipleship_tree, get_multiplication_stats

User = get_user_model()

class DiscipleshipTreeTestCase(TestCase):
    def setUp(self):
        # Create leader and 3 generations of disciples
        self.leader = User.objects.create_user(username='leader', email='leader@test.com', password='password123')
        self.gen1_mentee = User.objects.create_user(username='gen1', email='gen1@test.com', password='password123')
        self.gen2_mentee = User.objects.create_user(username='gen2', email='gen2@test.com', password='password123')

        # Establish mentorship links
        Mentorship.objects.create(mentor=self.leader, mentee=self.gen1_mentee, is_active=True)
        Mentorship.objects.create(mentor=self.gen1_mentee, mentee=self.gen2_mentee, is_active=True)

    def test_discipleship_tree_structure(self):
        tree = build_discipleship_tree(self.leader)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]['email'], 'gen1@test.com')
        self.assertEqual(len(tree[0]['children']), 1)
        self.assertEqual(tree[0]['children'][0]['email'], 'gen2@test.com')

    def test_multiplication_stats_calculation(self):
        stats = get_multiplication_stats(self.leader)
        self.assertEqual(stats['total_footprint'], 2)
        self.assertEqual(stats['gen_1_count'], 1)
        self.assertEqual(stats['gen_2_plus_count'], 1)
        self.assertEqual(stats['max_depth'], 2)
