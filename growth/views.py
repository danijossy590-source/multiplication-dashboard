from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Assignment, Reflection
from .forms import AssignmentForm, ReflectionForm, MentorFeedbackForm
from django.http import JsonResponse
from django.db.models import Count, Q
from accounts.utils import get_multiplication_stats, build_discipleship_tree, notify_user
from pods.models import Pod
from community.models import Question

@login_required
def assignment_create_view(request):
    """
    Allows mentors and leaders to create a new action assignment.
    """
    if not (request.user.is_staff or request.user.is_superuser or request.user.leading_pods.exists()):
        messages.error(request, "Only staff or pod leaders can create assignments.")
        return redirect('multiplication_dashboard')

    if request.method == 'POST':
        form = AssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.created_by = request.user
            assignment.status = 'published'
            assignment.save()
            if assignment.pod:
                for member in assignment.pod.memberships.select_related('user').all():
                    notify_user(member.user, 'New challenge assigned', f"A new challenge '{assignment.title}' was shared in {assignment.pod.name}.", '/growth/dashboard/')
            messages.success(request, f"Challenge '{assignment.title}' published successfully!")
            return redirect('multiplication_dashboard')
    else:
        form = AssignmentForm()

    return render(request, 'growth/assignment_form.html', {'form': form})


@login_required
def reflection_submit_view(request, assignment_id):
    """
    Allows disciples to submit written or audio reflections for an assignment.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check if user has already submitted a reflection
    existing_reflection = Reflection.objects.filter(assignment=assignment, user=request.user).first()

    if request.method == 'POST':
        form = ReflectionForm(request.POST, request.FILES, instance=existing_reflection)
        if form.is_valid():
            reflection = form.save(commit=False)
            reflection.assignment = assignment
            reflection.user = request.user
            reflection.status = 'pending'
            reflection.save()
            messages.success(request, "Your reflection has been submitted successfully!")
            return redirect('multiplication_dashboard')
    else:
        form = ReflectionForm(instance=existing_reflection)

    context = {
        'assignment': assignment,
        'form': form,
        'existing_reflection': existing_reflection,
    }
    return render(request, 'growth/reflection_form.html', context)


@login_required
def reflection_detail_view(request, reflection_id):
    """
    Detailed view of a reflection where mentors can review submissions, 
    listen to audio files, and submit feedback/approvals.
    """
    reflection = get_object_or_404(Reflection, id=reflection_id)
    
    # Mentor access check: must be staff, creator of assignment, or leader of associated pod
    is_mentor = (
        request.user.is_staff or 
        reflection.assignment.created_by == request.user or
        (reflection.assignment.pod and reflection.assignment.pod.leader == request.user)
    )

    if request.method == 'POST' and is_mentor:
        feedback_form = MentorFeedbackForm(request.POST, instance=reflection)
        if feedback_form.is_valid():
            updated_reflection = feedback_form.save(commit=False)
            updated_reflection.reviewed_at = timezone.now()
            updated_reflection.status = 'approved' if updated_reflection.is_approved else 'rejected'
            updated_reflection.save()
            notify_user(
                reflection.user,
                'Reflection reviewed',
                f"Your reflection for '{reflection.assignment.title}' was {'approved' if updated_reflection.is_approved else 'rejected'}.",
                '/profile/'
            )
            messages.success(request, "Feedback and review saved successfully!")
            return redirect('reflection_detail', reflection_id=reflection.id)
    else:
        feedback_form = MentorFeedbackForm(instance=reflection)

    context = {
        'reflection': reflection,
        'feedback_form': feedback_form,
        'is_mentor': is_mentor,
    }
    return render(request, 'growth/reflection_detail.html', context)

@login_required
def multiplication_dashboard_view(request):
    """
    Renders the Multiplication Dashboard with visual relational tree and growth metrics.
    """
    user = request.user
    stats = get_multiplication_stats(user)
    
    # Recent activity
    recent_reflections = Reflection.objects.filter(
        assignment__created_by=user
    ).select_related('user', 'assignment').order_by('-submitted_at')[:5]

    active_pods = Pod.objects.filter(leader=user)
    recent_questions = (
        Question.objects.filter(is_hidden=False)
        .annotate(visible_reply_count=Count('replies', filter=Q(replies__is_hidden=False)))
        .order_by('-created_at')[:3]
    )

    context = {
        'stats': stats,
        'recent_reflections': recent_reflections,
        'active_pods': active_pods,
        'recent_questions': recent_questions,
        'can_create_assignments': (
            request.user.is_staff
            or request.user.is_superuser
            or request.user.leading_pods.exists()
        ),
    }
    return render(request, 'growth/multiplication_dashboard.html', context)


@login_required
def discipleship_tree_api(request):
    """
    API endpoint that returns JSON structured tree data for dynamic frontend charts (e.g., D3.js or Vis.js).
    """
    tree_data = build_discipleship_tree(request.user)
    return JsonResponse({'name': request.user.get_full_name() or request.user.username, 'children': tree_data})
