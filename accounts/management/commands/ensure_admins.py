import os

from django.core.management.base import BaseCommand

from accounts.models import CustomUser


class Command(BaseCommand):
    help = "Create or update configured Django administrator accounts"

    def handle(self, *args, **options):
        configured = False

        for index in (1, 2):
            username = os.getenv(f"DJANGO_ADMIN_{index}_USERNAME")
            email = os.getenv(f"DJANGO_ADMIN_{index}_EMAIL")
            password = os.getenv(f"DJANGO_ADMIN_{index}_PASSWORD")

            if not all((username, email, password)):
                continue

            configured = True
            user, _ = CustomUser.objects.get_or_create(username=username)
            user.email = email
            user.role = "admin"
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Administrator '{username}' is ready"))

        if not configured:
            self.stdout.write("No administrator environment variables configured")
