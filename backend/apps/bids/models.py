from django.conf import settings
from django.db import models


class Bid(models.Model):
    title = models.CharField(max_length=256, db_index=True)
    status = models.CharField(max_length=32, default='draft')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bids')
    completed_chapters = models.IntegerField(default=0)
    total_chapters = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bids'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class BidChapter(models.Model):
    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='chapters')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    title = models.CharField(max_length=256)
    order = models.IntegerField(default=0)
    content = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bid_chapters'
        ordering = ['order']

    def __str__(self):
        return self.title


class BidStep(models.Model):
    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='steps')
    order = models.IntegerField(default=0)
    label = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bid_steps'
        ordering = ['order']

    def __str__(self):
        return self.label
