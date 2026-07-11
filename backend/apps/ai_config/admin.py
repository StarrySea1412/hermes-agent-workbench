from django.contrib import admin
from unfold.admin import ModelAdmin
from apps.ai_config.models import AIConfig


@admin.register(AIConfig)
class AIConfigAdmin(ModelAdmin):
    list_display = ['id', 'user', 'provider', 'model_name', 'base_url', 'temperature', 'max_tokens', 'is_active', 'updated_at']
    list_display_links = ['id', 'user']
    list_filter = ['provider', 'is_active']
    search_fields = ['user__username', 'model_name']
    list_per_page = 20
    readonly_fields = ['api_key_masked', 'created_at', 'updated_at']
    fieldsets = (
        ('用户', {
            'fields': ('user',)
        }),
        ('模型配置', {
            'fields': ('provider', 'model_name', 'base_url')
        }),
        ('参数', {
            'fields': ('temperature', 'max_tokens', 'is_active')
        }),
        ('密钥', {
            'fields': ('api_key_masked',)
        }),
        ('时间', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['activate', 'deactivate']

    @admin.display(description='API Key')
    def api_key_masked(self, obj):
        if obj.api_key_encrypted:
            return f'****{obj.api_key_encrypted[-6:]}'
        return '未设置'

    @admin.action(description='启用配置')
    def activate(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description='禁用配置')
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
