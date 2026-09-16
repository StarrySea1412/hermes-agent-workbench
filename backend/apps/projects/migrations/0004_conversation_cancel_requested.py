from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_conversation_model_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='cancel_requested',
            field=models.BooleanField(default=False),
        ),
    ]
