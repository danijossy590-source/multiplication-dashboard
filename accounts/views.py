import smtplib

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm, CustomUserChangeForm, ProfileForm
from .models import CustomUser, Mentorship, Notification
from accounts.utils import notify_user
from accounts.tokens import account_verification_token
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
            user.is_staff = False
            user.is_superuser = False
        elif action == 'make_mentee':
            user.role = 'mentee'
            user.is_staff = False
            user.is_superuser = False
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
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            uid = urlsafe_base64_encode(str(user.pk).encode())
            token = account_verification_token.make_token(user)
            verification_url = request.build_absolute_uri(
                reverse('verify_account', kwargs={'uidb64': uid, 'token': token})
            )
            try:
                send_mail(
                    'Verify your Multiply account',
                    (
                        f'Hello {user.get_username()},\n\n'
                        'Please verify your email address to activate your Multiply account:\n'
                        f'{verification_url}\n\n'
                        'If you did not create this account, you can ignore this email.'
                    ),
                    None,
                    [user.email],
                    fail_silently=False,
                )
            except (smtplib.SMTPException, OSError):
                user.delete()
                messages.error(
                    request,
                    'We could not send the verification email. Please try again later.',
                )
            else:
                return redirect('verification_email_sent')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = CustomUserCreationForm()

    return render(request, 'sign_up.html', {'form': form})


def verification_email_sent_view(request):
    return render(request, 'accounts/verification_email_sent.html')


def verify_account_view(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is None or user.is_active or not account_verification_token.check_token(user, token):
        messages.error(request, 'This verification link is invalid or has expired.')
        return redirect('login')

    user.is_active = True
    user.save(update_fields=['is_active'])
    notify_user(
        user,
        'Welcome to Multiply',
        'Your account is ready. Start by joining a pod and completing your first lesson.',
        '/profile/',
    )
    messages.success(request, 'Your email is verified. You can now log in.')
    return redirect('login')


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