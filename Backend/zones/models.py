from django.db import models

# Keep only Zone-related models here
# Remove AccessEvent since it belongs to access_control app

class Zone(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'fg_zones'
    
    def __str__(self):
        return self.name

# If you had any other Zone-related models, keep them here
# But AccessEvent should be removed
