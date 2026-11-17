import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from .ai import LessonAIError, generate_lesson_suggestions
from .models import (
    Course,
    CourseCertificate,
    Lesson,
    LessonProgress,
    Module,
    ModuleQuiz,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
)
from .structure import structure_lesson
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

    def test_leader_can_upload_word_lesson_and_publish_converted_pdf(self):
        self.client.force_login(self.leader)
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        word_document = SimpleUploadedFile(
            'baptism-with-the-holy-spirit.docx',
            b'word-document',
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

        with patch(
            'curriculum.views.convert_word_document',
            return_value=(b'%PDF-test-content', 'Baptism with the Holy Spirit\nLesson text'),
        ) as convert_document:
            response = self.client.post(
                reverse('lesson_create'),
                {
                    'title': 'Baptism with the Holy Spirit and with Fire',
                    'description': 'A lesson about the Spirit and fire.',
                    'word_document': word_document,
                    'is_master_template': 'on',
                },
                secure=True,
            )

        self.assertRedirects(response, reverse('lesson_list'), fetch_redirect_response=False)
        convert_document.assert_called_once()
        lesson = Lesson.objects.get(title='Baptism with the Holy Spirit and with Fire')
        self.assertEqual(lesson.content, 'Baptism with the Holy Spirit\nLesson text')
        self.assertTrue(lesson.is_master_template)
        self.assertTrue(lesson.pdf_resource.name.endswith('.pdf'))
        self.assertEqual(
            Path(lesson.pdf_resource.path).read_bytes(),
            b'%PDF-test-content',
        )

    def test_lesson_assistant_extracts_word_text_and_checks_sections_without_ai(self):
        self.client.force_login(self.leader)
        document = SimpleUploadedFile(
            'lesson.docx',
            b'word-document',
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        content = (
            'Text: Matthew 3:11  Proposition: Our purpose is described.  '
            'Introduction The lesson begins.  OUTLINES  1. The first outline: '
            'Teaching details.  Conclusion The lesson concludes.'
        )

        with (
            patch('curriculum.views.convert_word_document', return_value=(b'%PDF', content)),
            patch(
                'curriculum.views.generate_lesson_suggestions',
                side_effect=LessonAIError('Local AI is not configured.'),
            ),
        ):
            response = self.client.post(
                reverse('lesson_assist'),
                {'content': '', 'word_document': document},
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['extracted_text'], content)
        self.assertTrue(result['is_structured'])
        self.assertEqual(result['missing_sections'], [])
        self.assertFalse(result['ai_available'])
        self.assertEqual(
            [section['heading'] for section in result['sections']],
            ['Scripture', 'Proposition', 'Introduction', '1. The first outline', 'Conclusion'],
        )

    def test_non_leader_cannot_use_lesson_assistant(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse('lesson_assist'),
            {'content': 'Private lesson text'},
            secure=True,
        )

        self.assertEqual(response.status_code, 403)


class LessonStructureTests(TestCase):
    def test_unlabeled_content_is_preserved_and_required_sections_are_reported(self):
        result = structure_lesson('Opening note.  Introduction Start here.')

        self.assertEqual(result['sections'][0]['heading'], 'Lesson notes')
        self.assertEqual(result['sections'][0]['body'], 'Opening note.')
        self.assertEqual(
            result['missing_sections'],
            ['Scripture', 'Proposition', 'Outline', 'Conclusion'],
        )


class LocalLessonAITests(TestCase):
    @override_settings(OLLAMA_BASE_URL='')
    def test_ai_not_configured_is_reported_without_network_request(self):
        with self.assertRaisesMessage(LessonAIError, 'not configured'):
            generate_lesson_suggestions('A lesson about prayer.')

    @override_settings(
        OLLAMA_BASE_URL='http://ollama:11434',
        OLLAMA_MODEL='qwen2.5:1.5b',
        OLLAMA_TIMEOUT=5,
    )
    def test_ai_suggestions_are_parsed_and_limited(self):
        response_body = json.dumps({
            'response': json.dumps({
                'summary': 'A short lesson summary.',
                'discussion_questions': ['Question one?', 'Question two?'],
            }),
        }).encode()

        with patch('curriculum.ai.urlopen', return_value=BytesIO(response_body)) as open_url:
            result = generate_lesson_suggestions('A lesson about prayer.')

        self.assertEqual(result['summary'], 'A short lesson summary.')
        self.assertEqual(result['discussion_questions'], ['Question one?', 'Question two?'])
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, 'http://ollama:11434/api/generate')
        self.assertIn(b'qwen2.5:1.5b', request.data)


class CourseLearningFlowTests(TestCase):
    def setUp(self):
        self.learner = CustomUser.objects.create_user(
            username='course-learner',
            password='test-password',
        )
        self.leader = CustomUser.objects.create_user(
            username='course-leader',
            password='test-password',
        )
        self.leader_pod = Pod.objects.create(name='Leader Course Pod', leader=self.leader)
        self.course = Course.objects.create(
            title='Foundations of Discipleship',
            description='A structured course.',
            created_by=self.leader,
            is_published=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Module One',
            order=1,
        )
        self.lesson_one = Lesson.objects.create(
            title='Lesson One',
            content='First lesson content.',
            module=self.module,
            is_master_template=True,
            created_by=self.leader,
        )
        self.lesson_two = Lesson.objects.create(
            title='Lesson Two',
            content='Second lesson content.',
            module=self.module,
            is_master_template=True,
            created_by=self.leader,
            order=2,
        )
        self.quiz = ModuleQuiz.objects.create(
            module=self.module,
            title='Module One Quiz',
            passing_score=50,
        )
        self.question = QuizQuestion.objects.create(
            quiz=self.quiz,
            prompt='Which lesson is first?',
        )
        self.correct_choice = QuizChoice.objects.create(
            question=self.question,
            text='Lesson One',
            is_correct=True,
        )
        self.wrong_choice = QuizChoice.objects.create(
            question=self.question,
            text='Lesson Two',
            is_correct=False,
            order=1,
        )
        self.client.force_login(self.learner)

    def test_published_course_shows_modules_lessons_and_progress(self):
        response = self.client.get(
            reverse('course_detail', args=[self.course.pk]),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Foundations of Discipleship')
        self.assertContains(response, 'Module One')
        self.assertContains(response, 'Lesson One')
        self.assertContains(response, '0% complete')

    def test_course_lesson_has_sidebar_completion_and_next_lesson_navigation(self):
        response = self.client.get(
            reverse('lesson_detail', args=[self.lesson_one.pk]),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Foundations of Discipleship')
        self.assertContains(response, 'Mark lesson complete')
        self.assertContains(response, reverse('lesson_detail', args=[self.lesson_two.pk]))

    def test_leader_can_create_a_course_and_module(self):
        self.client.force_login(self.leader)
        response = self.client.post(
            reverse('course_create'),
            {
                'title': 'New Foundations Course',
                'description': 'Course summary',
                'pod': str(self.leader_pod.pk),
                'order': '1',
                'is_published': 'on',
            },
            secure=True,
        )

        new_course = Course.objects.get(title='New Foundations Course')
        self.assertRedirects(
            response,
            reverse('course_detail', args=[new_course.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(new_course.pod, self.leader_pod)

        module_response = self.client.post(
            reverse('module_create', args=[new_course.pk]),
            {'title': 'First Module', 'description': '', 'order': '1'},
            secure=True,
        )
        self.assertRedirects(
            module_response,
            reverse('course_detail', args=[new_course.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(new_course.modules.filter(title='First Module').exists())

    def test_learner_can_render_quiz_and_course_manager_cannot_be_used_by_learner(self):
        LessonProgress.objects.create(user=self.learner, lesson=self.lesson_one)
        LessonProgress.objects.create(user=self.learner, lesson=self.lesson_two)

        quiz_response = self.client.get(
            reverse('quiz', args=[self.module.pk]),
            secure=True,
        )
        manager_response = self.client.get(
            reverse('quiz_manage', args=[self.module.pk]),
            secure=True,
        )

        self.assertEqual(quiz_response.status_code, 200)
        self.assertContains(quiz_response, 'Which lesson is first?')
        self.assertEqual(manager_response.status_code, 403)

    def test_unpublished_course_is_hidden_from_other_learners(self):
        self.course.is_published = False
        self.course.save()

        response = self.client.get(
            reverse('course_detail', args=[self.course.pk]),
            secure=True,
        )

        self.assertEqual(response.status_code, 403)

    def test_course_certificate_requires_all_lessons_and_a_passed_quiz(self):
        self.client.post(
            reverse('lesson_complete', args=[self.lesson_one.pk]),
            secure=True,
        )
        self.assertFalse(CourseCertificate.objects.filter(user=self.learner, course=self.course).exists())
        locked_response = self.client.get(
            reverse('quiz', args=[self.module.pk]),
            secure=True,
        )
        self.assertRedirects(
            locked_response,
            reverse('course_detail', args=[self.course.pk]),
            fetch_redirect_response=False,
        )
        self.client.post(
            reverse('lesson_complete', args=[self.lesson_two.pk]),
            secure=True,
        )
        self.client.post(
            reverse('quiz', args=[self.module.pk]),
            {f'question_{self.question.pk}': self.wrong_choice.pk},
            secure=True,
        )
        self.assertFalse(CourseCertificate.objects.filter(user=self.learner, course=self.course).exists())

        self.client.post(
            reverse('quiz', args=[self.module.pk]),
            {f'question_{self.question.pk}': self.correct_choice.pk},
            secure=True,
        )
        self.assertTrue(CourseCertificate.objects.filter(user=self.learner, course=self.course).exists())
        self.assertEqual(LessonProgress.objects.filter(user=self.learner).count(), 2)
        certificate_response = self.client.get(
            reverse('certificate', args=[self.course.pk]),
            secure=True,
        )
        self.assertEqual(certificate_response.status_code, 200)
        self.assertContains(certificate_response, 'Certificate of Completion')

    def test_quiz_is_locked_until_module_lessons_are_completed(self):
        response = self.client.get(
            reverse('quiz', args=[self.module.pk]),
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('course_detail', args=[self.course.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(QuizAttempt.objects.filter(user=self.learner, quiz=self.quiz).exists())

    def test_course_leader_can_create_quiz_question(self):
        self.client.force_login(self.leader)
        response = self.client.post(
            reverse('quiz_manage', args=[self.module.pk]),
            {
                'add_question': '1',
                'question-prompt': 'What is the first lesson?',
                'question-choice_1': 'Lesson One',
                'question-choice_2': 'Lesson Two',
                'question-choice_3': 'Lesson Three',
                'question-choice_4': 'Lesson Four',
                'question-correct_choice': '1',
            },
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('quiz_manage', args=[self.module.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(self.quiz.questions.filter(prompt='What is the first lesson?').exists())
