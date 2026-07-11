from django.contrib import admin
from unfold.admin import ModelAdmin
from apps.logs.models import RequestLog


@admin.register(RequestLog)
class RequestLogAdmin(ModelAdmin):
    list_display = ['created_at', 'method', 'path', 'status_code', 'duration_ms', 'user', 'ip']
    list_display_links = ['created_at', 'path']
    list_filter = ['method', 'status_code', 'user']
    search_fields = ['path', 'user', 'ip']
    list_per_page = 50
    date_hierarchy = 'created_at'
    readonly_fields = [
        'method', 'path', 'query_string', 'status_code', 'duration_ms',
        'user', 'ip', 'request_body', 'response_body', 'created_at',
    ]
    fieldsets = (
        ('请求信息', {
            'fields': ('method', 'path', 'query_string', 'ip', 'user')
        }),
        ('响应信息', {
            'fields': ('status_code', 'duration_ms')
        }),
        ('内容详情', {
            'fields': ('request_body', 'response_body'),
            'classes': ('collapse',)
        }),
        ('时间', {
            'fields': ('created_at',)
        }),
    )

    actions = ['delete_selected_logs']

    @admin.action(description='删除选中日志')
    def delete_selected_logs(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'已删除 {count} 条日志')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
