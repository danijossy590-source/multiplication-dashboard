from io import BytesIO
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from accounts.models import CustomUser
from curriculum.models import Course, Lesson, Module
from .books import prepare_book_document
from .models import (
    ApprenticeOversight,
    Pod,
    PodBook,
    PodBookReviewComment,
    PodBookReview,
    PodBookSectionProgress,
    PodMeeting,
    PodMember,
    PodMessage,
    PodMentor,
)


def make_pdf(page_count):
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PodBookSectioningTests(TestCase):
    def test_chapter_headings_are_kept_together_in_weekly_sections(self):
        pages = [
            Mock(extract_text=Mock(return_value='Chapter 1: Foundations\nFirst chapter.')),
            Mock(extract_text=Mock(return_value='First chapter continued.')),
            Mock(extract_text=Mock(return_value='Chapter 2: Practice\nSecond chapter.')),
            Mock(extract_text=Mock(return_value='Second chapter continued.')),
        ]
        with patch(
            'pods.books.PdfReader',
            return_value=Mock(is_encrypted=False, pages=pages),
        ):
            _, sections = prepare_book_document(
                SimpleUploadedFile('book.pdf', b'%PDF-test'),
                duration_weeks=2,
            )

        self.assertEqual(
            sections,
            [
                {
                    'week_number': 1,
                    'title': 'Chapter 1: Foundations',
                    'start_page': 1,
                    'end_page': 2,
                },
                {
                    'week_number': 2,
                    'title': 'Chapter 2: Practice',
                    'start_page': 3,
                    'end_page': 4,
                },
            ],
        )


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

    def test_pod_leader_can_assign_supported_book_file_and_reading_duration(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.client.force_login(self.leader)

        response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {
                'assign_book': '1',
                'title': 'A Book for the Pod',
                'duration_weeks': '6',
                'document': SimpleUploadedFile(
                    'pod-book.pdf',
                    make_pdf(12),
                    content_type='application/pdf',
                ),
            },
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('pod_detail', args=[self.pod.pk]),
            fetch_redirect_response=False,
        )
        book = PodBook.objects.get(pod=self.pod, is_current=True)
        self.assertEqual(book.title, 'A Book for the Pod')
        self.assertEqual(book.duration_weeks, 6)
        self.assertTrue(book.document.name.endswith('.pdf'))
        self.assertEqual(book.started_on, timezone.localdate())
        sections = list(book.sections.all())
        self.assertEqual(len(sections), 6)
        self.assertEqual((sections[0].start_page, sections[0].end_page), (1, 2))
        self.assertTrue(book.reader_pdf)

        self.client.force_login(self.member)
        reader_response = self.client.get(
            reverse('pod_book_read', args=[self.pod.pk, book.pk]),
            secure=True,
        )
        self.assertEqual(reader_response.status_code, 200)
        self.assertContains(reader_response, 'Week 1')
        self.assertContains(reader_response, 'Mark section as read')
        progress_response = self.client.post(
            reverse(
                'pod_book_section_progress',
                args=[self.pod.pk, book.pk, sections[0].pk],
            ),
            {'mark_complete': '1'},
            secure=True,
        )
        self.assertEqual(progress_response.status_code, 302)
        self.assertTrue(
            PodBookSectionProgress.objects.filter(
                section=sections[0],
                user=self.member,
            ).exists()
        )

    def test_weekly_reviews_are_unique_editable_and_cannot_be_submitted_early(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        book = PodBook.objects.create(
            pod=self.pod,
            title='A Book for the Pod',
            document=SimpleUploadedFile('pod-book.docx', b'word-document'),
            duration_weeks=3,
            assigned_by=self.leader,
        )
        self.client.force_login(self.member)

        first_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {
                'submit_book_review': '1',
                'week_number': '1',
                'review': 'My first thoughts.',
            },
            secure=True,
        )
        update_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {
                'submit_book_review': '1',
                'week_number': '1',
                'review': 'My updated first-week thoughts.',
            },
            secure=True,
        )
        early_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {
                'submit_book_review': '1',
                'week_number': '2',
                'review': 'This week has not started yet.',
            },
            secure=True,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(update_response.status_code, 302)
        self.assertEqual(early_response.status_code, 200)
        review = PodBookReview.objects.get(book=book, user=self.member, week_number=1)
        self.assertEqual(review.review, 'My updated first-week thoughts.')
        self.assertEqual(PodBookReview.objects.filter(book=book, user=self.member).count(), 1)

    def test_pod_members_can_track_lagging_reviews_and_reply_to_review_threads(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        lagging_member = CustomUser.objects.create_user(
            username='pod-lagging-member',
            password='test-password',
        )
        PodMember.objects.create(pod=self.pod, user=lagging_member, role='MEMBER')
        book = PodBook.objects.create(
            pod=self.pod,
            title='A Book for the Pod',
            document=SimpleUploadedFile('pod-book.pdf', b'%PDF-book-content'),
            duration_weeks=3,
            started_on=timezone.localdate() - timedelta(days=8),
            assigned_by=self.leader,
        )
        review = PodBookReview.objects.create(
            book=book,
            user=self.member,
            week_number=1,
            review='This chapter helped me understand the topic.',
        )
        comment_url = reverse(
            'pod_book_review_comment',
            args=[self.pod.pk, book.pk, review.pk],
        )
        self.client.force_login(self.member)
        comment_response = self.client.post(
            comment_url,
            {'body': 'Thanks for sharing this.'},
            secure=True,
        )
        comment = PodBookReviewComment.objects.get(review=review)

        self.client.force_login(self.leader)
        reply_response = self.client.post(
            comment_url,
            {'body': 'Glad it was helpful.', 'parent_id': str(comment.pk)},
            secure=True,
        )
        self.assertEqual(comment_response.status_code, 302)
        self.assertEqual(reply_response.status_code, 302)
        self.assertTrue(PodBookReviewComment.objects.filter(parent=comment).exists())

        self.client.force_login(lagging_member)
        detail_response = self.client.get(
            reverse('pod_detail', args=[self.pod.pk]),
            secure=True,
        )
        week_progress = {
            entry['user'].username: entry['review_status']
            for entry in detail_response.context['book_weeks'][0]['member_progress']
        }
        self.assertEqual(week_progress['pod-member'], 'reviewed')
        self.assertEqual(week_progress['pod-lagging-member'], 'behind')
        self.assertContains(detail_response, 'This chapter helped me understand the topic.')
        self.assertContains(detail_response, 'Thanks for sharing this.')
        self.assertContains(detail_response, 'Glad it was helpful.')

    def test_oversight_mentor_cannot_comment_on_book_reviews(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        book = PodBook.objects.create(
            pod=self.pod,
            title='A Book for the Pod',
            document=SimpleUploadedFile('pod-book.pdf', b'%PDF-book-content'),
            assigned_by=self.leader,
        )
        review = PodBookReview.objects.create(
            book=book,
            user=self.member,
            week_number=1,
            review='A weekly review.',
        )
        mentor = CustomUser.objects.create_user(
            username='pod-oversight-reader',
            password='test-password',
        )
        ApprenticeOversight.objects.create(mentor=mentor, apprentice_pod=self.pod)
        self.client.force_login(mentor)

        response = self.client.post(
            reverse('pod_book_review_comment', args=[self.pod.pk, book.pk, review.pk]),
            {'body': 'This should remain read-only.'},
            secure=True,
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PodBookReviewComment.objects.exists())

    def test_only_pod_participants_can_download_book(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        book = PodBook.objects.create(
            pod=self.pod,
            title='A Book for the Pod',
            document=SimpleUploadedFile('pod-book.pdf', b'%PDF-book-content'),
            assigned_by=self.leader,
        )
        outsider = CustomUser.objects.create_user(
            username='pod-book-outsider',
            password='test-password',
        )
        url = reverse('pod_book_file', args=[self.pod.pk, book.pk])

        self.client.force_login(self.member)
        allowed_response = self.client.get(url, secure=True)
        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(b''.join(allowed_response.streaming_content), b'%PDF-book-content')

        self.client.force_login(outsider)
        denied_response = self.client.get(url, secure=True)
        self.assertEqual(denied_response.status_code, 403)

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

    def test_pod_leader_can_rotate_code_and_user_can_join_with_it(self):
        old_code = self.pod.join_code
        self.client.force_login(self.leader)

        detail_response = self.client.get(
            reverse('pod_detail', args=[self.pod.pk]),
            secure=True,
        )
        rotate_response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'rotate_join_code': '1'},
            secure=True,
        )
        self.pod.refresh_from_db()

        self.assertContains(detail_response, old_code)
        self.assertEqual(rotate_response.status_code, 302)
        self.assertNotEqual(self.pod.join_code, old_code)

        joiner = CustomUser.objects.create_user(
            username='pod-code-joiner',
            password='test-password',
        )
        self.client.force_login(joiner)
        join_response = self.client.post(
            reverse('pod_join'),
            {'code': self.pod.join_code},
            secure=True,
        )

        self.assertRedirects(
            join_response,
            reverse('pod_detail', args=[self.pod.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            PodMember.objects.filter(pod=self.pod, user=joiner, role='MEMBER').exists()
        )

    def test_non_manager_cannot_rotate_pod_join_code(self):
        join_code = self.pod.join_code
        self.client.force_login(self.member)

        response = self.client.post(
            reverse('pod_detail', args=[self.pod.pk]),
            {'rotate_join_code': '1'},
            secure=True,
        )

        self.assertEqual(response.status_code, 403)
        self.pod.refresh_from_db()
        self.assertEqual(self.pod.join_code, join_code)

    def test_only_admin_can_delete_pod_and_related_data(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        course = Course.objects.create(title='Pod course', pod=self.pod)
        module = Module.objects.create(course=course, title='Pod module')
        lesson = Lesson.objects.create(
            title='Pod lesson',
            content='Lesson content.',
            module=module,
            created_by=self.leader,
        )
        lesson.audio_file.save(
            'pod-lesson.mp3',
            SimpleUploadedFile('pod-lesson.mp3', b'audio-content', content_type='audio/mpeg'),
        )
        audio_path = Path(lesson.audio_file.path)
        book = PodBook.objects.create(
            pod=self.pod,
            title='Pod book',
            document=SimpleUploadedFile('pod-book.pdf', b'%PDF-book-content'),
            assigned_by=self.leader,
        )
        book_path = Path(book.document.path)
        PodMessage.objects.create(pod=self.pod, author=self.member, body='Pod message')
        admin = CustomUser.objects.create_user(
            username='pod-delete-admin',
            password='test-password',
            is_staff=True,
        )

        self.client.force_login(self.leader)
        denied_response = self.client.post(
            reverse('pod_delete', args=[self.pod.pk]),
            secure=True,
        )
        self.assertEqual(denied_response.status_code, 403)
        self.assertTrue(Pod.objects.filter(pk=self.pod.pk).exists())

        self.client.force_login(admin)
        detail_response = self.client.get(
            reverse('pod_detail', args=[self.pod.pk]),
            secure=True,
        )
        delete_response = self.client.post(
            reverse('pod_delete', args=[self.pod.pk]),
            secure=True,
        )

        self.assertContains(detail_response, 'Delete Pod permanently')
        self.assertContains(detail_response, 'data-confirm-delete')
        self.assertRedirects(
            delete_response,
            reverse('pod_list'),
            fetch_redirect_response=False,
        )
        self.assertFalse(Pod.objects.filter(pk=self.pod.pk).exists())
        self.assertFalse(Course.objects.filter(pk=course.pk).exists())
        self.assertFalse(Lesson.objects.filter(pk=lesson.pk).exists())
        self.assertFalse(audio_path.exists())
        self.assertFalse(book_path.exists())
