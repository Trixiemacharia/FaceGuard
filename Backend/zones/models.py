from django.conf import settings
from django.db import models

class Zone(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    camera_ids = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'fg_zones'
    
    def __str__(self):
        return self.name


class ZoneRule(models.Model):
    class Permission(models.TextChoices):
        ALLOW = 'allow', 'Allow'
        DENY = 'deny', 'Deny'

    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='rules')
    person = models.ForeignKey('recognition.EnrolledPerson', on_delete=models.CASCADE, related_name='zone_rules')
    permission = models.CharField(max_length=10, choices=Permission.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fg_zone_rules'
        unique_together = ('zone', 'person')

    def __str__(self):
        return f'{self.person} {self.permission} in {self.zone}'


class AccessEvent(models.Model):
    class Outcome(models.TextChoices):
        GRANTED = 'granted', 'Granted'
        DENIED = 'denied', 'Denied'
        ERROR = 'error', 'Error'

    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_events')
    person = models.ForeignKey(
        'recognition.EnrolledPerson',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='access_events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='zone_access_events',
    )
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    confidence = models.FloatField(null=True, blank=True)
    camera_id = models.CharField(max_length=100, blank=True)
    liveness_pass = models.BooleanField(default=False)
    denial_reason = models.CharField(max_length=255, blank=True)
    processing_ms = models.PositiveIntegerField(null=True, blank=True)
    frame_path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fg_zone_access_events'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['zone', 'created_at'])]

    def __str__(self):
        return f'{self.outcome} at {self.zone or "unknown zone"}'
