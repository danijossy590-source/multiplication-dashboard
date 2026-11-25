from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm, CustomUserChangeForm, ProfileForm
from .models import CustomUser, Mentorship, Notification
from accounts.utils import notify_user
from pods.models import Pod
from curriculum.models import Lesson
from growth.models import Assignment, Reflection
from community.models import ContentReport
from config.confirmations import render_confirmation


class RoleBasedLoginView(LoginView):
    template_name = 'accounts/login.html'

    def get_success_url(self):
        if self.request.user.is_staff or self.request.user.is_superuser:
            return '/admin/'
        return super().get_success_url()


def admin_required(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@user_passes_test(admin_required, login_url='login')
def admin_dashboard(request):
    context = {
        'total_users': CustomUser.objects.count(),
        'admins': CustomUser.objects.filter(is_staff=True).count(),
        'mentors': CustomUser.objects.filter(role='mentor').count(),
        'mentees': CustomUser.objects.filter(role='mentee').count(),
        'total_pods': Pod.objects.count(),
        'total_lessons': Lesson.objects.count(),
        'total_assignments': Assignment.objects.count(),
        'pending_reflections': Reflection.objects.filter(is_approved=False).count(),
        'pending_question_reports': ContentReport.objects.filter(
            status=ContentReport.Status.PENDING
        ).count(),
        'recent_users': CustomUser.objects.order_by('-date_joined')[:8],
        'recent_pods': Pod.objects.select_related('leader').order_by('-created_at')[:6],
        'recent_reflections': Reflection.objects.select_related(
            'user', 'assignment'
        ).order_by('-submitted_at')[:6],
        'unread_notifications': Notification.objects.filter(user=request.user, is_read=False).count(),
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@user_passes_test(admin_required, login_url='login')
def admin_users(request):
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, pk=request.POST.get('user_id'))
        action = request.POST.get('action')
        if action == 'make_admin' and request.POST.get('confirm_action') != 'yes':
            return render_confirmation(
                request,
                title=f'Grant admin access to {user.username}?',
                message='This gives the account access to administrator tools and platform-wide user management.',
                confirm_label='Grant admin access',
                cancel_url=reverse('admin_users'),
                hidden_fields={'user_id': user.pk, 'action': action},
            )
        previous_role = user.role
        if action == 'make_admin':
            user.role = 'admin'
            user.is_staff = True
            user.is_superuser = True
        elif action == 'make_mentor':
            user.role = 'mentor'
        elif action == 'make_mentee':
            user.role = 'mentee'
        else:
            messages.error(request, "Choose a valid access role.")
            return redirect('admin_users')

        user.save()
        notify_user(
            user,
            'Access updated',
            f"Your role changed from {previous_role} to {user.role}.",
            '/profile/'
        )
        messages.success(request, f"{user.username} was updated.")
        return redirect('admin_users')

    users = CustomUser.objects.order_by('-date_joined')
    return render(request, 'accounts/admin_users.html', {'users': users})


def landing_view(request):
    return render(request, 'landing.html')


def register_view(request):
    """
    Handles new user registration using CustomUserCreationForm.
    Automatically logs the user in upon successful account creation.
    """
    if request.user.is_authenticated:
        return redirect('profile')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            notify_user(
                user,
                'Welcome to Multiply',
                'Your account is ready. Start by joining a pod and completing your first lesson.',
                '/profile/'
            )
            messages.success(
                request, 
                f"Welcome to Multiply, {user.username}! Your account was created successfully."
            )
            return redirect('profile')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = CustomUserCreationForm()

    return render(request, 'sign_up.html', {'form': form})


@login_required
def profile_view(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('admin_dashboard')

    mentors = Mentorship.objects.filter(mentee=request.user).select_related('mentor')
    mentees = Mentorship.objects.filter(mentor=request.user).select_related('mentee')

    context = {
        'user': request.user,
        'mentors': mentors,
        'mentees': mentees,
        'recent_notifications': request.user.notifications.filter(is_read=False)[:5],
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def edit_profile_view(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('admin_dashboard')

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile was updated.")
            return redirect('profile')
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'accounts/edit_profile.html', {'form': form})


@login_required
def notifications_view(request):
    notifications = request.user.notifications.all()
    return render(request, 'accounts/notifications.html', {'notifications': notifications})


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    messages.success(request, 'Notification marked as read.')
    return redirect('notifications')