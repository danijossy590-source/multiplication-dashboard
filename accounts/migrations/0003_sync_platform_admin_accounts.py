from django.db import migrations
from django.db.models import Q


def synchronize_admin_accounts(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.using(schema_editor.connection.alias).filter(
        Q(role='admin') | Q(is_staff=True) | Q(is_superuser=True)
    ).update(
        role='admin',
        is_staff=True,
        is_superuser=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_notification'),
    ]

    operations = [
        migrations.RunPython(
            synchronize_admin_accounts,
            migrations.RunPython.noop,
        ),
    ]
