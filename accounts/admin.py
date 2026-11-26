from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Mentorship, Notification
from .forms import AdminUserCreationForm, CustomUserChangeForm

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = AdminUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = ['username', 'email', 'role', 'phone_number', 'is_staff', 'is_superuser']
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Fields', {'fields': ('role', 'bio', 'phone_number')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'role', 'phone_number', 'bio', 'password1', 'password2'),
        }),
    )

@admin.register(Mentorship)
class MentorshipAdmin(admin.ModelAdmin):
    list_display = ['mentor', 'mentee', 'created_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['title', 'message', 'user__username']