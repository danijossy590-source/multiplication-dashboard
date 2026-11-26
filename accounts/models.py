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

    def save(self, *args, **kwargs):
        admin_values = {
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True,
        }
        synchronized_fields = set()
        if self.role == 'admin' or self.is_staff or self.is_superuser:
            for field, value in admin_values.items():
                if getattr(self, field) != value:
                    setattr(self, field, value)
                    synchronized_fields.add(field)

        update_fields = kwargs.get('update_fields')
        if update_fields is not None and synchronized_fields:
            kwargs['update_fields'] = set(update_fields) | synchronized_fields

        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_url = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}: {self.title}'


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