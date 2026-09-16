from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_chat_workbench_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='model_override',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
