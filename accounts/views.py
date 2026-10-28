from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, Mentorship


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
    mentors = Mentorship.objects.filter(mentee=request.user).select_related('mentor')
    mentees = Mentorship.objects.filter(mentor=request.user).select_related('mentee')

    context = {
        'user': request.user,
        'mentors': mentors,
        'mentees': mentees,
    }
    return render(request, 'accounts/profile.html', context)