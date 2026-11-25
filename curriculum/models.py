from django.db import models
from django.conf import settings
from pods.models import Pod


class Course(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    pod = models.ForeignKey(
        Pod,
        on_delete=models.CASCADE,
        related_name='courses',
        blank=True,
        null=True,
        help_text="Leave blank to publish this course to all learners.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_courses',
    )
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    learning_objectives = models.TextField(blank=True)
    learning_steps = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.course.title}: {self.title}'


class Lesson(models.Model):
    """
    Represents a discipleship lesson containing teaching text, audio messages, and PDF files.
    """
    title = models.CharField(max_length=200, help_text="e.g., Lesson 1: Foundations of Prayer")
    description = models.TextField(blank=True, null=True, help_text="Short summary or learning objectives")
    content = models.TextField(help_text="Detailed teaching text, scripture references, and discussion questions")
    discussion_questions = models.TextField(blank=True, help_text="Optional editor-reviewed questions suggested for discussion.")
    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        related_name='lessons',
        blank=True,
        null=True,
    )
    order = models.PositiveIntegerField(default=0)
    
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

    class Meta:
        ordering = ['order', 'created_at']

    def clone_for_pod(self, target_pod, user):
        """
        Clones this lesson into a target Pod led by the user.
        """
        cloned_lesson = Lesson.objects.create(
            title=f"{self.title} (Pod Edition)",
            description=self.description,
            content=self.content,
            discussion_questions=self.discussion_questions,
            module=None,
            order=self.order,
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


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress_records')
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'lesson'], name='unique_user_lesson_progress'),
        ]
        ordering = ['completed_at']

    def __str__(self):
        return f'{self.user.username} completed {self.lesson.title}'


class ModuleQuiz(models.Model):
    module = models.OneToOneField(Module, on_delete=models.CASCADE, related_name='quiz')
    title = models.CharField(max_length=200)
    passing_score = models.PositiveSmallIntegerField(default=70)

    def __str__(self):
        return f'{self.module.title}: {self.title}'


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(ModuleQuiz, on_delete=models.CASCADE, related_name='questions')
    prompt = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.prompt[:80]


class QuizChoice(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(ModuleQuiz, on_delete=models.CASCADE, related_name='attempts')
    score = models.PositiveSmallIntegerField(default=0)
    passed = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.user.username}: {self.quiz} ({self.score}%)'


class CourseCertificate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_certificates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='certificates')
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'course'], name='unique_user_course_certificate'),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.course.title}'
