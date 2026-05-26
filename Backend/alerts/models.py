from django.db import models
from django.conf import settings

class Alert(models.Model):
    class AlertType(models.TextChoices):
        UNKNOWN_FACE  = 'unknown_face',  'Unknown Face Detected'
        LIVENESS_FAIL = 'liveness_fail', 'Liveness Check Failed'
        MULTIPLE_FAIL = 'multiple_fail', 'Multiple Failed Attempts'
        SYSTEM_ERROR  = 'system_error',  'System Error'

    alert_type  = models.CharField(max_length=30, choices=AlertType.choices)
    message     = models.TextField()
    camera_id   = models.CharField(max_length=100, blank=True)
    resolved    = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'fg_alerts'
        ordering = ['-created_at']
