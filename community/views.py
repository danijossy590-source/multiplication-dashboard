from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from config.confirmations import render_confirmation
from .forms import QuestionForm, ReplyForm, ReportForm
from .models import ContentReport, Question, Reply


def question_list_view(request):
    questions = (
        Question.objects.filter(is_hidden=False)
        .annotate(
            visible_reply_count=Count(
                'replies',
                filter=Q(replies__is_hidden=False),
            )
        )
        .order_by('-created_at')
    )
    page_obj = Paginator(questions, 15).get_page(request.GET.get('page'))
    return render(request, 'community/question_list.html', {'page_obj': page_obj})


def question_detail_view(request, question_id):
    question = get_object_or_404(
        Question.objects.filter(is_hidden=False),
        pk=question_id,
    )
    all_replies = list(
        question.replies.filter(is_hidden=False)
        .select_related('author', 'parent')
        .order_by('created_at')
    )
    replies_by_id = {}
    replies = []
    for reply in all_replies:
        reply.visible_children = []
        if reply.parent_id and reply.parent_id in replies_by_id:
            replies_by_id[reply.parent_id].visible_children.append(reply)
        else:
            replies.append(reply)
        replies_by_id[reply.pk] = reply

    return render(request, 'community/question_detail.html', {
        'question': question,
        'replies': replies,
        'reply_count': len(all_replies),
        'reply_form': ReplyForm(),
        'report_form': ReportForm(),
    })


@login_required
def question_create_view(request):
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.author = request.user
            question.is_anonymous = form.cleaned_data['is_anonymous']
            if question.is_anonymous:
                question.display_name = ''
            else:
                question.display_name = request.user.get_username()
            question.save()
            messages.success(request, 'Your question has been posted.')
            return redirect('question_detail', question_id=question.pk)
    else:
        form = QuestionForm(initial={'is_anonymous': True})

    return render(request, 'community/question_form.html', {'form': form})


@login_required
@require_POST
def reply_create_view(request, question_id):
    question = get_object_or_404(Question, pk=question_id, is_hidden=False)
    form = ReplyForm(request.POST)
    if form.is_valid():
        parent_id = form.cleaned_data.get('parent_id')
        parent = None
        if parent_id:
            parent = get_object_or_404(
                Reply,
                pk=parent_id,
                question=question,
                is_hidden=False,
            )
        reply = form.save(commit=False)
        reply.question = question
        reply.parent = parent
        reply.author = request.user
        reply.display_name = request.user.get_username()
        reply.save()
        messages.success(request, 'Your reply has been posted.')
    else:
        messages.error(request, 'Please enter a reply before submitting.')
    return redirect('question_detail', question_id=question.pk)


@login_required
@require_POST
def question_report_view(request, question_id):
    question = get_object_or_404(Question, pk=question_id, is_hidden=False)
    return _create_report(request, question=question)


@login_required
@require_POST
def reply_report_view(request, reply_id):
    reply = get_object_or_404(
        Reply.objects.select_related('question'),
        pk=reply_id,
        is_hidden=False,
        question__is_hidden=False,
    )
    return _create_report(request, reply=reply)


@login_required
@require_POST
def question_delete_view(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    if question.author_id != request.user.pk and not (
        request.user.is_staff or request.user.is_superuser
    ):
        messages.error(request, 'You can only delete your own question.')
        return redirect('question_detail', question_id=question.pk)

    if request.POST.get('confirm_action') != 'yes':
        return render_confirmation(
            request,
            title=f'Delete "{question.title}"?',
            message='This permanently removes the question and all of its replies. This action cannot be undone.',
            confirm_label='Delete question',
            cancel_url=reverse('question_detail', args=[question.pk]),
        )

    question.delete()
    messages.success(request, 'Your question was deleted.')
    return redirect('question_list')


@login_required
@require_POST
def reply_delete_view(request, reply_id):
    reply = get_object_or_404(
        Reply.objects.select_related('question'),
        pk=reply_id,
    )
    if reply.author_id != request.user.pk and not (
        request.user.is_staff or request.user.is_superuser
    ):
        messages.error(request, 'You can only delete your own reply.')
        return redirect('question_detail', question_id=reply.question_id)

    if request.POST.get('confirm_action') != 'yes':
        return render_confirmation(
            request,
            title='Delete this reply?',
            message='This permanently removes the reply and any replies nested beneath it. This action cannot be undone.',
            confirm_label='Delete reply',
            cancel_url=reverse('question_detail', args=[reply.question_id]),
        )

    reply.delete()
    messages.success(request, 'Your reply was deleted.')
    return redirect('question_detail', question_id=reply.question_id)


def _create_report(request, question=None, reply=None):
    form = ReportForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide a reason for the report.')
    else:
        lookup = {'reporter': request.user}
        if question:
            lookup['question'] = question
            destination_id = question.pk
        else:
            lookup['reply'] = reply
            destination_id = reply.question_id

        _, created = ContentReport.objects.get_or_create(
            **lookup,
            defaults={'reason': form.cleaned_data['reason']},
        )
        if created:
            messages.success(request, 'Thanks. The content has been reported for review.')
        else:
            messages.info(request, 'You have already reported this content.')
        return redirect('question_detail', question_id=destination_id)

    destination_id = question.pk if question else reply.question_id
    return redirect('question_detail', question_id=destination_id)
