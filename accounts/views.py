from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.contrib import messages
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, Mentorship
from pods.models import Pod
from curriculum.models import Lesson
from growth.models import Assignment, Reflection


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
        'recent_users': CustomUser.objects.order_by('-date_joined')[:8],
        'recent_pods': Pod.objects.select_related('leader').order_by('-created_at')[:6],
        'recent_reflections': Reflection.objects.select_related(
            'user', 'assignment'
        ).order_by('-submitted_at')[:6],
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@user_passes_test(admin_required, login_url='login')
def admin_users(request):
    if request.method == 'POST':
        user = get_object_or_404(CustomUser, pk=request.POST.get('user_id'))
        action = request.POST.get('action')
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
        user.save()
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
    }
    return render(request, 'accounts/profile.html', context)