from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import CustomUser, Mentorship
from curriculum.models import Lesson
from growth.models import Assignment, Reflection
from pods.models import Pod, PodMember


class Command(BaseCommand):
    help = 'Create a demo discipleship setup for local development.'

    def handle(self, *args, **options):
        admin_user, _ = CustomUser.objects.get_or_create(
            username='campadmin',
            defaults={
                'email': 'admin@campofgilgal.com',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if not admin_user.has_usable_password():
            admin_user.set_password('Password123!')
            admin_user.save(update_fields=['password'])

        mentor, _ = CustomUser.objects.get_or_create(
            username='mentorone',
            defaults={'email': 'mentor@example.com', 'role': 'mentor'},
        )
        mentee, _ = CustomUser.objects.get_or_create(
            username='menteeone',
            defaults={'email': 'mentee@example.com', 'role': 'mentee'},
        )

        Mentorship.objects.get_or_create(mentor=mentor, mentee=mentee)

        pod, _ = Pod.objects.get_or_create(
            name='Faith Walk Pod',
            defaults={'leader': mentor, 'description': 'A discipleship pod for prayer and multiplication.'},
        )

        PodMember.objects.get_or_create(pod=pod, user=mentor, defaults={'role': 'LEADER'})
        PodMember.objects.get_or_create(pod=pod, user=mentee, defaults={'role': 'MEMBER'})

        lesson, _ = Lesson.objects.get_or_create(
            title='Foundations of Prayer',
            defaults={
                'description': 'A foundational lesson on prayer and spiritual discipline.',
                'content': 'Prayer is the heartbeat of discipleship. Begin with confession, thanksgiving, and listening.',
                'created_by': mentor,
                'is_master_template': True,
            },
        )

        assignment, _ = Assignment.objects.get_or_create(
            title='Pray daily with a partner',
            defaults={
                'lesson': lesson,
                'pod': pod,
                'instruction': 'Pray for 15 minutes daily and write a short reflection on what God showed you.',
                'due_date': timezone.now().date(),
                'created_by': mentor,
                'status': 'published',
            },
        )

        Reflection.objects.get_or_create(
            assignment=assignment,
            user=mentee,
            defaults={
                'written_content': 'I learned that prayer deepens my dependence on God and helps me listen well.',
                'mentor_feedback': 'Good start. Continue to pray daily and be honest before God.',
                'is_approved': True,
                'status': 'approved',
                'reviewed_at': timezone.now(),
            },
        )

        self.stdout.write(self.style.SUCCESS('Demo discipleship data has been created successfully.'))
