from pathlib import Path
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpResponseForbidden
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST
from accounts.utils import notify_user
from curriculum.models import Lesson
from .models import (
    ApprenticeOversight,
    Pod,
    PodBook,
    PodBookReviewComment,
    PodBookReview,
    PodMeeting,
    PodMember,
    PodMentor,
    PodMessage,
)
from .forms import (
    AddMemberForm,
    AssignMentorsForm,
    JoinPodForm,
    LaunchApprenticePodForm,
    PodBookForm,
    PodBookReviewCommentForm,
    PodBookReviewForm,
    PodForm,
    PodMeetingForm,
    PodMessageForm,
)

User = get_user_model()


def user_has_pod_access(user, pod):
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    if pod.leader_id == user.id:
        return True
    if PodMember.objects.filter(pod=pod, user=user).exists():
        return True
    if PodMentor.objects.filter(pod=pod, mentor=user).exists():
        return True
    if ApprenticeOversight.objects.filter(apprentice_pod=pod, mentor=user).exists():
        return True
    return False


def user_can_participate_in_pod(user, pod):
    if not user.is_authenticated:
        return False
    return (
        user.is_staff
        or user.is_superuser
        or pod.leader_id == user.id
        or PodMember.objects.filter(pod=pod, user=user).exists()
        or PodMentor.objects.filter(pod=pod, mentor=user).exists()
    )


@login_required
def pod_list_view(request):
    """
    Displays:
    1. Pods led by the user.
    2. Pods where user is a member/apprentice.
    3. Pods overseen by user (Apprentice Oversight).
    """
    my_leading_pods = Pod.objects.filter(leader=request.user)
    my_memberships = PodMember.objects.filter(user=request.user).exclude(pod__leader=request.user)
    my_oversight_pods = ApprenticeOversight.objects.filter(mentor=request.user)

    context = {
        'my_leading_pods': my_leading_pods,
        'my_memberships': my_memberships,
        'my_oversight_pods': my_oversight_pods,
        'all_pods': Pod.objects.select_related('leader').order_by('name')
        if request.user.is_staff or request.user.is_superuser
        else Pod.objects.none(),
        'is_admin': request.user.is_staff or request.user.is_superuser,
        'join_form': JoinPodForm(),
    }
    return render(request, 'pods/pod_list.html', context)


@login_required
def pod_join_view(request):
    if request.method == 'POST':
        form = JoinPodForm(request.POST)
        if form.is_valid():
            pod = Pod.objects.filter(
                join_code=form.cleaned_data['code'],
                status='active',
            ).first()
            if not pod:
                form.add_error('code', 'That code is invalid or the Pod is not accepting members.')
            else:
                _, created = PodMember.objects.get_or_create(
                    pod=pod,
                    user=request.user,
                    defaults={'role': 'MEMBER'},
                )
                if created:
                    messages.success(request, f"You joined '{pod.name}'.")
                else:
                    messages.info(request, f"You are already part of '{pod.name}'.")
                return redirect('pod_detail', pod_id=pod.pk)
    else:
        form = JoinPodForm()

    return render(request, 'pods/pod_join.html', {'form': form})


@login_required
def pod_create_view(request):
    """
    Creates a new Pod and automatically adds the user as Leader.
    """
    is_admin = request.user.is_staff or request.user.is_superuser
    if request.method == 'POST':
        form = PodForm(request.POST, is_admin=is_admin)
        if form.is_valid():
            with transaction.atomic():
                pod = form.save(commit=False)
                pod.leader = form.cleaned_data['leader'] if is_admin else request.user
                pod.save()
                PodMember.objects.create(pod=pod, user=pod.leader, role='LEADER')
                if is_admin:
                    PodMentor.objects.bulk_create(
                        [PodMentor(pod=pod, mentor=mentor) for mentor in form.cleaned_data['mentors']]
                    )
            notify_user(request.user, 'Pod created', f"You created the pod '{pod.name}'.", f'/pods/{pod.id}/')
            if pod.leader != request.user:
                notify_user(
                    pod.leader,
                    'Pod leadership assigned',
                    f"You are the leader of '{pod.name}'.",
                    f'/pods/{pod.id}/',
                )
            messages.success(request, f"Pod '{pod.name}' created successfully!")
            return redirect('pod_detail', pod_id=pod.id)
    else:
        form = PodForm(is_admin=is_admin)

    return render(request, 'pods/pod_form.html', {'form': form, 'title': 'Create New Pod'})


@login_required
def pod_detail_view(request, pod_id):
    """
    Displays Pod details, members, and management options based on user access levels.
    """
    pod = get_object_or_404(Pod, id=pod_id)

    # Determine user permissions for this specific Pod
    is_leader = (pod.leader == request.user)
    is_member = PodMember.objects.filter(pod=pod, user=request.user).exists()
    is_overseers = ApprenticeOversight.objects.filter(apprentice_pod=pod, mentor=request.user).exists()
    is_admin = request.user.is_staff or request.user.is_superuser
    is_mentor = PodMentor.objects.filter(pod=pod, mentor=request.user).exists()

    # Access security check
    if not user_has_pod_access(request.user, pod):
        messages.error(request, "You do not have permission to view this Pod.")
        return redirect('pod_list')

    members = pod.memberships.select_related('user').all()

    can_manage_members = is_leader or is_admin
    can_participate = user_can_participate_in_pod(request.user, pod)
    add_member_form = AddMemberForm()
    assign_mentors_form = AssignMentorsForm(
        initial={'mentors': pod.mentors.values_list('mentor_id', flat=True)}
    )
    message_form = PodMessageForm()
    meeting_form = PodMeetingForm()
    book = pod.reading_books.filter(is_current=True).first()
    book_form = PodBookForm()
    book_review_form = None
    book_weeks = []

    if book:
        days_since_start = (timezone.localdate() - book.started_on).days
        available_week_count = min(
            book.duration_weeks,
            max(0, days_since_start // 7 + 1),
        )
        available_weeks = list(range(1, available_week_count + 1))
        if available_weeks:
            current_week = available_weeks[-1]
            book_review_form = PodBookReviewForm(
                available_weeks=available_weeks,
                initial_week=current_week,
            )
        reviews = list(book.reviews.filter(
            week_number__lte=available_week_count,
        ).select_related('user'))
        reviews_by_week = {}
        reviews_by_id = {review.pk: review for review in reviews}
        reviews_by_week_user = {}
        for review in reviews:
            reviews_by_week.setdefault(review.week_number, []).append(review)
            reviews_by_week_user[(review.week_number, review.user_id)] = review
            review.comment_threads = []
        comments = PodBookReviewComment.objects.filter(
            review__in=reviews,
        ).select_related('author', 'parent').order_by('created_at')
        comments_by_id = {}
        for comment in comments:
            comment.thread_replies = []
            if comment.parent_id and comment.parent_id in comments_by_id:
                comments_by_id[comment.parent_id].thread_replies.append(comment)
            else:
                review = reviews_by_id.get(comment.review_id)
                if review:
                    review.comment_threads.append(comment)
            comments_by_id[comment.pk] = comment
        book_weeks = [
            {
                'number': week,
                'due_on': book.started_on + timedelta(days=week * 7),
                'reviews': reviews_by_week.get(week, []),
                'reviewed_count': sum(
                    (week, member.user_id) in reviews_by_week_user
                    for member in members
                ),
                'member_progress': [
                    {
                        'user': member.user,
                        'review': reviews_by_week_user.get((week, member.user_id)),
                        'status': (
                            'reviewed'
                            if (week, member.user_id) in reviews_by_week_user
                            else (
                                'behind'
                                if book.started_on + timedelta(days=week * 7) <= timezone.localdate()
                                else 'in_progress'
                            )
                        ),
                    }
                    for member in members
                ],
            }
            for week in available_weeks
        ]

    if can_manage_members and request.method == 'POST' and 'assign_book' in request.POST:
        book_form = PodBookForm(request.POST, request.FILES)
        if book_form.is_valid():
            with transaction.atomic():
                pod.reading_books.filter(is_current=True).update(is_current=False)
                book = PodBook.objects.create(
                    pod=pod,
                    title=book_form.cleaned_data['title'],
                    document=book_form.cleaned_data['document'],
                    duration_weeks=book_form.cleaned_data['duration_weeks'],
                    assigned_by=request.user,
                )
            messages.success(request, f"'{book.title}' is now the reading assignment for {pod.name}.")
            return redirect('pod_detail', pod_id=pod.id)
    elif can_participate and book and request.method == 'POST' and 'submit_book_review' in request.POST:
        days_since_start = (timezone.localdate() - book.started_on).days
        available_week_count = min(
            book.duration_weeks,
            max(0, days_since_start // 7 + 1),
        )
        available_weeks = list(range(1, available_week_count + 1))
        current_week = available_weeks[-1] if available_weeks else None
        book_review_form = PodBookReviewForm(
            request.POST,
            available_weeks=available_weeks,
            initial_week=current_week,
        )
        if book_review_form.is_valid():
            week_number = int(book_review_form.cleaned_data['week_number'])
            PodBookReview.objects.update_or_create(
                book=book,
                user=request.user,
                week_number=week_number,
                defaults={'review': book_review_form.cleaned_data['review']},
            )
            messages.success(request, f'Your week {week_number} book review was saved.')
            return redirect('pod_detail', pod_id=pod.id)
    elif can_manage_members and request.method == 'POST' and 'add_member' in request.POST:
        add_member_form = AddMemberForm(request.POST)
        if add_member_form.is_valid():
            username = add_member_form.cleaned_data['username']
            role = add_member_form.cleaned_data['role']
            try:
                user_to_add = User.objects.get(username=username)
                if PodMember.objects.filter(pod=pod, user=user_to_add).exists():
                    messages.warning(request, f"User {username} is already in this Pod.")
                else:
                    PodMember.objects.create(pod=pod, user=user_to_add, role=role)
                    messages.success(request, f"Added {username} to {pod.name}.")
                    return redirect('pod_detail', pod_id=pod.id)
            except User.DoesNotExist:
                messages.error(request, f"User '{username}' does not exist.")
    elif request.method == 'POST' and 'rotate_join_code' in request.POST:
        if not can_manage_members:
            return HttpResponseForbidden('Only admins and this Pod leader can manage its join code.')
        pod.rotate_join_code()
        messages.success(request, f"A new access code was generated for '{pod.name}'. The old code no longer works.")
        return redirect('pod_detail', pod_id=pod.id)
    elif is_admin and request.method == 'POST' and 'assign_mentors' in request.POST:
        assign_mentors_form = AssignMentorsForm(request.POST)
        if assign_mentors_form.is_valid():
            selected_mentors = assign_mentors_form.cleaned_data['mentors']
            with transaction.atomic():
                pod.mentors.exclude(mentor__in=selected_mentors).delete()
                PodMentor.objects.bulk_create(
                    [
                        PodMentor(pod=pod, mentor=mentor)
                        for mentor in selected_mentors
                        if not pod.mentors.filter(mentor=mentor).exists()
                    ]
                )
            messages.success(request, f"Mentors updated for {pod.name}.")
            return redirect('pod_detail', pod_id=pod.id)
    elif can_participate and request.method == 'POST' and 'send_message' in request.POST:
        message_form = PodMessageForm(request.POST)
        if message_form.is_valid():
            PodMessage.objects.create(
                pod=pod,
                author=request.user,
                body=message_form.cleaned_data['body'],
            )
            return redirect('pod_detail', pod_id=pod.id)
    elif can_participate and request.method == 'POST' and 'schedule_meeting' in request.POST:
        meeting_form = PodMeetingForm(request.POST)
        if meeting_form.is_valid():
            PodMeeting.objects.create(
                pod=pod,
                created_by=request.user,
                **meeting_form.cleaned_data,
            )
            messages.success(request, "Pod meeting scheduled.")
            return redirect('pod_detail', pod_id=pod.id)

    context = {
        'pod': pod,
        'members': members,
        'mentors': pod.mentors.select_related('mentor').all(),
        'chat_messages': pod.messages.select_related('author').all(),
        'meetings': pod.meetings.select_related('created_by').all(),
        'is_leader': is_leader,
        'is_member': is_member,
        'is_overseers': is_overseers,
        'is_admin': is_admin,
        'is_mentor': is_mentor,
        'can_manage_members': can_manage_members,
        'can_participate': can_participate,
        'add_member_form': add_member_form,
        'assign_mentors_form': assign_mentors_form,
        'message_form': message_form,
        'meeting_form': meeting_form,
        'can_manage_join_code': can_manage_members,
        'book': book,
        'book_form': book_form,
        'book_review_form': book_review_form,
        'book_weeks': book_weeks,
        'can_manage_book': can_manage_members,
        'can_review_book': can_participate,
    }
    return render(request, 'pods/pod_detail.html', context)


@login_required
def pod_book_file_view(request, pod_id, book_id):
    book = get_object_or_404(PodBook, pk=book_id, pod_id=pod_id)
    if not user_has_pod_access(request.user, book.pod):
        return HttpResponseForbidden('You do not have permission to access this Pod book.')
    return FileResponse(
        book.document.open('rb'),
        as_attachment=True,
        filename=Path(book.document.name).name,
    )


@login_required
@require_POST
def pod_book_review_comment_view(request, pod_id, book_id, review_id):
    book = get_object_or_404(
        PodBook,
        pk=book_id,
        pod_id=pod_id,
        is_current=True,
    )
    if not user_has_pod_access(request.user, book.pod):
        return HttpResponseForbidden('You do not have permission to access this Pod book.')
    if not user_can_participate_in_pod(request.user, book.pod):
        return HttpResponseForbidden('Only Pod participants can comment on book reviews.')

    review = get_object_or_404(PodBookReview, pk=review_id, book=book)
    form = PodBookReviewCommentForm(request.POST)
    if form.is_valid():
        parent = None
        parent_id = form.cleaned_data['parent_id']
        if parent_id:
            parent = get_object_or_404(
                PodBookReviewComment,
                pk=parent_id,
                review=review,
            )
        PodBookReviewComment.objects.create(
            review=review,
            parent=parent,
            author=request.user,
            body=form.cleaned_data['body'],
        )
        messages.success(request, 'Your comment was added to the book review.')
    else:
        messages.error(request, 'Enter a comment before submitting.')

    return redirect(f"{reverse('pod_detail', args=[pod_id])}#book-review-{review.pk}")


@login_required
@require_POST
def pod_delete_view(request, pod_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('Only admins can delete Pods.')

    pod = get_object_or_404(Pod, pk=pod_id)
    files = {}
    pod_lessons = Lesson.objects.filter(
        Q(pod=pod) | Q(module__course__pod=pod)
    ).distinct()
    for lesson in pod_lessons:
        for field in (lesson.audio_file, lesson.pdf_resource):
            if field:
                files[field.name] = field.storage
    for book in pod.reading_books.all():
        if book.document:
            files[book.document.name] = book.document.storage

    pod_name = pod.name
    with transaction.atomic():
        pod_lessons.delete()
        pod.delete()

    for name, storage in files.items():
        lesson_references_file = Lesson.objects.filter(
            Q(audio_file=name) | Q(pdf_resource=name)
        ).exists()
        book_references_file = PodBook.objects.filter(document=name).exists()
        if not lesson_references_file and not book_references_file:
            storage.delete(name)

    messages.success(request, f"Pod '{pod_name}' and its associated data were deleted.")
    return redirect('pod_list')


@login_required
def launch_apprentice_pod_view(request):
    """
    Allows a mentor to appoint an apprentice and launch a new branch Pod for them,
    automatically setting up ApprenticeOversight.
    """
    if request.method == 'POST':
        form = LaunchApprenticePodForm(request.POST, leader=request.user)
        if form.is_valid():
            apprentice_user = form.cleaned_data['apprentice']
            new_pod_name = form.cleaned_data['new_pod_name']
            new_pod_desc = form.cleaned_data['new_pod_description']

            if apprentice_user == request.user:
                messages.error(request, "You cannot appoint yourself as an apprentice.")
                return redirect('launch_apprentice_pod')

            if not PodMember.objects.filter(pod__leader=request.user, user=apprentice_user).exists():
                messages.error(request, "You can only appoint disciples from a pod you lead.")
                return redirect('launch_apprentice_pod')

            # 1. Create new Pod with apprentice as primary leader
            new_pod = Pod.objects.create(
                name=new_pod_name,
                description=new_pod_desc,
                leader=apprentice_user,
                status='active'
            )

            # 2. Set apprentice as LEADER in the new pod
            PodMember.objects.create(pod=new_pod, user=apprentice_user, role='LEADER')

            # 3. Create ApprenticeOversight link for current mentor
            ApprenticeOversight.objects.create(
                mentor=request.user,
                apprentice_pod=new_pod
            )

            # 4. Update apprentice role in mentor's pod to 'APPRENTICE' if not already set
            PodMember.objects.filter(user=apprentice_user, pod__leader=request.user).update(role='APPRENTICE')

            notify_user(request.user, 'Apprentice pod launched', f"You launched '{new_pod.name}' and now oversee {apprentice_user.username}.", '/pods/')
            notify_user(apprentice_user, 'Leadership assigned', f"You were appointed leader of '{new_pod.name}' and now have a mentor oversight relationship.", '/pods/')

            messages.success(
                request, 
                f"Successfully launched Pod '{new_pod.name}' led by {apprentice_user.username}! You have oversight."
            )
            return redirect('pod_list')
    else:
        form = LaunchApprenticePodForm(leader=request.user)

    return render(request, 'pods/launch_apprentice.html', {'form': form})
