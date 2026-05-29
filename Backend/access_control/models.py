from django.db import models
from django.conf import settings

class AccessPoint(models.Model):
    name       = models.CharField(max_length=100)
    camera_id  = models.CharField(max_length=100, unique=True)
    location   = models.CharField(max_length=255, blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fg_access_points'

    def __str__(self):
        return f'{self.name} ({self.camera_id})'

class AccessEvent(models.Model):
    RESULT_CHOICES = [
        ('granted', 'Granted'),
        ('denied', 'Denied'),
        ('unknown', 'Unknown face'),
        ('liveness_fail', 'Liveness check failed'),
    ]
    zone        = models.ForeignKey(AccessPoint, on_delete=models.SET_NULL, null=True)
    user        = models.ForeignKey(
                    settings.AUTH_USER_MODEL, 
                    on_delete=models.SET_NULL,
                    null=True, 
                    blank=True
                )
    result      = models.CharField(max_length=20, choices=RESULT_CHOICES)
    confidence  = models.FloatField(null=True, blank=True)
    frame_path  = models.CharField(max_length=255, blank=True)
    timestamp   = models.DateTimeField(auto_now_add=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'fg_access_events'  # Keep this unique
        ordering = ['-timestamp']
        indexes  = [models.Index(fields=['zone', 'timestamp'])]

    def __str__(self):
        user_name = self.user.get_full_name() if self.user else 'Unknown'
        return f"{user_name} - {self.result} at {self.zone}"
