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

    def test_guest_must_sign_in_to_open_or_post_a_question(self):
        create_url = reverse('question_create')

        get_response = self.client.get(create_url, secure=True)
        post_response = self.client.post(
            create_url,
            {
                'title': 'A public question',
                'body': 'What is the next step?',
            },
            secure=True,
        )

        self.assertRedirects(
            get_response,
            f'{reverse("login")}?next={create_url}',
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            post_response,
            f'{reverse("login")}?next={create_url}',
            fetch_redirect_response=False,
        )
        self.assertFalse(Question.objects.exists())

    def test_guest_is_guided_back_to_question_form_after_sign_in(self):
        create_url = reverse('question_create')
        login_page = self.client.get(create_url, secure=True, follow=True)

        self.assertContains(login_page, f'name="next" value="{create_url}"')

        response = self.client.post(
            reverse('login'),
            {
                'username': self.member.username,
                'password': 'test-password',
                'next': create_url,
            },
            secure=True,
        )

        self.assertRedirects(response, create_url, fetch_redirect_response=False)

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

    def test_author_can_delete_question_and_reply(self):
        self.client.force_login(self.member)
        question = Question.objects.create(
            title='Own question',
            body='Own body',
            author=self.member,
        )
        reply = Reply.objects.create(
            question=question,
            author=self.member,
            display_name=self.member.username,
            body='Own reply',
        )

        reply_response = self.client.post(
            reverse('reply_delete', args=[reply.pk]),
            {'confirm_action': 'yes'},
            secure=True,
        )
        self.assertRedirects(
            reply_response,
            reverse('question_detail', args=[question.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(Reply.objects.filter(pk=reply.pk).exists())

        question_response = self.client.post(
            reverse('question_delete', args=[question.pk]),
            {'confirm_action': 'yes'},
            secure=True,
        )
        self.assertRedirects(
            question_response,
            reverse('question_list'),
            fetch_redirect_response=False,
        )
        self.assertFalse(Question.objects.filter(pk=question.pk).exists())

    def test_delete_requires_server_confirmation_without_javascript(self):
        self.client.force_login(self.member)
        question = Question.objects.create(
            title='Question requiring confirmation',
            body='Question body',
            author=self.member,
        )
        url = reverse('question_delete', args=[question.pk])

        confirmation = self.client.post(url, secure=True)

        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, 'This action cannot be undone.')
        self.assertTrue(Question.objects.filter(pk=question.pk).exists())

        response = self.client.post(url, {'confirm_action': 'yes'}, secure=True)

        self.assertRedirects(
            response,
            reverse('question_list'),
            fetch_redirect_response=False,
        )
        self.assertFalse(Question.objects.filter(pk=question.pk).exists())

    def test_user_cannot_delete_another_users_content(self):
        other = CustomUser.objects.create_user(
            username='other-member',
            password='test-password',
        )
        question = Question.objects.create(
            title='Other question',
            body='Other body',
            author=other,
        )
        reply = Reply.objects.create(
            question=question,
            author=other,
            display_name=other.username,
            body='Other reply',
        )
        self.client.force_login(self.member)

        question_response = self.client.post(
            reverse('question_delete', args=[question.pk]),
            secure=True,
            follow=True,
        )
        reply_response = self.client.post(
            reverse('reply_delete', args=[reply.pk]),
            secure=True,
            follow=True,
        )

        self.assertTrue(Question.objects.filter(pk=question.pk).exists())
        self.assertTrue(Reply.objects.filter(pk=reply.pk).exists())
        self.assertContains(question_response, 'You can only delete your own question.')
        self.assertContains(reply_response, 'You can only delete your own reply.')
