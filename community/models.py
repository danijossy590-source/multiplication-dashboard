from django.conf import settings
from django.db import models
from django.db.models import Q


class Question(models.Model):
    title = models.CharField(max_length=180)
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='community_questions',
        blank=True,
        null=True,
    )
    display_name = models.CharField(max_length=80, blank=True)
    is_anonymous = models.BooleanField(default=True)
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def public_author(self):
        if self.is_anonymous:
            return 'Anonymous'
        return self.display_name or 'Guest'

    def __str__(self):
        return self.title


class Reply(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='replies')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        related_name='children',
        blank=True,
        null=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='community_replies',
        blank=True,
        null=True,
    )
    display_name = models.CharField(max_length=80)
    body = models.TextField()
    is_anonymous = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    @property
    def public_author(self):
        if self.is_anonymous:
            return 'Anonymous'
        return self.display_name or 'Member'

    def __str__(self):
        return f'Reply to {self.question.title}'


class ContentReport(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        REVIEWED = 'reviewed', 'Reviewed'
        DISMISSED = 'dismissed', 'Dismissed'

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_reports',
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='reports',
        blank=True,
        null=True,
    )
    reply = models.ForeignKey(
        Reply,
        on_delete=models.CASCADE,
        related_name='reports',
        blank=True,
        null=True,
    )
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['status', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(question__isnull=False, reply__isnull=True)
                    | Q(question__isnull=True, reply__isnull=False)
                ),
                name='community_report_exactly_one_target',
            ),
            models.UniqueConstraint(
                fields=['reporter', 'question'],
                condition=Q(question__isnull=False),
                name='community_unique_question_report',
            ),
            models.UniqueConstraint(
                fields=['reporter', 'reply'],
                condition=Q(reply__isnull=False),
                name='community_unique_reply_report',
            ),
        ]

    def __str__(self):
        target = self.question or self.reply
        return f'{self.get_status_display()} report: {target}'
