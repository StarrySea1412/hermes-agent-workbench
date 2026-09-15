import os
from django.db import models
from django.conf import settings


def upload_to(instance, filename):
    return f'uploads/{instance.user_id}/{filename}'


class UploadedFile(models.Model):
    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('md', 'Markdown'),
        ('docx', 'Word'),
        ('doc', 'Word 97-2003'),
        ('txt', '文本'),
        ('other', '其他'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_files',
        verbose_name='用户',
    )
    file = models.FileField('文件', upload_to=upload_to)
    original_name = models.CharField('原始文件名', max_length=255)
    file_type = models.CharField('文件类型', max_length=10, choices=FILE_TYPE_CHOICES, default='other')
    file_size = models.PositiveIntegerField('文件大小(字节)')
    description = models.CharField('描述', max_length=500, blank=True, default='')
    created_at = models.DateTimeField('上传时间', auto_now_add=True)

    class Meta:
        db_table = 'uploaded_files'
        ordering = ['-created_at']
        verbose_name = '上传文件'
        verbose_name_plural = '上传文件'

    def __str__(self):
        return self.original_name

    @property
    def file_size_display(self):
        size = self.file_size
        if size < 1024:
            return f'{size} B'
        if size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        return f'{size / (1024 * 1024):.1f} MB'

    def delete(self, *args, **kwargs):
        if self.file and os.path.isfile(self.file.path):
            os.remove(self.file.path)
        super().delete(*args, **kwargs)


class FileChunk(models.Model):
    """上传文件的向量分块，聊天检索直接查这张表。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='file_chunks',
    )
    file = models.ForeignKey(
        UploadedFile,
        on_delete=models.CASCADE,
        related_name='chunks',
    )
    file_name = models.CharField(max_length=255)
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'file_chunks'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['file']),
        ]
