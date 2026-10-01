from django.contrib import admin
from .models import Assignment, Reflection

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'pod', 'due_date', 'created_by', 'created_at')
    list_filter = ('due_date', 'created_at')
    search_fields = ('title', 'instruction')

@admin.register(Reflection)
class ReflectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'assignment', 'is_approved', 'submitted_at')
    list_filter = ('is_approved', 'submitted_at')
    search_fields = ('user__username', 'assignment__title', 'written_content')
