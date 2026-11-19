from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from .models import ContentReport, Question, Reply


class CommunityQuestionTests(TestCase):
    def setUp(self):
        self.member = CustomUser.objects.create_user(
            username='community-member',
            password='test-password',
        )

    def test_guest_can_post_named_or_anonymous_public_question(self):
        response = self.client.post(
            reverse('question_create'),
            {
                'title': 'A public question',
                'body': 'What is the next step?',
                'display_name': 'Curious guest',
                'is_anonymous': '',
            },
            secure=True,
        )

        question = Question.objects.get()
        self.assertRedirects(
            response,
            reverse('question_detail', args=[question.pk]),
            fetch_redirect_response=False,
        )
        self.assertIsNone(question.author)
        self.assertEqual(question.public_author, 'Curious guest')
        self.assertContains(
            self.client.get(reverse('question_list'), secure=True),
            'A public question',
        )

    def test_signed_in_anonymous_question_retains_private_author(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse('question_create'),
            {
                'title': 'Anonymous member question',
                'body': 'A question for the community.',
                'is_anonymous': 'on',
            },
            secure=True,
        )

        question = Question.objects.get()
        detail = self.client.get(reverse('question_detail', args=[question.pk]), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(question.author, self.member)
        self.assertTrue(question.is_anonymous)
        self.assertContains(detail, 'Anonymous')
        self.client.logout()
        public_detail = self.client.get(
            reverse('question_detail', args=[question.pk]),
            secure=True,
        )
        self.assertNotContains(public_detail, self.member.username)

    def test_only_signed_in_users_can_reply_and_they_choose_reply_anonymity(self):
        question = Question.objects.create(title='Open question', body='Question body.')

        guest_response = self.client.post(
            reverse('reply_create', args=[question.pk]),
            {'body': 'Guest reply'},
            secure=True,
        )
        self.assertEqual(guest_response.status_code, 302)
        self.assertFalse(Reply.objects.exists())

        self.client.force_login(self.member)
        response = self.client.post(
            reverse('reply_create', args=[question.pk]),
            {'body': 'Private-name reply', 'is_anonymous': 'on'},
            secure=True,
        )

        reply = Reply.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(reply.author, self.member)
        self.assertTrue(reply.is_anonymous)
        self.assertContains(
            self.client.get(reverse('question_detail', args=[question.pk]), secure=True),
            'Anonymous',
        )

    def test_signed_in_user_can_reply_to_an_existing_reply(self):
        question = Question.objects.create(title='Open question', body='Question body.')
        parent = Reply.objects.create(
            question=question,
            author=self.member,
            display_name=self.member.username,
            body='First reply',
        )
        self.client.force_login(self.member)

        response = self.client.post(
            reverse('reply_create', args=[question.pk]),
            {
                'parent_id': str(parent.pk),
                'body': 'Nested anonymous reply',
                'is_anonymous': 'on',
            },
            secure=True,
        )

        child = Reply.objects.get(parent=parent)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(child.question, question)
        self.assertTrue(child.is_anonymous)
        detail = self.client.get(reverse('question_detail', args=[question.pk]), secure=True)
        self.assertContains(detail, 'First reply')
        self.assertContains(detail, 'Nested anonymous reply')

    def test_report_requires_login_and_is_available_for_questions_and_replies(self):
        question = Question.objects.create(title='Reportable question', body='Question body.')
        reply = Reply.objects.create(
            question=question,
            author=self.member,
            display_name=self.member.username,
            body='Reportable reply',
        )
        guest_response = self.client.post(
            reverse('question_report', args=[question.pk]),
            {'reason': 'Needs review'},
            secure=True,
        )
        self.assertEqual(guest_response.status_code, 302)
        self.assertFalse(ContentReport.objects.exists())

        self.client.force_login(self.member)
        self.client.post(
            reverse('question_report', args=[question.pk]),
            {'reason': 'Needs review'},
            secure=True,
        )
        self.client.post(
            reverse('question_report', args=[question.pk]),
            {'reason': 'Duplicate report'},
            secure=True,
        )
        self.client.post(
            reverse('reply_report', args=[reply.pk]),
            {'reason': 'Needs review'},
            secure=True,
        )

        self.assertEqual(ContentReport.objects.count(), 2)
        self.assertEqual(ContentReport.objects.filter(question=question).count(), 1)
        self.assertEqual(ContentReport.objects.filter(reply=reply).count(), 1)

    def test_hidden_questions_and_replies_are_not_public(self):
        question = Question.objects.create(
            title='Hidden question',
            body='Hidden body',
            is_hidden=True,
        )
        visible_question = Question.objects.create(title='Visible question', body='Visible body')
        hidden_reply = Reply.objects.create(
            question=visible_question,
            author=self.member,
            display_name=self.member.username,
            body='Hidden reply',
            is_hidden=True,
        )

        self.assertEqual(
            self.client.get(reverse('question_detail', args=[question.pk]), secure=True).status_code,
            404,
        )
        response = self.client.get(reverse('question_detail', args=[visible_question.pk]), secure=True)
        self.assertNotContains(response, hidden_reply.body)
