from django.contrib import admin
from unfold.admin import ModelAdmin
from apps.users.models import User


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ['id', 'username', 'display_name', 'avatar_letter', 'points', 'vip_level', 'is_active', 'created_at']
    list_display_links = ['id', 'username']
    search_fields = ['username', 'display_name']
    list_filter = ['vip_level', 'is_active']
    list_per_page = 20
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at', 'last_login']
    fieldsets = (
        ('基本信息', {
            'fields': ('username', 'display_name', 'avatar_letter')
        }),
        ('会员信息', {
            'fields': ('points', 'vip_level')
        }),
        ('状态', {
            'fields': ('is_active', 'is_staff', 'is_superuser')
        }),
        ('时间', {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['reset_points', 'set_vip']

    @admin.action(description='重置积分为 0')
    def reset_points(self, request, queryset):
        queryset.update(points=0)

    @admin.action(description='设为普通会员')
    def set_vip(self, request, queryset):
        queryset.update(vip_level='普通会员')
