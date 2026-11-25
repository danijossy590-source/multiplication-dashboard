import json
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from .ai import LessonAIError, generate_course_plan, generate_lesson_suggestions
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
        self.pod = Pod.objects.create(name='Curriculum Pod', leader=self.leader)
        PodMember.objects.create(pod=self.pod, user=self.leader, role='LEADER')
        PodMember.objects.create(pod=self.pod, user=self.member, role='MEMBER')

    def test_regular_member_does_not_see_upload_lesson_action(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('lesson_list'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Upload New Lesson')
        self.assertNotContains(response, 'Create Progressive Course')

    def test_pod_leader_sees_upload_lesson_action(self):
        self.client.force_login(self.leader)

        response = self.client.get(reverse('lesson_list'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload New Lesson')
        self.assertContains(response, 'Create Progressive Course')

    def test_pod_course_lessons_appear_in_curriculum_before_publication(self):
        course = Course.objects.create(
            title='Pod Reading Course',
            pod=self.pod,
            created_by=self.leader,
            is_published=False,
        )
        module = Module.objects.create(course=course, title='Pod Module')
        lesson = Lesson.objects.create(
            title='Lesson Uploaded to Pod',
            content='Pod lesson content.',
            module=module,
            pod=self.pod,
            created_by=self.leader,
        )
        self.client.force_login(self.member)

        library_response = self.client.get(reverse('lesson_list'), secure=True)
        course_response = self.client.get(
            reverse('course_detail', args=[course.pk]),
            secure=True,
        )

        self.assertContains(library_response, 'Pod Reading Course')
        self.assertEqual(course_response.status_code, 200)
        self.assertContains(course_response, lesson.title)

    def test_admin_curriculum_lists_every_lesson_counted_on_dashboard(self):
        admin = CustomUser.objects.create_user(
            username='curriculum-admin',
            password='test-password',
            is_staff=True,
        )
        standalone = Lesson.objects.create(
            title='Standalone lesson',
            content='Standalone content.',
            created_by=self.leader,
            is_master_template=True,
        )
        course = Course.objects.create(
            title='Admin course',
            pod=self.pod,
            created_by=self.leader,
            is_published=False,
        )
        module = Module.objects.create(course=course, title='Admin module')
        course_lesson = Lesson.objects.create(
            title='Lesson inside course',
            content='Course content.',
            module=module,
            pod=self.pod,
            created_by=self.leader,
        )
        pod_lesson = Lesson.objects.create(
            title='Standalone Pod lesson',
            content='Pod content.',
            pod=self.pod,
            created_by=self.leader,
        )
        self.client.force_login(admin)

        curriculum_response = self.client.get(reverse('lesson_list'), secure=True)
        dashboard_response = self.client.get(reverse('admin_dashboard'), secure=True)

        self.assertEqual(curriculum_response.status_code, 200)
        self.assertEqual(dashboard_response.context['total_lessons'], Lesson.objects.count())
        self.assertEqual(
            len(curriculum_response.context['all_lessons']),
            dashboard_response.context['total_lessons'],
        )
        self.assertContains(curriculum_response, 'All Lessons')
        for lesson in (standalone, course_lesson, pod_lesson):
            self.assertContains(curriculum_response, lesson.title)

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
        self.assertIn('Click Try again.', result['ai_message'])
        self.assertIn('ask an admin to check the AI settings', result['ai_message'])
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


class LessonManagementTests(TestCase):
    def setUp(self):
        self.creator = CustomUser.objects.create_user(
            username='lesson-creator',
            password='test-password',
        )
        self.other_user = CustomUser.objects.create_user(
            username='lesson-other-user',
            password='test-password',
        )
        self.lesson = Lesson.objects.create(
            title='Uploaded lesson',
            description='Original summary',
            content='Original lesson content.',
            created_by=self.creator,
            is_master_template=True,
        )

    def test_creator_can_edit_uploaded_lesson(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse('lesson_edit', args=[self.lesson.pk]),
            {
                'title': 'Updated lesson',
                'description': 'Updated summary',
                'content': 'Updated lesson content.',
                'discussion_questions': 'What did you learn?',
                'is_master_template': 'on',
                'module': '',
                'order': '1',
            },
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('lesson_detail', args=[self.lesson.pk]),
            fetch_redirect_response=False,
        )
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.title, 'Updated lesson')
        self.assertEqual(self.lesson.content, 'Updated lesson content.')
        self.assertEqual(self.lesson.order, 1)

    def test_unrelated_user_cannot_edit_or_delete_lesson(self):
        self.client.force_login(self.other_user)

        edit_response = self.client.get(
            reverse('lesson_edit', args=[self.lesson.pk]),
            secure=True,
        )
        delete_response = self.client.post(
            reverse('lesson_delete', args=[self.lesson.pk]),
            secure=True,
        )

        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())

    def test_creator_can_delete_uploaded_lesson(self):
        self.client.force_login(self.creator)

        url = reverse('lesson_delete', args=[self.lesson.pk])
        confirmation = self.client.post(
            url,
            secure=True,
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())

        response = self.client.post(
            url,
            {'confirm_action': 'yes'},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('lesson_list'),
            fetch_redirect_response=False,
        )
        self.assertFalse(Lesson.objects.filter(pk=self.lesson.pk).exists())

    def test_edit_form_preserves_existing_attachments_and_detail_shows_controls(self):
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)
        settings_override = override_settings(MEDIA_ROOT=media_directory.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.lesson.audio_file.save(
            'lesson.mp3',
            SimpleUploadedFile('lesson.mp3', b'audio-content', content_type='audio/mpeg'),
        )
        self.lesson.pdf_resource.save(
            'lesson.pdf',
            SimpleUploadedFile('lesson.pdf', b'%PDF-content', content_type='application/pdf'),
        )
        self.client.force_login(self.creator)

        detail_response = self.client.get(
            reverse('lesson_detail', args=[self.lesson.pk]),
            secure=True,
        )
        edit_response = self.client.post(
            reverse('lesson_edit', args=[self.lesson.pk]),
            {
                'title': 'Updated lesson',
                'description': 'Updated summary',
                'content': 'Updated lesson content.',
                'discussion_questions': '',
                'is_master_template': 'on',
                'module': '',
                'order': '0',
            },
            secure=True,
        )

        self.assertContains(detail_response, 'Edit lesson')
        self.assertContains(detail_response, 'Delete lesson')
        self.assertContains(detail_response, 'data-confirm-delete')
        self.assertRedirects(
            edit_response,
            reverse('lesson_detail', args=[self.lesson.pk]),
            fetch_redirect_response=False,
        )
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.audio_file)
        self.assertTrue(self.lesson.pdf_resource)
        audio_path = Path(self.lesson.audio_file.path)
        pdf_path = Path(self.lesson.pdf_resource.path)
        shared_lesson = Lesson.objects.create(
            title='Lesson sharing attachments',
            content='Shared attachment content.',
            created_by=self.creator,
            audio_file=self.lesson.audio_file.name,
            pdf_resource=self.lesson.pdf_resource.name,
        )

        self.client.post(
            reverse('lesson_delete', args=[self.lesson.pk]),
            {'confirm_action': 'yes'},
            secure=True,
        )
        self.assertTrue(audio_path.exists())
        self.assertTrue(pdf_path.exists())

        self.client.post(
            reverse('lesson_delete', args=[shared_lesson.pk]),
            {'confirm_action': 'yes'},
            secure=True,
        )
        self.assertFalse(audio_path.exists())
        self.assertFalse(pdf_path.exists())


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
    def _course_source_and_plan(self):
        source = [{
            'id': 42,
            'title': 'A selected lesson',
            'description': 'A short source lesson.',
            'content': 'This lesson explains a single supported concept.',
        }]
        plan = {
            'course_title': 'A generated course',
            'course_description': 'A factual description based on the source.',
            'modules': [{
                'title': 'The core idea',
                'description': '',
                'learning_objectives': ['Describe the core idea.', 'Recognize it in an example.'],
                'learning_steps': ['Read the lesson.', 'Review its example.'],
                'lesson_ids': [42],
                'quiz_title': 'Core idea check',
                'quiz_questions': [{
                    'prompt': 'What does the lesson explain?',
                    'choices': ['The core concept', 'An unrelated concept', 'A new claim', 'An outside source'],
                    'correct_choice': 0,
                }, {
                    'prompt': 'What should the learner review?',
                    'choices': ['The example', 'Unrelated material', 'An outside source', 'No material'],
                    'correct_choice': 0,
                }],
            }],
        }
        return source, plan

    @override_settings(AI_PROVIDER='ollama', OLLAMA_BASE_URL='')
    def test_ai_not_configured_is_reported_without_network_request(self):
        with self.assertRaisesMessage(LessonAIError, 'not configured'):
            generate_lesson_suggestions('A lesson about prayer.')

    @override_settings(
        AI_PROVIDER='ollama',
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

    @override_settings(
        AI_PROVIDER='gemini',
        GEMINI_API_KEY='test-api-key',
        GEMINI_MODEL='gemini-test',
        GEMINI_TIMEOUT=5,
    )
    def test_gemini_suggestions_are_parsed_and_authenticated(self):
        response_body = json.dumps({
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': json.dumps({
                            'summary': 'A short lesson summary.',
                            'discussion_questions': ['Question one?', 'Question two?'],
                        }),
                    }],
                },
            }],
        }).encode()

        with patch('curriculum.ai.urlopen', return_value=BytesIO(response_body)) as open_url:
            result = generate_lesson_suggestions('A lesson about prayer.')

        self.assertEqual(result['summary'], 'A short lesson summary.')
        self.assertEqual(result['discussion_questions'], ['Question one?', 'Question two?'])
        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url,
            'https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent',
        )
        self.assertEqual(request.get_header('X-goog-api-key'), 'test-api-key')
        self.assertIn(b'responseMimeType', request.data)

    @override_settings(AI_PROVIDER='gemini', GEMINI_API_KEY='')
    def test_gemini_without_api_key_is_reported_without_network_request(self):
        with patch('curriculum.ai.urlopen') as open_url:
            with self.assertRaisesMessage(LessonAIError, 'Gemini is not configured'):
                generate_lesson_suggestions('A lesson about prayer.')

        open_url.assert_not_called()

    @override_settings(AI_PROVIDER='gemini', GEMINI_API_KEY='test-api-key')
    def test_gemini_retries_temporary_service_unavailable_responses(self):
        error = HTTPError(
            'https://generativelanguage.googleapis.com/',
            503,
            'Service unavailable',
            {},
            BytesIO(),
        )
        response_body = json.dumps({
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': json.dumps({
                            'summary': 'A short lesson summary.',
                            'discussion_questions': ['Question one?'],
                        }),
                    }],
                },
            }],
        }).encode()

        with (
            patch('curriculum.ai.urlopen', side_effect=[error, BytesIO(response_body)]) as open_url,
            patch('curriculum.ai.time.sleep') as sleep,
        ):
            result = generate_lesson_suggestions('A lesson about prayer.')

        self.assertEqual(result['summary'], 'A short lesson summary.')
        self.assertEqual(open_url.call_count, 2)
        sleep.assert_called_once_with(1)

        with (
            patch('curriculum.ai.urlopen', side_effect=error) as open_url,
            patch('curriculum.ai.time.sleep') as sleep,
        ):
            with self.assertRaisesMessage(LessonAIError, 'Gemini returned HTTP 503'):
                generate_lesson_suggestions('A lesson about prayer.')

        self.assertEqual(open_url.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    @override_settings(AI_PROVIDER='gemini', GEMINI_API_KEY='test-api-key')
    def test_gemini_http_errors_identify_model_key_and_quota_problems(self):
        cases = [
            (404, 'could not find the configured model'),
            (403, 'rejected the API key or request'),
            (429, 'rate or quota limit reached'),
        ]
        for status_code, expected_message in cases:
            with self.subTest(status_code=status_code):
                error = HTTPError(
                    'https://generativelanguage.googleapis.com/',
                    status_code,
                    'Request failed',
                    {},
                    BytesIO(),
                )
                with patch('curriculum.ai.urlopen', side_effect=error):
                    with self.assertRaisesMessage(LessonAIError, expected_message):
                        generate_lesson_suggestions('A lesson about prayer.')

    @override_settings(
        AI_PROVIDER='openrouter',
        OPENROUTER_API_KEY='test-openrouter-key',
        OPENROUTER_MODEL='test/provider-model',
        OPENROUTER_BASE_URL='https://openrouter.test/api/v1',
        OPENROUTER_TIMEOUT=17,
        OPENROUTER_SITE_URL='https://multiply.example',
        OPENROUTER_APP_NAME='Multiply test',
    )
    def test_openrouter_suggestions_use_chat_completions_and_attribution(self):
        response_body = json.dumps({
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': 'A factual summary.',
                        'discussion_questions': ['Question one?', 'Question two?'],
                    }),
                },
            }],
        }).encode()

        with patch('curriculum.ai.urlopen', return_value=BytesIO(response_body)) as open_url:
            result = generate_lesson_suggestions('A lesson about service.')

        self.assertEqual(result['summary'], 'A factual summary.')
        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://openrouter.test/api/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-openrouter-key')
        self.assertEqual(request.get_header('Http-referer'), 'https://multiply.example')
        self.assertEqual(request.get_header('X-title'), 'Multiply test')
        self.assertEqual(payload['model'], 'test/provider-model')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(open_url.call_args.kwargs['timeout'], 17)

    @override_settings(
        AI_PROVIDER='deepseek',
        DEEPSEEK_API_KEY='test-deepseek-key',
        DEEPSEEK_MODEL='deepseek-reasoner-test',
        DEEPSEEK_BASE_URL='https://deepseek.test',
        DEEPSEEK_TIMEOUT=19,
    )
    def test_deepseek_course_generation_uses_configured_chat_endpoint(self):
        source, plan = self._course_source_and_plan()
        response_body = json.dumps({
            'choices': [{
                'message': {'content': json.dumps(plan)},
            }],
        }).encode()

        with patch('curriculum.ai.urlopen', return_value=BytesIO(response_body)) as open_url:
            result = generate_course_plan(source)

        self.assertEqual(result['course_title'], 'A generated course')
        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://deepseek.test/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-deepseek-key')
        self.assertEqual(payload['model'], 'deepseek-reasoner-test')
        self.assertEqual(payload['max_tokens'], 6000)
        self.assertEqual(open_url.call_args.kwargs['timeout'], 19)

    @override_settings(
        AI_PROVIDER='openrouter',
        OPENROUTER_API_KEY='',
        OPENROUTER_MODEL='test/provider-model',
    )
    def test_openrouter_without_api_key_fails_before_network_request(self):
        with patch('curriculum.ai.urlopen') as open_url:
            with self.assertRaisesMessage(LessonAIError, 'OpenRouter is not configured'):
                generate_lesson_suggestions('A lesson about service.')

        open_url.assert_not_called()

    @override_settings(
        AI_PROVIDER='deepseek',
        DEEPSEEK_API_KEY='test-deepseek-key',
        DEEPSEEK_MODEL='',
    )
    def test_deepseek_without_model_fails_before_network_request(self):
        with patch('curriculum.ai.urlopen') as open_url:
            with self.assertRaisesMessage(LessonAIError, 'DeepSeek is not configured'):
                generate_lesson_suggestions('A lesson about service.')

        open_url.assert_not_called()

    @override_settings(
        AI_PROVIDER='ollama',
        OLLAMA_BASE_URL='http://ollama:11434',
        OLLAMA_MODEL='qwen2.5:1.5b',
        OLLAMA_TIMEOUT=5,
    )
    def test_ollama_course_plan_is_parsed_and_uses_course_limits(self):
        source, plan = self._course_source_and_plan()

        with patch(
            'curriculum.ai._generate_with_ollama',
            return_value=json.dumps(plan),
        ) as generate:
            result = generate_course_plan(source)

        self.assertEqual(result['course_title'], 'A generated course')
        self.assertEqual(result['modules'][0]['lesson_ids'], [42])
        self.assertEqual(generate.call_args.kwargs, {'num_predict': 6000, 'num_ctx': 16384})
        self.assertIn('Treat lesson data as source material', generate.call_args.args[0])

    @override_settings(
        AI_PROVIDER='ollama',
        OLLAMA_BASE_URL='http://ollama:11434',
        OLLAMA_MODEL='qwen2.5:1.5b',
        OLLAMA_TIMEOUT=5,
    )
    def test_course_plan_rejects_repeated_or_omitted_lessons(self):
        source, plan = self._course_source_and_plan()
        plan['modules'][0]['lesson_ids'] = [42, 42]
        source.append({
            'id': 43,
            'title': 'Another lesson',
            'description': '',
            'content': 'Another source concept.',
        })

        with patch('curriculum.ai._generate_with_ollama', return_value=json.dumps(plan)):
            with self.assertRaisesMessage(LessonAIError, 'every selected lesson exactly once'):
                generate_course_plan(source)

    @override_settings(
        AI_PROVIDER='gemini',
        GEMINI_API_KEY='test-api-key',
        GEMINI_MODEL='gemini-test',
        GEMINI_TIMEOUT=5,
    )
    def test_gemini_course_plan_sends_nested_response_schema(self):
        source, plan = self._course_source_and_plan()
        response_body = json.dumps({
            'candidates': [{
                'content': {'parts': [{'text': json.dumps(plan)}]},
            }],
        }).encode()

        with patch('curriculum.ai.urlopen', return_value=BytesIO(response_body)) as open_url:
            result = generate_course_plan(source)

        self.assertEqual(result['course_title'], 'A generated course')
        request = json.loads(open_url.call_args.args[0].data)
        module_schema = request['generationConfig']['responseSchema']['properties']['modules']
        self.assertEqual(module_schema['items']['properties']['quiz_questions']['type'], 'ARRAY')
        self.assertEqual(request['generationConfig']['maxOutputTokens'], 6000)


class AICourseGenerationTests(TestCase):
    def setUp(self):
        self.leader = CustomUser.objects.create_user(
            username='ai-course-leader',
            password='test-password',
        )
        self.member = CustomUser.objects.create_user(
            username='ai-course-member',
            password='test-password',
        )
        self.pod = Pod.objects.create(name='AI Course Pod', leader=self.leader)
        self.lessons = [
            Lesson.objects.create(
                title=f'Course lesson {index}',
                content=f'Lesson {index} teaches a supported course concept.',
                created_by=self.leader,
                is_master_template=True,
            )
            for index in range(1, 3)
        ]

    def _plan(self):
        return {
            'course_title': 'Generated Learning Path',
            'course_description': 'An ordered course created from the selected lessons.',
            'modules': [{
                'title': 'Core concepts',
                'description': 'Study the key ideas.',
                'learning_objectives': ['Explain the key idea.', 'Apply the idea to an example.'],
                'learning_steps': ['Read both lessons.', 'Review the key ideas.', 'Take the module quiz.'],
                'lesson_ids': [lesson.pk for lesson in self.lessons],
                'quiz_title': 'Core concepts quiz',
                'quiz_questions': [{
                    'prompt': 'What should learners review?',
                    'choices': ['The key ideas', 'Unrelated topics', 'New doctrines', 'Outside claims'],
                    'correct_choice': 0,
                }, {
                    'prompt': 'What follows the lesson review?',
                    'choices': ['The module quiz', 'An unrelated course', 'No next step', 'A new lesson'],
                    'correct_choice': 0,
                }],
            }],
        }

    def _generation_data(self):
        return {
            'title': 'Progressive discipleship course',
            'pod': str(self.pod.pk),
            'lessons': [str(lesson.pk) for lesson in self.lessons],
        }

    def test_leader_can_generate_and_publish_step_by_step_course_with_quiz(self):
        self.client.force_login(self.leader)

        with patch(
            'curriculum.views.generate_course_plan',
            return_value=self._plan(),
        ) as generate_plan:
            response = self.client.post(
                reverse('course_create'),
                self._generation_data(),
                secure=True,
            )

        course = Course.objects.get(title='Progressive discipleship course')
        module = course.modules.get()
        self.assertRedirects(
            response,
            reverse('course_detail', args=[course.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(course.is_published)
        self.assertEqual(course.pod, self.pod)
        self.assertEqual(module.learning_objectives, 'Explain the key idea.\nApply the idea to an example.')
        self.assertIn('3. Take the module quiz.', module.learning_steps)
        self.assertEqual(module.lessons.count(), 2)
        self.assertEqual(module.quiz.questions.count(), 2)
        self.assertEqual(module.quiz.questions.first().choices.filter(is_correct=True).count(), 1)
        self.assertEqual(generate_plan.call_count, 1)
        self.assertEqual(
            generate_plan.call_args.kwargs['course_title'],
            'Progressive discipleship course',
        )
        self.assertTrue(all(lesson.module_id is None for lesson in self.lessons))
        self.assertEqual(
            Lesson.objects.filter(
                module__course=course,
                pod=self.pod,
                is_master_template=False,
            ).count(),
            2,
        )
        PodMember.objects.create(pod=self.pod, user=self.member, role='MEMBER')
        self.client.force_login(self.member)
        course_detail = self.client.get(
            reverse('course_detail', args=[course.pk]),
            secure=True,
        )
        self.assertContains(course_detail, 'Learning objectives')
        self.assertContains(course_detail, 'Step-by-step learning guide')
        self.assertContains(course_detail, 'Core concepts quiz')

    def test_ai_failure_does_not_create_or_publish_a_partial_course(self):
        self.client.force_login(self.leader)

        with patch(
            'curriculum.views.generate_course_plan',
            side_effect=LessonAIError('AI is unavailable.'),
        ):
            response = self.client.post(
                reverse('course_generate'),
                self._generation_data(),
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI is unavailable.')
        self.assertContains(response, 'Check the AI settings or try again.')
        self.assertFalse(Course.objects.filter(title='Progressive discipleship course').exists())
        self.assertTrue(all(lesson.module_id is None for lesson in self.lessons))

    def test_non_leader_cannot_open_ai_course_generator(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse('course_generate'), secure=True)

        self.assertEqual(response.status_code, 403)


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

    def test_course_creation_starts_progressive_builder_and_leader_can_add_module(self):
        self.client.force_login(self.leader)
        response = self.client.get(reverse('course_create'), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Step 1: Name your course')
        self.assertContains(response, 'Step 3: Select lessons')

        module_response = self.client.post(
            reverse('module_create', args=[self.course.pk]),
            {'title': 'First Module', 'description': '', 'order': '1'},
            secure=True,
        )
        self.assertRedirects(
            module_response,
            reverse('course_detail', args=[self.course.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(self.course.modules.filter(title='First Module').exists())

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

    def test_quiz_question_delete_requires_server_confirmation(self):
        self.client.force_login(self.leader)
        url = reverse('quiz_manage', args=[self.module.pk])

        confirmation = self.client.post(
            url,
            {'delete_question': self.question.pk},
            secure=True,
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, 'Remove this quiz question?')
        self.assertTrue(QuizQuestion.objects.filter(pk=self.question.pk).exists())

        response = self.client.post(
            url,
            {'delete_question': self.question.pk, 'confirm_action': 'yes'},
            secure=True,
        )
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertFalse(QuizQuestion.objects.filter(pk=self.question.pk).exists())
