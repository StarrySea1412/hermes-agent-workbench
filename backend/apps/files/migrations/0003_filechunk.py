from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0002_alter_uploadedfile_file_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FileChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_name', models.CharField(max_length=255)),
                ('chunk_index', models.PositiveIntegerField()),
                ('content', models.TextField()),
                ('embedding', models.BinaryField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='files.uploadedfile')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='file_chunks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'file_chunks',
                'indexes': [
                    models.Index(fields=['user'], name='file_chunks_user_id_idx'),
                    models.Index(fields=['file'], name='file_chunks_file_id_idx'),
                ],
            },
        ),
    ]
