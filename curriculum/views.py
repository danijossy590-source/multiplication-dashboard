
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.text import slugify
from config.confirmations import render_confirmation

from .documents import DocumentConversionError, convert_word_document
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
from .forms import (
    CourseForm,
    CourseGenerationForm,
    LessonForm,
    ModuleForm,
    QuizQuestionForm,
    QuizSettingsForm,
    TeachThisForm,
)
from .structure import structure_lesson
from pods.models import ApprenticeOversight, Pod, PodMentor

@login_required
def lesson_list_view(request):
    """
    Displays:
    1. Master Curriculum Templates.
    2. Lessons specific to Pods the user participates in or leads.
    """
    search_query = request.GET.get('q', '').strip()

    # Include every Pod the user can learn in, including mentor and oversight Pods.
    leading_pod_ids = request.user.leading_pods.values_list('id', flat=True)
    membership_pod_ids = request.user.pod_memberships.values_list('pod_id', flat=True)
    mentor_pod_ids = PodMentor.objects.filter(
        mentor=request.user,
    ).values_list('pod_id', flat=True)
    oversight_pod_ids = ApprenticeOversight.objects.filter(
        mentor=request.user,
    ).values_list('apprentice_pod_id', flat=True)
    all_user_pod_ids = set(
        list(leading_pod_ids)
        + list(membership_pod_ids)
        + list(mentor_pod_ids)
        + list(oversight_pod_ids)
    )

    available_courses = Course.objects.filter(
        Q(pod__isnull=True, is_published=True)
        | Q(pod_id__in=all_user_pod_ids)
        | Q(created_by=request.user)
    ).select_related('pod').prefetch_related('modules__lessons')
    if request.user.is_staff or request.user.is_superuser:
        available_courses = Course.objects.all().select_related('pod').prefetch_related('modules__lessons')
    visible_course_ids = available_courses.values_list('id', flat=True)
    if search_query:
        available_courses = available_courses.filter(title__icontains=search_query)

    if request.user.is_staff or request.user.is_superuser:
        all_lessons = Lesson.objects.all()
    else:
        all_lessons = Lesson.objects.filter(
            Q(is_master_template=True)
            | Q(pod_id__in=all_user_pod_ids)
            | Q(created_by=request.user, module__isnull=True)
            | Q(module__course_id__in=visible_course_ids)
        ).distinct()
    all_lessons = all_lessons.select_related(
        'pod',
        'created_by',
        'module__course',
    ).order_by('-created_at', 'id')
    if search_query:
        all_lessons = all_lessons.filter(title__icontains=search_query)
    for course in available_courses:
        lesson_ids = [
            lesson.id
            for module in course.modules.all()
            for lesson in module.lessons.all()
        ]
        course.total_lessons = len(lesson_ids)
        course.completed_lessons = LessonProgress.objects.filter(
            user=request.user,
            lesson_id__in=lesson_ids,
        ).count()
        course.progress_percent = (
            course.completed_lessons * 100 // course.total_lessons
            if course.total_lessons else 0
        )

    context = {
        'all_lessons': all_lessons,
        'courses': available_courses,
        'search_query': search_query,
        'can_create_lessons': (
            request.user.is_staff
            or request.user.is_superuser
            or request.user.leading_pods.exists()
        ),
        'can_create_course': (
            request.user.is_staff
            or request.user.is_superuser
            or request.user.leading_pods.exists()
        ),
    }
    return render(request, 'curriculum/lesson_list.html', context)


def _can_manage_course(user, course):
    return (
        user.is_staff
        or user.is_superuser
        or course.created_by_id == user.id
        or (course.pod_id and course.pod.leader_id == user.id)
    )


def _can_manage_lesson(user, lesson):
    return (
        user.is_staff
        or user.is_superuser
        or lesson.created_by_id == user.id
        or (lesson.pod_id and lesson.pod.leader_id == user.id)
        or (
            lesson.module_id
            and _can_manage_course(user, lesson.module.course)
        )
    )


def _lesson_files(lesson):
    return [
        (field.storage, field.name)
        for field in (lesson.audio_file, lesson.pdf_resource)
        if field
    ]


def _delete_unreferenced_lesson_files(files):
    for storage, name in files:
        still_referenced = Lesson.objects.filter(
            Q(audio_file=name) | Q(pdf_resource=name)
        ).exists()
        if not still_referenced:
            storage.delete(name)


def _can_view_course(user, course):
    if user.is_staff or user.is_superuser or _can_manage_course(user, course):
        return True
    if course.pod_id:
        return (
            course.pod.leader_id == user.id
            or course.pod.memberships.filter(user=user).exists()
        )
    return course.is_published


def _course_is_complete(user, course):
    lesson_ids = list(
        Lesson.objects.filter(module__course=course).values_list('id', flat=True)
    )
    if not lesson_ids:
        return False
    if LessonProgress.objects.filter(user=user, lesson_id__in=lesson_ids).count() != len(lesson_ids):
        return False
    quizzes = ModuleQuiz.objects.filter(module__course=course)
    return all(quiz.attempts.filter(user=user, passed=True).exists() for quiz in quizzes)


def _issue_course_certificate(user, course):
    if _course_is_complete(user, course):
        return CourseCertificate.objects.get_or_create(user=user, course=course)[0]
    return None


@login_required
def course_detail_view(request, course_id):
    course = get_object_or_404(
        Course.objects.select_related('pod', 'created_by').prefetch_related(
            'modules__lessons',
            'modules__quiz__questions__choices',
        ),
        pk=course_id,
    )
    if not _can_view_course(request.user, course):
        return HttpResponseForbidden('You do not have access to this course.')

    modules = list(course.modules.all())
    lesson_ids = [lesson.id for module in modules for lesson in module.lessons.all()]
    completed_ids = set(
        LessonProgress.objects.filter(
            user=request.user,
            lesson_id__in=lesson_ids,
        ).values_list('lesson_id', flat=True)
    )
    for module in modules:
        module.lesson_items = list(module.lessons.all())
        module.completed_count = sum(lesson.id in completed_ids for lesson in module.lesson_items)
        module.quiz_passed = (
            hasattr(module, 'quiz')
            and module.quiz.attempts.filter(user=request.user, passed=True).exists()
        )
    total_lessons = len(lesson_ids)
    completed_count = len(completed_ids)
    certificate = _issue_course_certificate(request.user, course)
    context = {
        'course': course,
        'modules': modules,
        'total_lessons': total_lessons,
        'completed_count': completed_count,
        'progress_percent': completed_count * 100 // total_lessons if total_lessons else 0,
        'completed_ids': completed_ids,
        'can_manage': _can_manage_course(request.user, course),
        'certificate': certificate,
    }
    return render(request, 'curriculum/course_detail.html', context)


@login_required
def course_edit_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not _can_manage_course(request.user, course):
        return HttpResponseForbidden('You cannot edit this course.')

    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course, user=request.user)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Course "{course.title}" was updated.')
            return redirect('course_detail', course_id=course.pk)
    else:
        form = CourseForm(instance=course, user=request.user)

    return render(
        request,
        'curriculum/course_form.html',
        {'form': form, 'course': course},
    )


def _course_builder_view(request):
    if not (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.leading_pods.exists()
    ):
        return HttpResponseForbidden('Only admins and pod leaders can create courses.')

    form = CourseGenerationForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        selected_lessons = list(form.cleaned_data['lessons'])
        lesson_sources = [
            {
                'id': lesson.pk,
                'title': lesson.title,
                'description': lesson.description or '',
                'content': lesson.content,
            }
            for lesson in selected_lessons
        ]
        try:
            plan = generate_course_plan(
                lesson_sources,
                course_title=form.cleaned_data['title'],
            )
        except LessonAIError as error:
            form.add_error(None, f'{error} Check the AI settings or try again.')
        else:
            pod = form.cleaned_data['pod']
            selected_by_id = {lesson.pk: lesson for lesson in selected_lessons}
            with transaction.atomic():
                course = Course.objects.create(
                    title=form.cleaned_data['title'],
                    description=plan['course_description'],
                    pod=pod,
                    created_by=request.user,
                    is_published=True,
                )
                for module_order, module_plan in enumerate(plan['modules']):
                    module = Module.objects.create(
                        course=course,
                        title=module_plan['title'],
                        description=module_plan['description'],
                        learning_objectives='\n'.join(module_plan['learning_objectives']),
                        learning_steps='\n'.join(
                            f'{step_number}. {step}'
                            for step_number, step in enumerate(module_plan['learning_steps'], start=1)
                        ),
                        order=module_order,
                    )
                    for lesson_order, lesson_id in enumerate(module_plan['lesson_ids']):
                        lesson = selected_by_id[lesson_id]
                        if pod and lesson.pod_id is None and lesson.is_master_template:
                            lesson = lesson.clone_for_pod(pod, request.user)
                        if pod:
                            lesson.pod = pod
                            lesson.is_master_template = False
                        lesson.module = module
                        lesson.order = lesson_order
                        lesson.save()

                    quiz = ModuleQuiz.objects.create(
                        module=module,
                        title=module_plan['quiz_title'],
                    )
                    for question_order, question_plan in enumerate(module_plan['quiz_questions']):
                        question = QuizQuestion.objects.create(
                            quiz=quiz,
                            prompt=question_plan['prompt'],
                            order=question_order,
                        )
                        QuizChoice.objects.bulk_create([
                            QuizChoice(
                                question=question,
                                text=choice,
                                is_correct=choice_order == question_plan['correct_choice'],
                                order=choice_order,
                            )
                            for choice_order, choice in enumerate(question_plan['choices'])
                        ])

            messages.success(request, f'Course "{course.title}" was created and published.')
            return redirect('course_detail', course_id=course.pk)

    return render(request, 'curriculum/course_generate.html', {'form': form})


@login_required
def course_create_view(request):
    if not (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.leading_pods.exists()
    ):
        return HttpResponseForbidden('Only admins and pod leaders can create courses.')

    form = CourseForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        course = form.save(commit=False)
        course.created_by = request.user
        course.save()
        messages.success(request, f'Course "{course.title}" was created.')
        return redirect('course_detail', course_id=course.pk)

    return render(request, 'curriculum/course_form.html', {'form': form})


@login_required
def course_generate_view(request):
    return _course_builder_view(request)


@login_required
def module_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not _can_manage_course(request.user, course):
        return HttpResponseForbidden('You cannot edit this course.')
    if request.method == 'POST':
        form = ModuleForm(request.POST)
        if form.is_valid():
            module = form.save(commit=False)
            module.course = course
            module.save()
            messages.success(request, f'Module "{module.title}" added.')
            return redirect('course_detail', course_id=course.pk)
    else:
        form = ModuleForm()
    return render(request, 'curriculum/module_form.html', {'form': form, 'course': course})


@login_required
def lesson_detail_view(request, lesson_id):
    """
    Displays full lesson text, HTML5 audio playback player, PDF download links,
    and the 'Teach This' button for eligible leaders.
    """
    lesson = get_object_or_404(
        Lesson.objects.select_related('module__course'),
        id=lesson_id,
    )
    course = lesson.module.course if lesson.module_id else None
    if course and not _can_view_course(request.user, course):
        if lesson.is_master_template:
            course = None
        else:
            return HttpResponseForbidden('You do not have access to this lesson.')
    
    # Check if the current user is a leader of at least one pod
    user_is_a_leader = request.user.leading_pods.exists()

    course_lessons = []
    current_index = None
    is_complete = False
    completed_ids = set()
    if course:
        course_lessons = list(
            Lesson.objects.filter(module__course=course)
            .select_related('module')
            .order_by('module__order', 'module_id', 'order', 'created_at')
        )
        current_index = next(
            (index for index, item in enumerate(course_lessons) if item.pk == lesson.pk),
            None,
        )
        completed_ids = set(
            LessonProgress.objects.filter(
                user=request.user,
                lesson_id__in=[item.pk for item in course_lessons],
            ).values_list('lesson_id', flat=True)
        )
        is_complete = lesson.pk in completed_ids
    context = {
        'lesson': lesson,
        'user_is_a_leader': user_is_a_leader,
        'lesson_structure': structure_lesson(lesson.content),
        'course': course,
        'course_lessons': course_lessons,
        'current_index': current_index,
        'previous_lesson': course_lessons[current_index - 1] if current_index else None,
        'next_lesson': (
            course_lessons[current_index + 1]
            if current_index is not None and current_index + 1 < len(course_lessons)
            else None
        ),
        'is_complete': is_complete,
        'completed_ids': completed_ids,
        'can_manage_lesson': _can_manage_lesson(request.user, lesson),
        'can_manage_course': _can_manage_course(request.user, course) if course else False,
    }
    return render(request, 'curriculum/lesson_detail.html', context)


@login_required
def lesson_create_view(request):
    """
    Allows instructors or leaders to upload new lessons and attached media files.
    """
    if not (request.user.is_staff or request.user.leading_pods.exists()):
        messages.error(request, "Only staff or pod leaders can create curriculum lessons.")
        return redirect('lesson_list')

    if request.method == 'POST':
        # MUST pass request.FILES to handle uploaded audio/PDF files
        form = LessonForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            word_document = form.cleaned_data['word_document']
            if word_document:
                try:
                    pdf_content, extracted_text = convert_word_document(word_document)
                except DocumentConversionError as error:
                    form.add_error('word_document', str(error))
                else:
                    lesson = form.save(commit=False)
                    lesson.content = extracted_text
                    lesson.created_by = request.user
                    lesson.module = form.cleaned_data.get('module')
                    lesson.order = form.cleaned_data.get('order') or 0
                    if lesson.module:
                        lesson.pod = lesson.module.course.pod
                        lesson.is_master_template = lesson.module.course.pod_id is None
                    filename = f'{slugify(lesson.title) or "lesson"}-{uuid.uuid4().hex}.pdf'
                    lesson.pdf_resource.save(filename, ContentFile(pdf_content), save=False)
                    lesson.save()
                    messages.success(request, f"Lesson '{lesson.title}' uploaded and converted to PDF.")
                    return redirect('lesson_list')
            else:
                lesson = form.save(commit=False)
                lesson.created_by = request.user
                lesson.module = form.cleaned_data.get('module')
                lesson.order = form.cleaned_data.get('order') or 0
                if lesson.module:
                    lesson.pod = lesson.module.course.pod
                    lesson.is_master_template = lesson.module.course.pod_id is None
                lesson.save()
                messages.success(request, f"Lesson '{lesson.title}' uploaded successfully!")
                return redirect('lesson_list')
    else:
        initial = {}
        module_id = request.GET.get('module')
        if module_id:
            initial['module'] = module_id
        form = LessonForm(user=request.user, initial=initial)

    return render(request, 'curriculum/lesson_form.html', {'form': form, 'title': 'Create & Upload Lesson'})


@login_required
def lesson_edit_view(request, lesson_id):
    lesson = get_object_or_404(
        Lesson.objects.select_related('module__course', 'pod'),
        pk=lesson_id,
    )
    if not _can_manage_lesson(request.user, lesson):
        return HttpResponseForbidden('You cannot edit this lesson.')

    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson, user=request.user)
        if form.is_valid():
            old_files = _lesson_files(lesson)
            word_document = form.cleaned_data['word_document']
            if word_document:
                try:
                    pdf_content, extracted_text = convert_word_document(word_document)
                except DocumentConversionError as error:
                    form.add_error('word_document', str(error))
                else:
                    lesson = form.save(commit=False)
                    lesson.content = extracted_text
                    lesson.module = form.cleaned_data.get('module')
                    lesson.order = form.cleaned_data.get('order') or 0
                    if lesson.module:
                        lesson.pod = lesson.module.course.pod
                        lesson.is_master_template = lesson.module.course.pod_id is None
                    filename = f'{slugify(lesson.title) or "lesson"}-{uuid.uuid4().hex}.pdf'
                    lesson.pdf_resource.save(filename, ContentFile(pdf_content), save=False)
                    lesson.save()
                    _delete_unreferenced_lesson_files(old_files)
                    messages.success(request, f"Lesson '{lesson.title}' updated.")
                    return redirect('lesson_detail', lesson_id=lesson.pk)
            else:
                lesson = form.save(commit=False)
                lesson.module = form.cleaned_data.get('module')
                lesson.order = form.cleaned_data.get('order') or 0
                if lesson.module:
                    lesson.pod = lesson.module.course.pod
                    lesson.is_master_template = lesson.module.course.pod_id is None
                lesson.save()
                _delete_unreferenced_lesson_files(old_files)
                messages.success(request, f"Lesson '{lesson.title}' updated.")
                return redirect('lesson_detail', lesson_id=lesson.pk)
    else:
        form = LessonForm(instance=lesson, user=request.user)

    return render(request, 'curriculum/lesson_form.html', {
        'form': form,
        'title': 'Edit Lesson',
        'lesson': lesson,
    })


@login_required
@require_POST
def lesson_delete_view(request, lesson_id):
    lesson = get_object_or_404(
        Lesson.objects.select_related('module__course', 'pod'),
        pk=lesson_id,
    )
    if not _can_manage_lesson(request.user, lesson):
        return HttpResponseForbidden('You cannot delete this lesson.')

    if request.POST.get('confirm_action') != 'yes':
        return render_confirmation(
            request,
            title=f'Delete "{lesson.title}"?',
            message='This permanently removes the lesson and its completion records. This action cannot be undone.',
            confirm_label='Delete lesson',
            cancel_url=reverse('lesson_detail', args=[lesson.pk]),
        )

    lesson_title = lesson.title
    files = _lesson_files(lesson)
    lesson.delete()
    _delete_unreferenced_lesson_files(files)
    messages.success(request, f"Lesson '{lesson_title}' deleted.")
    return redirect('lesson_list')


@login_required
@require_POST
def lesson_complete_view(request, lesson_id):
    lesson = get_object_or_404(
        Lesson.objects.select_related('module__course'),
        pk=lesson_id,
        module__isnull=False,
    )
    course = lesson.module.course
    if not _can_view_course(request.user, course):
        return HttpResponseForbidden('You do not have access to this course.')
    LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
    _issue_course_certificate(request.user, course)
    messages.success(request, 'Lesson marked complete.')
    return redirect('lesson_detail', lesson_id=lesson.pk)


@login_required
def quiz_view(request, module_id):
    module = get_object_or_404(
        Module.objects.select_related('course').prefetch_related('lessons', 'quiz__questions__choices'),
        pk=module_id,
    )
    if not _can_view_course(request.user, module.course):
        return HttpResponseForbidden('You do not have access to this course.')
    quiz = get_object_or_404(ModuleQuiz.objects.prefetch_related('questions__choices'), module=module)
    incomplete_lessons = Lesson.objects.filter(module=module).exclude(
        progress_records__user=request.user
    ).exists()
    if incomplete_lessons:
        messages.info(request, 'Complete the module lessons before taking its quiz.')
        return redirect('course_detail', course_id=module.course_id)
    questions = list(quiz.questions.all())
    latest_attempt = quiz.attempts.filter(user=request.user).first()

    if request.method == 'POST':
        if not questions:
            messages.error(request, 'This quiz has no questions yet.')
            return redirect('quiz', module_id=module.pk)
        correct_count = 0
        for question in questions:
            choice_id = request.POST.get(f'question_{question.pk}')
            if question.choices.filter(pk=choice_id, is_correct=True).exists():
                correct_count += 1
        score = correct_count * 100 // len(questions)
        passed = score >= quiz.passing_score
        attempt = QuizAttempt.objects.create(
            user=request.user,
            quiz=quiz,
            score=score,
            passed=passed,
        )
        if passed:
            _issue_course_certificate(request.user, module.course)
            messages.success(request, f'You passed with {score}%.')
        else:
            messages.warning(request, f'You scored {score}%. Review the module and try again.')
        return redirect('quiz_result', attempt_id=attempt.pk)

    return render(request, 'curriculum/quiz.html', {
        'module': module,
        'course': module.course,
        'quiz': quiz,
        'questions': questions,
        'latest_attempt': latest_attempt,
    })


@login_required
def quiz_result_view(request, attempt_id):
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related('quiz__module__course'),
        pk=attempt_id,
        user=request.user,
    )
    if not _can_view_course(request.user, attempt.quiz.module.course):
        return HttpResponseForbidden('You do not have access to this course.')
    return render(request, 'curriculum/quiz_result.html', {'attempt': attempt})


@login_required
def quiz_manage_view(request, module_id):
    module = get_object_or_404(Module.objects.select_related('course'), pk=module_id)
    if not _can_manage_course(request.user, module.course):
        return HttpResponseForbidden('You cannot edit this course.')
    quiz, _ = ModuleQuiz.objects.get_or_create(
        module=module,
        defaults={'title': f'{module.title} Quiz'},
    )
    settings_form = QuizSettingsForm(request.POST or None, instance=quiz, prefix='settings')
    question_form = QuizQuestionForm(request.POST or None, prefix='question')

    if request.method == 'POST' and 'save_settings' in request.POST:
        if settings_form.is_valid():
            settings_form.save()
            messages.success(request, 'Quiz settings saved.')
            return redirect('quiz_manage', module_id=module.pk)
    elif request.method == 'POST' and 'add_question' in request.POST:
        if question_form.is_valid():
            with transaction.atomic():
                question = QuizQuestion.objects.create(
                    quiz=quiz,
                    prompt=question_form.cleaned_data['prompt'],
                    order=quiz.questions.count(),
                )
                correct_choice = question_form.cleaned_data['correct_choice']
                for index in range(1, 5):
                    QuizChoice.objects.create(
                        question=question,
                        text=question_form.cleaned_data[f'choice_{index}'],
                        is_correct=str(index) == correct_choice,
                        order=index,
                    )
            messages.success(request, 'Question added to quiz.')
            return redirect('quiz_manage', module_id=module.pk)
    elif request.method == 'POST' and 'delete_question' in request.POST:
        question = get_object_or_404(QuizQuestion, pk=request.POST.get('delete_question'), quiz=quiz)
        if request.POST.get('confirm_action') != 'yes':
            return render_confirmation(
                request,
                title='Remove this quiz question?',
                message='This permanently removes the question and its answer choices from the module quiz.',
                confirm_label='Remove question',
                cancel_url=reverse('quiz_manage', args=[module.pk]),
                hidden_fields={'delete_question': question.pk},
            )
        question.delete()
        messages.success(request, 'Question removed.')
        return redirect('quiz_manage', module_id=module.pk)

    return render(request, 'curriculum/quiz_manage.html', {
        'module': module,
        'course': module.course,
        'quiz': quiz,
        'settings_form': settings_form,
        'question_form': question_form,
    })


@login_required
def certificate_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not _can_view_course(request.user, course):
        return HttpResponseForbidden('You do not have access to this course.')
    certificate = _issue_course_certificate(request.user, course)
    if not certificate:
        messages.error(request, 'Complete every lesson and pass each module quiz to earn this certificate.')
        return redirect('course_detail', course_id=course.pk)
    return render(request, 'curriculum/certificate.html', {'certificate': certificate})


@login_required
@require_POST
def lesson_assist_view(request):
    if not (request.user.is_staff or request.user.is_superuser or request.user.leading_pods.exists()):
        return JsonResponse({'error': 'Only staff or pod leaders can use lesson assistance.'}, status=403)

    content = request.POST.get('content', '').strip()
    word_document = request.FILES.get('word_document')
    if word_document:
        if word_document.size > LessonForm.MAX_FILE_SIZE:
            return JsonResponse({'error': 'Word document must be 10MB or smaller.'}, status=400)
        if not word_document.name.lower().endswith(('.doc', '.docx')):
            return JsonResponse({'error': 'Only Word documents (.doc or .docx) are supported.'}, status=400)
        try:
            _, content = convert_word_document(word_document)
        except DocumentConversionError as error:
            return JsonResponse({'error': str(error)}, status=400)

    if not content:
        return JsonResponse({'error': 'Enter lesson text or choose a Word document first.'}, status=400)
    if len(content) > 30000:
        return JsonResponse({'error': 'Lesson text is too long for analysis (30,000 characters maximum).'}, status=400)

    result = structure_lesson(content)
    result['extracted_text'] = content if word_document else ''
    try:
        result['ai_suggestions'] = generate_lesson_suggestions(content)
        result['ai_available'] = True
    except LessonAIError as error:
        result['ai_suggestions'] = None
        result['ai_available'] = False
        result['ai_message'] = (
            f'{error} Click Try again. If the issue continues, ask an admin to check the AI settings.'
        )
    return JsonResponse(result)


@login_required
def teach_this_view(request, lesson_id):
    """
    Executes the 'Teach This' duplication process:
    Clones the chosen lesson directly into a destination Pod led by the user.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)

    if not request.user.leading_pods.exists():
        messages.error(request, "You must lead at least one Pod to use the 'Teach This' feature.")
        return redirect('lesson_detail', lesson_id=lesson.id)

    if request.method == 'POST':
        form = TeachThisForm(request.POST, user=request.user)
        if form.is_valid():
            target_pod = form.cleaned_data['target_pod']
            
            # Execute cloning pattern
            cloned_lesson = lesson.clone_for_pod(target_pod=target_pod, user=request.user)
            
            messages.success(
                request, 
                f"Successfully duplicated '{lesson.title}' to '{target_pod.name}'! You can now teach this lesson."
            )
            return redirect('lesson_detail', lesson_id=cloned_lesson.id)
    else:
        form = TeachThisForm(user=request.user)

    context = {
        'form': form,
        'lesson': lesson,
    }
    return render(request, 'curriculum/teach_this.html', context)

# Create your views here.
