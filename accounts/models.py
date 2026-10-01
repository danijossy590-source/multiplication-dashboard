from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('mentor', 'Mentor'),
        ('mentee', 'Mentee'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='mentee')
    bio = models.TextField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.username


class Mentorship(models.Model):
    mentor = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='mentorship_mentors'
    )
    mentee = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='mentorship_mentees'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('mentor', 'mentee')

    def __str__(self):
        return f"{self.mentor.username} -> {self.mentee.username}"