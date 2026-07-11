from django.contrib import admin
from unfold.admin import ModelAdmin
from apps.files.models import UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(ModelAdmin):
    list_display = ['id', 'original_name', 'file_type', 'file_size_display', 'user', 'created_at']
    list_display_links = ['id', 'original_name']
    list_filter = ['file_type', 'created_at']
    search_fields = ['original_name', 'user__username']
    list_per_page = 30
    date_hierarchy = 'created_at'
    readonly_fields = ['file_size_display', 'created_at']

    actions = ['delete_selected_files']

    @admin.action(description='删除选中文件')
    def delete_selected_files(self, request, queryset):
        count = queryset.count()
        for f in queryset:
            f.delete()
        self.message_user(request, f'已删除 {count} 个文件')
