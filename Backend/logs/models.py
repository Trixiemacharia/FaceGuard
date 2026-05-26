from django.db import models
from django.conf import settings

class SystemLog(models.Model):
    class Level(models.TextChoices):
        INFO    = 'info',    'Info'
        WARNING = 'warning', 'Warning'
        ERROR   = 'error',   'Error'

    level      = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    message    = models.TextField()
    source     = models.CharField(max_length=100, blank=True)
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fg_system_logs'
        ordering = ['-created_at']