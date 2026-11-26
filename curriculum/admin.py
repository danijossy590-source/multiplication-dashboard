from django.contrib import admin
from .models import Course, Lesson, Module


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ('title', 'order', 'description', 'learning_objectives', 'learning_steps')
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'pod', 'is_published', 'created_by', 'created_at')
    list_filter = ('is_published', 'pod')
    search_fields = ('title', 'description', 'created_by__username')
    readonly_fields = ('created_by', 'created_at')
    inlines = (ModuleInline,)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'course__title')


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'pod', 'is_master_template', 'created_by', 'created_at')
    list_filter = ('is_master_template', 'pod')
    search_fields = ('title', 'description', 'content', 'module__course__title')
    readonly_fields = ('created_by', 'created_at')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        if obj.module_id:
            course = obj.module.course
            obj.pod = course.pod
            obj.is_master_template = course.pod_id is None
        super().save_model(request, obj, form, change)
