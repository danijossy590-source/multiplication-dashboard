from django.db import models
from django.conf import settings
from curriculum.models import Lesson
from pods.models import Pod

class Assignment(models.Model):
    """
    Practical real-world challenge or action item derived from a Lesson or Pod.
    """
    lesson = models.ForeignKey(
        Lesson, 
        on_delete=models.CASCADE, 
        related_name='assignments',
        null=True, 
        blank=True,
        help_text="The lesson this practical challenge is tied to."
    )
    pod = models.ForeignKey(
        Pod,
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True,
        blank=True,
        help_text="Optional: Limit challenge to a specific Pod."
    )
    title = models.CharField(max_length=200)
    instruction = models.TextField(help_text="Detailed practical challenge instructions for disciples.")
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_assignments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Challenge: {self.title}"


class Reflection(models.Model):
    """
    A disciple's submission responding to an Assignment.
    Supports written text and audio recordings, with mentor review fields.
    """
    assignment = models.ForeignKey(
        Assignment, 
        on_delete=models.CASCADE, 
        related_name='reflections'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='reflections'
    )
    written_content = models.TextField(
        help_text="Written reflection on what was learned or experienced during the challenge."
    )
    audio_reflection = models.FileField(
        upload_to='audio_reflections/', 
        blank=True, 
        null=True,
        help_text="Upload an MP3/WAV audio note reflecting on the assignment."
    )
    mentor_feedback = models.TextField(
        blank=True, 
        null=True,
        help_text="Constructive feedback from the leader or mentor."
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="Mark as approved when the mentor verifies the completion of the challenge."
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        unique_together = ('assignment', 'user')

    def __str__(self):
        return f"Reflection by {self.user.username} on '{self.assignment.title}'"
