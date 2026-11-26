from django.db import migrations


def make_existing_lessons_master_templates(apps, schema_editor):
    Lesson = apps.get_model('curriculum', 'Lesson')
    Lesson.objects.using(schema_editor.connection.alias).update(is_master_template=True)


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0005_course_default_published'),
    ]

    operations = [
        migrations.RunPython(
            make_existing_lessons_master_templates,
            migrations.RunPython.noop,
        ),
    ]
