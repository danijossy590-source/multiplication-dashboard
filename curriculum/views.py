
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Lesson
from .forms import LessonForm, TeachThisForm
from pods.models import Pod

@login_required
def lesson_list_view(request):
    """
    Displays:
    1. Master Curriculum Templates.
    2. Lessons specific to Pods the user participates in or leads.
    """
    master_lessons = Lesson.objects.filter(is_master_template=True).order_by('-created_at')
    
    # Retrieve all Pod IDs where the user is either a Leader or Member
    leading_pod_ids = request.user.leading_pods.values_list('id', flat=True)
    membership_pod_ids = request.user.pod_memberships.values_list('pod_id', flat=True)
    all_user_pod_ids = list(set(list(leading_pod_ids) + list(membership_pod_ids)))

    pod_lessons = Lesson.objects.filter(pod_id__in=all_user_pod_ids).select_related('pod', 'created_by').order_by('-created_at')

    context = {
        'master_lessons': master_lessons,
        'pod_lessons': pod_lessons,
    }
    return render(request, 'curriculum/lesson_list.html', context)


@login_required
def lesson_detail_view(request, lesson_id):
    """
    Displays full lesson text, HTML5 audio playback player, PDF download links,
    and the 'Teach This' button for eligible leaders.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)
    
    # Check if the current user is a leader of at least one pod
    user_is_a_leader = request.user.leading_pods.exists()

    context = {
        'lesson': lesson,
        'user_is_a_leader': user_is_a_leader,
    }
    return render(request, 'curriculum/lesson_detail.html', context)


@login_required
def lesson_create_view(request):
    """
    Allows instructors or leaders to upload new lessons and attached media files.
    """
    if request.method == 'POST':
        # MUST pass request.FILES to handle uploaded audio/PDF files
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.created_by = request.user
            lesson.save()
            messages.success(request, f"Lesson '{lesson.title}' uploaded successfully!")
            return redirect('lesson_list')
    else:
        form = LessonForm()

    return render(request, 'curriculum/lesson_form.html', {'form': form, 'title': 'Create & Upload Lesson'})


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
