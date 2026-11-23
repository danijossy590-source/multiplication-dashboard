import secrets

from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q
from django.utils import timezone

class Pod(models.Model):
    """
    Represents an intimate small group (Pod) for discipleship.
    """
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('archived', 'Archived'),
    )

    name = models.CharField(max_length=150, help_text="e.g., Faith Walk Pod Alpha")
    description = models.TextField(blank=True, null=True, help_text="Brief purpose or focus of this pod")
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='leading_pods',
        help_text="The primary leader/mentor of this Pod"
    )
    join_code = models.CharField(max_length=24, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def _new_join_code(self):
        while True:
            code = secrets.token_urlsafe(12)
            if not Pod.objects.filter(join_code=code).exclude(pk=self.pk).exists():
                return code

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = self._new_join_code()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'join_code'}
        super().save(*args, **kwargs)

    def rotate_join_code(self):
        self.join_code = self._new_join_code()
        self.save(update_fields=['join_code'])
        return self.join_code

    def __str__(self):
        return f"{self.name} (Leader: {self.leader.username})"


class PodMember(models.Model):
    """
    Links users to Pods with specific roles.
    Allows a user to have different roles in different Pods.
    """
    ROLE_CHOICES = (
        ('MEMBER', 'Member / Disciple'),
        ('APPRENTICE', 'Apprentice Leader'),
        ('LEADER', 'Primary Leader'),
    )

    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pod_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='MEMBER')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevents a user from being added to the same Pod twice
        unique_together = ('pod', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.pod.name} as {self.get_role_display()}"


class ApprenticeOversight(models.Model):
    """
    Connects a primary mentor to a Pod led by their apprentice.
    Gives the primary mentor silent read-only oversight.
    """
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='overseeing_pods',
        help_text="The senior mentor giving oversight"
    )
    apprentice_pod = models.ForeignKey(
        Pod, 
        on_delete=models.CASCADE, 
        related_name='oversights',
        help_text="The Pod led by the apprentice"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('mentor', 'apprentice_pod')

    def __str__(self):
        return f"Mentor {self.mentor.username} overseeing Pod '{self.apprentice_pod.name}'"


class PodMentor(models.Model):
    """A mentor assigned to participate in a Pod."""
    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name='mentors')
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mentored_pods',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('pod', 'mentor')

    def __str__(self):
        return f"{self.mentor.username} mentoring {self.pod.name}"


class PodMessage(models.Model):
    """A message posted to a Pod's group chat."""
    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pod_messages',
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.author.username} in {self.pod.name}"


class PodMeeting(models.Model):
    """A scheduled meeting for Pod members."""
    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name='meetings')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_pod_meetings',
    )
    title = models.CharField(max_length=150)
    details = models.TextField(blank=True)
    scheduled_at = models.DateTimeField()
    meeting_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.title} - {self.pod.name}"


class PodBook(models.Model):
    """A book assignment and reading schedule for a Pod."""
    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name='reading_books')
    title = models.CharField(max_length=200)
    document = models.FileField(upload_to='pods/books/')
    reader_pdf = models.FileField(upload_to='pods/books/readers/', blank=True)
    duration_weeks = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
    )
    started_on = models.DateField(default=timezone.localdate)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_pod_books',
    )
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['pod'],
                condition=Q(is_current=True),
                name='unique_pod_current_book',
            ),
        ]

    def __str__(self):
        return f'{self.title} - {self.pod.name}'


class PodBookSection(models.Model):
    book = models.ForeignKey(PodBook, on_delete=models.CASCADE, related_name='sections')
    week_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    start_page = models.PositiveSmallIntegerField()
    end_page = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['week_number', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['book', 'week_number'],
                name='unique_pod_book_week_section',
            ),
        ]

    def __str__(self):
        return f'{self.book.title}: week {self.week_number} - {self.title}'


class PodBookSectionProgress(models.Model):
    section = models.ForeignKey(
        PodBookSection,
        on_delete=models.CASCADE,
        related_name='progress_records',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pod_book_section_progress',
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['section', 'user'],
                name='unique_pod_book_section_progress',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} completed {self.section}'


class PodBookReview(models.Model):
    """A participant's weekly review of a Pod book."""
    book = models.ForeignKey(PodBook, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pod_book_reviews',
    )
    week_number = models.PositiveSmallIntegerField()
    review = models.TextField(max_length=5000)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['week_number', 'submitted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['book', 'user', 'week_number'],
                name='unique_pod_book_week_review',
            ),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.book.title} (week {self.week_number})'


class PodBookReviewComment(models.Model):
    """A Pod participant's comment or nested reply on a weekly review."""
    review = models.ForeignKey(
        PodBookReview,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        related_name='replies',
        blank=True,
        null=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='pod_book_review_comments',
        blank=True,
        null=True,
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Comment on {self.review}'