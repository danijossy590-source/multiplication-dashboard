from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from .models import Pod, PodMember, ApprenticeOversight
from .forms import PodForm, AddMemberForm, LaunchApprenticePodForm

User = get_user_model()

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
    }
    return render(request, 'pods/pod_list.html', context)


@login_required
def pod_create_view(request):
    """
    Creates a new Pod and automatically adds the user as Leader.
    """
    if request.method == 'POST':
        form = PodForm(request.POST)
        if form.is_valid():
            pod = form.save(commit=False)
            pod.leader = request.user
            pod.save()
            
            # Automatically create PodMember record for the leader
            PodMember.objects.create(pod=pod, user=request.user, role='LEADER')
            messages.success(request, f"Pod '{pod.name}' created successfully!")
            return redirect('pod_detail', pod_id=pod.id)
    else:
        form = PodForm()

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

    # Access security check
    if not (is_leader or is_member or is_overseers or request.user.is_staff):
        messages.error(request, "You do not have permission to view this Pod.")
        return redirect('pod_list')

    members = pod.memberships.select_related('user').all()

    # Form to add members (only visible to leader)
    add_member_form = AddMemberForm()
    if is_leader and request.method == 'POST' and 'add_member' in request.POST:
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

    context = {
        'pod': pod,
        'members': members,
        'is_leader': is_leader,
        'is_member': is_member,
        'is_overseers': is_overseers,
        'add_member_form': add_member_form,
    }
    return render(request, 'pods/pod_detail.html', context)


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

            # 1. Create new Pod with apprentice as primary leader
            new_pod = Pod.objects.create(
                name=new_pod_name,
                description=new_pod_desc,
                leader=apprentice_user
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

            messages.success(
                request, 
                f"Successfully launched Pod '{new_pod.name}' led by {apprentice_user.username}! You have oversight."
            )
            return redirect('pod_list')
    else:
        form = LaunchApprenticePodForm(leader=request.user)

    return render(request, 'pods/launch_apprentice.html', {'form': form})


