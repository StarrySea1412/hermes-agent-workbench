from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_config', '0005_delete_generationtask'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiconfig',
            name='embedding_model_name',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
