from django.conf import settings
from django.db import models


class AIConfig(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_config')
    provider = models.CharField(max_length=64, default='openai')
    api_key_encrypted = models.CharField(max_length=512)
    base_url = models.CharField(max_length=256, default='https://api.openai.com/v1')
    model_name = models.CharField(max_length=128, default='gpt-4o-mini')
    embedding_model_name = models.CharField(max_length=128, blank=True, default='')
    temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=2000)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_configs'

    def __str__(self):
        return f"{self.user.username} - {self.provider}"
