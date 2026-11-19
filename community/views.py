from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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


def question_create_view(request):
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.author = request.user if request.user.is_authenticated else None
            question.is_anonymous = form.cleaned_data['is_anonymous']
            if question.is_anonymous:
                question.display_name = ''
            elif request.user.is_authenticated:
                question.display_name = request.user.get_username()
            else:
                question.display_name = form.cleaned_data['display_name'].strip() or 'Guest'
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
