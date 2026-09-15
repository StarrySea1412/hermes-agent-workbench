from rest_framework import serializers
from django.conf import settings


class AIConfigSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    provider = serializers.CharField(max_length=64)
    base_url = serializers.CharField(max_length=256)
    model_name = serializers.CharField(max_length=128)
    embedding_model_name = serializers.CharField(max_length=128, allow_blank=True)
    temperature = serializers.FloatField()
    max_tokens = serializers.IntegerField()
    is_active = serializers.BooleanField()


class AIConfigCreateSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64, default=settings.AI_DEFAULT_PROVIDER)
    api_key = serializers.CharField(min_length=1, write_only=True)
    base_url = serializers.CharField(max_length=256)
    model_name = serializers.CharField(max_length=128)
    temperature = serializers.FloatField(default=0.7, min_value=0.0, max_value=2.0)
    max_tokens = serializers.IntegerField(default=2000, min_value=100, max_value=32000)


class AIConfigUpdateSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64, required=False)
    api_key = serializers.CharField(required=False)
    base_url = serializers.CharField(max_length=256, required=False)
    model_name = serializers.CharField(max_length=128, required=False)
    embedding_model_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    temperature = serializers.FloatField(min_value=0.0, max_value=2.0, required=False)
    max_tokens = serializers.IntegerField(min_value=100, max_value=32000, required=False)
    is_active = serializers.BooleanField(required=False)


class AIModelListRequestSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64, required=False, allow_blank=True)
    api_key = serializers.CharField(required=False, allow_blank=True, write_only=True)
    base_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    is_full_url = serializers.BooleanField(required=False, default=False)
    models_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    user_agent = serializers.CharField(max_length=256, required=False, allow_blank=True)
