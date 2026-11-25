from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0004_module_learning_objectives_module_learning_steps'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='is_published',
            field=models.BooleanField(default=True),
        ),
    ]
