"""
FaceGuard Celery Tasks
──────────────────────
- log_access_event   : async write to AccessEvent table
- send_deny_alert    : email + optional SMS on denial/liveness failure
- check_repeat_fails : fire alert if same camera gets N denials in M minutes
"""

import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('recognition')


# ── Event logging ─────────────────────────────────────────────────────── #

@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def log_access_event(self, event_data: dict):
    """
    Persist an access event asynchronously.

    event_data keys:
        zone_id, person_id, outcome, confidence, liveness_pass,
        camera_id, denial_reason, processing_ms
    """
    try:
        from zones.models import AccessEvent
        AccessEvent.objects.create(**{k: v for k, v in event_data.items() if v is not None})
        logger.info('AccessEvent logged: %s', event_data.get('outcome'))
    except Exception as exc:
        logger.error('log_access_event failed: %s', exc)
        raise self.retry(exc=exc)


# ── Denial alert ──────────────────────────────────────────────────────── #

@shared_task(bind=True, max_retries=2)
def send_deny_alert(self, camera_id: str, reason: str, confidence: float, person_name: str = 'Unknown'):
    """Send email (and optional SMS) when access is denied."""
    try:
        _send_email_alert(camera_id, reason, confidence, person_name)
        _send_sms_alert(camera_id, reason, person_name)
    except Exception as exc:
        logger.error('send_deny_alert failed: %s', exc)
        raise self.retry(exc=exc)


def _send_email_alert(camera_id, reason, confidence, person_name):
    from django.core.mail import send_mail
    cfg = getattr(settings, 'ALERT_EMAIL', {})
    recipients = cfg.get('RECIPIENTS', [])
    if not recipients:
        logger.debug('No ALERT_EMAIL.RECIPIENTS configured — skipping email.')
        return

    subject = f'[FaceGuard] Access Denied — {camera_id}'
    body    = (
        f'Access Denied Event\n'
        f'───────────────────\n'
        f'Camera   : {camera_id}\n'
        f'Person   : {person_name}\n'
        f'Reason   : {reason}\n'
        f'Confidence: {confidence:.1%}\n'
        f'Time     : {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    logger.info('Denial email sent to %s', recipients)


def _send_sms_alert(camera_id, reason, person_name):
    cfg = getattr(settings, 'TWILIO', {})
    if not cfg.get('ACCOUNT_SID') or not cfg.get('AUTH_TOKEN'):
        logger.debug('Twilio not configured — skipping SMS.')
        return

    try:
        from twilio.rest import Client
        client = Client(cfg['ACCOUNT_SID'], cfg['AUTH_TOKEN'])
        body   = f'[FaceGuard] DENIED at {camera_id} — {person_name} — {reason}'
        for number in cfg.get('TO_NUMBERS', []):
            client.messages.create(body=body, from_=cfg['FROM_NUMBER'], to=number)
        logger.info('SMS alert sent.')
    except ImportError:
        logger.warning('twilio package not installed — SMS skipped.')
    except Exception as e:
        logger.error('SMS send failed: %s', e)


# ── Repeat-failure check ───────────────────────────────────────────────── #

@shared_task
def check_repeat_failures(camera_id: str, window_minutes: int = 5, threshold: int = 3):
    """
    If a camera has >= `threshold` denials in the last `window_minutes`,
    create an Alert and fire a notification.
    """
    from zones.models import AccessEvent
    from alerts.models import Alert

    since  = timezone.now() - timedelta(minutes=window_minutes)
    count  = AccessEvent.objects.filter(
        camera_id=camera_id,
        outcome='denied',
        created_at__gte=since
    ).count()

    if count >= threshold:
        msg = f'{count} denied attempts at camera {camera_id} in the last {window_minutes} min.'
        logger.warning(msg)

        # Avoid duplicate alerts within the same window
        recent_alert = Alert.objects.filter(
            alert_type=Alert.AlertType.MULTIPLE_FAIL,
            camera_id=camera_id,
            created_at__gte=since,
        ).exists()

        if not recent_alert:
            Alert.objects.create(
                alert_type=Alert.AlertType.MULTIPLE_FAIL,
                message=msg,
                camera_id=camera_id,
            )
            send_deny_alert.delay(camera_id, 'repeated_failures', 0.0, 'Multiple unknown persons')
