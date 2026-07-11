from django.contrib import admin
from unfold.admin import ModelAdmin
from apps.bids.models import Bid, BidChapter, BidStep


class BidChapterInline(admin.TabularInline):
    model = BidChapter
    extra = 0
    fields = ['order', 'title', 'parent', 'content']
    ordering = ['order']


class BidStepInline(admin.TabularInline):
    model = BidStep
    extra = 0
    fields = ['order', 'label', 'status']
    ordering = ['order']


@admin.register(Bid)
class BidAdmin(ModelAdmin):
    list_display = ['id', 'title', 'status', 'user', 'total_chapters', 'completed_chapters', 'created_at', 'updated_at']
    list_display_links = ['id', 'title']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'user__username']
    list_per_page = 20
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at']
    inlines = [BidChapterInline, BidStepInline]
    fieldsets = (
        ('标书信息', {
            'fields': ('title', 'status', 'user')
        }),
        ('统计', {
            'fields': ('total_chapters', 'completed_chapters')
        }),
        ('时间', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_completed', 'mark_draft', 'delete_with_chapters']

    @admin.action(description='标记为已完成')
    def mark_completed(self, request, queryset):
        queryset.update(status='completed')

    @admin.action(description='标记为草稿')
    def mark_draft(self, request, queryset):
        queryset.update(status='draft')

    @admin.action(description='删除标书及所有章节和步骤')
    def delete_with_chapters(self, request, queryset):
        for bid in queryset:
            BidChapter.objects.filter(bid=bid).delete()
            BidStep.objects.filter(bid=bid).delete()
            bid.delete()
        self.message_user(request, f'已删除 {queryset.count()} 个标书')


@admin.register(BidChapter)
class BidChapterAdmin(ModelAdmin):
    list_display = ['id', 'title', 'bid', 'parent', 'order', 'has_content', 'created_at']
    list_display_links = ['id', 'title']
    list_filter = ['bid']
    search_fields = ['title', 'bid__title']
    list_per_page = 30
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['bid', 'order']

    @admin.display(description='有内容', boolean=True)
    def has_content(self, obj):
        return obj.content is not None and obj.content != {}


@admin.register(BidStep)
class BidStepAdmin(ModelAdmin):
    list_display = ['id', 'label', 'bid', 'order', 'status', 'created_at']
    list_display_links = ['id', 'label']
    list_filter = ['status', 'bid']
    search_fields = ['label', 'bid__title']
    list_per_page = 30
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['bid', 'order']

    actions = ['mark_completed', 'mark_active', 'mark_pending']

    @admin.action(description='标记为已完成')
    def mark_completed(self, request, queryset):
        queryset.update(status='completed')

    @admin.action(description='标记为进行中')
    def mark_active(self, request, queryset):
        queryset.update(status='active')

    @admin.action(description='标记为待处理')
    def mark_pending(self, request, queryset):
        queryset.update(status='pending')
