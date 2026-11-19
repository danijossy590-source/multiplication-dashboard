from django.contrib import admin
from .models import ContentReport, Question, Reply


@admin.action(description='Hide selected questions')
def hide_questions(modeladmin, request, queryset):
    queryset.update(is_hidden=True)


@admin.action(description='Show selected questions')
def show_questions(modeladmin, request, queryset):
    queryset.update(is_hidden=False)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'public_author', 'is_anonymous', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'is_anonymous', 'created_at')
    search_fields = ('title', 'body', 'display_name', 'author__username')
    readonly_fields = ('author', 'created_at')
    actions = [hide_questions, show_questions]


@admin.action(description='Hide selected replies')
def hide_replies(modeladmin, request, queryset):
    queryset.update(is_hidden=True)


@admin.action(description='Show selected replies')
def show_replies(modeladmin, request, queryset):
    queryset.update(is_hidden=False)


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ('question', 'parent', 'public_author', 'is_anonymous', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'is_anonymous', 'created_at')
    search_fields = ('body', 'display_name', 'author__username', 'question__title')
    readonly_fields = ('author', 'created_at')
    actions = [hide_replies, show_replies]


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'target', 'reporter', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reason', 'reporter__username', 'question__title', 'reply__body')
    readonly_fields = ('reporter', 'question', 'reply', 'reason', 'created_at')
    list_editable = ('status',)

    @admin.display(description='Reported content')
    def target(self, report):
        return report.question or report.reply
