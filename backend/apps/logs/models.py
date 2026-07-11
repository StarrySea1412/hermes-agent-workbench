from django.db import models


class RequestLog(models.Model):
    method = models.CharField('请求方法', max_length=10)
    path = models.CharField('请求路径', max_length=500, db_index=True)
    query_string = models.CharField('查询参数', max_length=500, blank=True, default='')
    status_code = models.IntegerField('状态码', db_index=True)
    duration_ms = models.FloatField('耗时(ms)')
    user = models.CharField('用户', max_length=150, blank=True, default='anonymous')
    ip = models.CharField('IP地址', max_length=50, blank=True, default='')
    request_body = models.JSONField('请求体', null=True, blank=True)
    response_body = models.JSONField('响应体', null=True, blank=True)
    created_at = models.DateTimeField('请求时间', auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'request_logs'
        ordering = ['-created_at']
        verbose_name = '请求日志'
        verbose_name_plural = '请求日志'

    def __str__(self):
        return f'{self.method} {self.path} [{self.status_code}] {self.duration_ms}ms'
