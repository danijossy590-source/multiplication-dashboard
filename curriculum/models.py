from django.db import models
from django.conf import settings
from pods.models import Pod

class Lesson(models.Model):
    """
    Represents a discipleship lesson containing teaching text, audio messages, and PDF files.
    """
    title = models.CharField(max_length=200, help_text="e.g., Lesson 1: Foundations of Prayer")
    description = models.TextField(blank=True, null=True, help_text="Short summary or learning objectives")
    content = models.TextField(help_text="Detailed teaching text, scripture references, and discussion questions")
    
    # File attachments
    audio_file = models.FileField(
        upload_to='lessons/audio/', 
        blank=True, 
        null=True, 
        help_text="Upload MP3 or audio teaching file"
    )
    pdf_resource = models.FileField(
        upload_to='lessons/pdf/', 
        blank=True, 
        null=True, 
        help_text="Upload printable PDF study guide or worksheet"
    )
    
    # Ownership & Relational Context
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_lessons'
    )
    pod = models.ForeignKey(
        Pod, 
        on_delete=models.CASCADE, 
        related_name='pod_lessons', 
        blank=True, 
        null=True, 
        help_text="If blank, this lesson is part of the Master Global Curriculum."
    )
    is_master_template = models.BooleanField(
        default=False, 
        help_text="Master lessons are visible to all leaders for cloning."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clone_for_pod(self, target_pod, user):
        """
        Clones this lesson into a target Pod led by the user.
        """
        cloned_lesson = Lesson.objects.create(
            title=f"{self.title} (Pod Edition)",
            description=self.description,
            content=self.content,
            audio_file=self.audio_file,
            pdf_resource=self.pdf_resource,
            created_by=user,
            pod=target_pod,
            is_master_template=False
        )
        return cloned_lesson

    def __str__(self):
        if self.pod:
            return f"{self.title} [Pod: {self.pod.name}]"
        return f"{self.title} [Master Curriculum]"
