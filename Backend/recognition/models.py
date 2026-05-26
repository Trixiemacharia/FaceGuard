import numpy as np
from django.db import models
from django.conf import settings


class EnrolledPerson(models.Model):
    name        = models.CharField(max_length=255)
    employee_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    department  = models.CharField(max_length=100, blank=True)
    is_active   = models.BooleanField(default=True)
    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='enrollments',
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    notes       = models.TextField(blank=True)

    class Meta:
        db_table = 'fg_enrolled_persons'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.employee_id or "no-id"})'

    @property
    def embedding_count(self):
        return self.embeddings.count()


class FaceEmbedding(models.Model):
    person     = models.ForeignKey(EnrolledPerson, on_delete=models.CASCADE, related_name='embeddings')
    embedding  = models.TextField()
    image      = models.ImageField(upload_to='enrolment/', blank=True)
    model_name = models.CharField(max_length=50, default='VGG-Face')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fg_face_embeddings'

    def __str__(self):
        return f'Embedding({self.person.name}, #{self.id})'

    def get_vector(self):
        return np.fromstring(self.embedding, sep=',')

    def set_vector(self, vector):
        self.embedding = ','.join(map(str, vector.tolist()))


class VerificationLog(models.Model):
    class Outcome(models.TextChoices):
        GRANTED = 'granted', 'Access Granted'
        DENIED  = 'denied',  'Access Denied'
        ERROR   = 'error',   'Error'

    matched_person = models.ForeignKey(
        EnrolledPerson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verifications',
    )
    outcome       = models.CharField(max_length=10, choices=Outcome.choices)
    confidence    = models.FloatField(default=0.0)
    distance      = models.FloatField(default=1.0)
    liveness_pass = models.BooleanField(default=False)
    frame_image   = models.ImageField(upload_to='verify_frames/', blank=True)
    camera_id     = models.CharField(max_length=100, blank=True)
    requested_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    error_detail = models.TextField(blank=True)

    class Meta:
        db_table = 'fg_verification_logs'
        ordering = ['-created_at']
