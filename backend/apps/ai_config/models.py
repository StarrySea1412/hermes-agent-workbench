from django.conf import settings
from django.db import models


class AIConfig(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_config')
    provider = models.CharField(max_length=64, default='openai')
    api_key_encrypted = models.CharField(max_length=512)
    base_url = models.CharField(max_length=256, default='https://api.openai.com/v1')
    model_name = models.CharField(max_length=128, default='gpt-4o-mini')
    temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=2000)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_configs'

    def __str__(self):
        return f"{self.user.username} - {self.provider}"


class GenerationTask(models.Model):
    """异步章节生成任务

    前端提交生成请求后，后端创建一条记录并入 Celery 队列，秒回 task_id；
    Celery worker 慢慢生成，把结果/错误回写。前端轮询状态。
    """

    STATUS_CHOICES = [
        ('pending', '排队中'),
        ('running', '生成中'),
        ('done', '已完成'),
        ('failed', '失败'),
    ]
    MODE_CHOICES = [
        ('fast', '快速生成'),
        ('hermes', 'Hermes 深度生成'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='generation_tasks',
    )
    chapter = models.ForeignKey(
        'bids.BidChapter',
        on_delete=models.CASCADE,
        related_name='generation_tasks',
    )
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default='fast')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)

    # 用户提交时的输入快照（任务异步执行，不能依赖前端再传一次）
    prompt = models.TextField(blank=True, default='')
    context = models.TextField(blank=True, default='')
    skill = models.CharField(max_length=128, blank=True, default='')

    # 生成结果（done 时填充）
    result = models.JSONField(null=True, blank=True)  # {content: [...], generated_text: "..."}

    # 失败原因（failed 时填充）
    error = models.TextField(blank=True, default='')

    # Celery 内部任务 id（用于日志关联 / 撤销）
    celery_task_id = models.CharField(max_length=128, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'generation_tasks'
        ordering = ['-created_at']
        verbose_name = '生成任务'
        verbose_name_plural = '生成任务'

    def __str__(self):
        return f"Task#{self.id} [{self.mode}] {self.status} (user={self.user_id} ch={self.chapter_id})"
