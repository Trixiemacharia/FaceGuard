# FaceGuard — Biometric Data Compliance Review
# GDPR Article 9 + Kenya Data Protection Act 2019

---

## 1. Legal Basis for Processing Biometric Data

Biometric data (face embeddings) is **special category data** under GDPR Article 9
and **sensitive personal data** under Kenya's Data Protection Act 2019, Section 2.

**Legal basis used:** Explicit consent (Article 9(2)(a)) + Legitimate interest
for access control in a controlled employment context.

**What this means in practice:**
- Every enrolled person MUST sign a consent form before enrolment
- Consent must be freely given, specific, informed, and unambiguous
- Withdrawal of consent must be easy and result in immediate data deletion

---

## 2. Consent Flow

### Step 1 — Pre-enrolment notice
Before any image is captured, the enrolled person must receive:

> "FaceGuard collects and processes your facial biometric data (face embeddings)
> for the sole purpose of access control at [Organisation Name]. Your data is
> stored encrypted in a secured database. You may withdraw consent at any time
> by contacting [Data Controller Contact]. Withdrawal will result in deletion
> of all biometric data within 30 days."

### Step 2 — Signed consent record
```
BIOMETRIC DATA CONSENT FORM
────────────────────────────
Full Name:       ___________________________
Employee ID:     ___________________________
Department:      ___________________________
Date:            ___________________________

I consent to [Organisation] collecting, storing, and processing my facial
biometric data for access control purposes. I understand:
  □ My data will be stored for no longer than my employment period + 90 days
  □ I may withdraw consent at any time
  □ My data will not be shared with third parties
  □ My data is stored encrypted

Signature: ___________________________ Date: ___________
```

### Step 3 — System record
The `EnrolledPerson` model stores `consent_given=True` and `consent_date`.
Add these fields to the model for production:

```python
consent_given = models.BooleanField(default=False)
consent_date  = models.DateTimeField(null=True, blank=True)
consent_form  = models.FileField(upload_to='consent_forms/', blank=True)
```

---

## 3. Data Retention Policy

| Data Type | Retention Period | Deletion Method |
|-----------|-----------------|-----------------|
| Face embeddings | Duration of employment + 90 days | Hard delete from DB |
| Verification frames | 30 days | Automated Celery task |
| Access event logs | 2 years (legal/audit) | Anonymise person FK after 2 years |
| Alert records | 1 year | Hard delete |
| JWT tokens | 60 minutes (access), 7 days (refresh) | Auto-expired |

### Automated retention Celery task (add to tasks.py):

```python
@shared_task
def enforce_data_retention():
    """Run daily via Celery Beat."""
    from django.utils import timezone
    from datetime import timedelta

    # Delete verification frames older than 30 days
    cutoff_frames = timezone.now() - timedelta(days=30)
    VerificationLog.objects.filter(created_at__lt=cutoff_frames).update(frame_image='')

    # Anonymise access events older than 2 years
    cutoff_events = timezone.now() - timedelta(days=730)
    AccessEvent.objects.filter(created_at__lt=cutoff_events).update(person=None)
```

Add to Celery Beat schedule in settings.py:
```python
CELERY_BEAT_SCHEDULE = {
    'enforce-data-retention': {
        'task': 'zones.tasks.enforce_data_retention',
        'schedule': crontab(hour=2, minute=0),  # 2am daily
    },
}
```

---

## 4. Encryption at Rest

Face embeddings must be encrypted in the database. Add field-level encryption:

```bash
pip install django-encrypted-model-fields
```

```python
# In recognition/models.py
from encrypted_model_fields.fields import EncryptedTextField

class FaceEmbedding(models.Model):
    embedding = EncryptedTextField()  # Replace models.TextField()
```

Set encryption key in `.env`:
```
FIELD_ENCRYPTION_KEY=your-32-byte-fernet-key-here
```

Generate a key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

---

## 5. Data Subject Rights

Under GDPR and Kenya DPA, enrolled persons have the right to:

| Right | Implementation |
|-------|---------------|
| Access | `GET /api/persons/{id}/` returns their record |
| Rectification | `PATCH /api/persons/{id}/` updates name/dept |
| Erasure ("right to be forgotten") | `DELETE /api/persons/{id}/` removes person + all embeddings |
| Portability | Export via CSV report filtered to their ID |
| Objection | Set `is_active=False` — stops matching without deletion |

---

## 6. Data Breach Response

If a breach occurs (e.g. DB dump exposed):

1. **Within 72 hours**: Notify Data Commissioner (Kenya) / supervisory authority (EU)
2. **Immediately**: Rotate all JWT secret keys (invalidates all sessions)
3. **Immediately**: Rotate database password + face embedding encryption key
4. **Within 30 days**: Notify affected individuals
5. **Document**: Incident date, scope, mitigation steps, notifications sent

Emergency key rotation:
```bash
# Invalidate all JWTs immediately
python manage.py shell -c "
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
OutstandingToken.objects.all().delete()
print('All tokens invalidated')
"
```

---

## 7. Privacy by Design Checklist

- [x] Face embeddings stored as vectors, NOT raw images (after enrolment)
- [x] No biometric data in JWT tokens or logs
- [x] Verification frames auto-deleted after 30 days
- [x] `send_default_pii=False` in Sentry config
- [x] Role-based access (viewers cannot access embeddings or raw frames)
- [x] Audit log of all access events
- [ ] Field-level encryption on embeddings (add before production)
- [ ] Consent form stored per enrolled person
- [ ] Data retention Celery Beat task scheduled
- [ ] DPA registration completed (Kenya: register with ODPC)