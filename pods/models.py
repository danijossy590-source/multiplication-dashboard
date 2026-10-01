from django.db import models
from django.conf import settings

class Pod(models.Model):
    """
    Represents an intimate small group (Pod) for discipleship.
    """
    name = models.CharField(max_length=150, help_text="e.g., Faith Walk Pod Alpha")
    description = models.TextField(blank=True, null=True, help_text="Brief purpose or focus of this pod")
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='leading_pods',
        help_text="The primary leader/mentor of this Pod"
    )
    created_at = models.DateTimeField(auto_now_add=True)

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