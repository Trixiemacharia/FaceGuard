"""
FaceGuard Load Test — Locust
─────────────────────────────
Tests the /verify-face endpoint under concurrent load.

Usage:
    pip install locust
    locust -f locustfile.py --host=http://127.0.0.1:8000

Then open http://localhost:8089, set:
    Users:       50
    Spawn rate:  5
    Run for:     60s

Target: p95 < 2000ms, error rate < 1% at 50 concurrent users.
"""

import base64
import json
import os
import cv2
import numpy as np
from locust import HttpUser, task, between, events


# ── Generate a small valid JPEG frame once ────────────────────────────── #

def _make_b64_frame():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    # Draw a simple face-like circle so DeepFace has something to try
    cv2.circle(frame, (160, 120), 60, (200, 180, 160), -1)
    cv2.circle(frame, (140, 105), 10, (50, 50, 50), -1)
    cv2.circle(frame, (180, 105), 10, (50, 50, 50), -1)
    cv2.ellipse(frame, (160, 140), (30, 15), 0, 0, 180, (50, 50, 50), 2)
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(buf).decode()


FRAME = _make_b64_frame()
FRAMES_PAYLOAD = [FRAME] * 5  # 5 frames per request


# ── Auth helper ───────────────────────────────────────────────────────── #

class FaceGuardUser(HttpUser):
    """
    Simulates a guard terminal making verify-face requests.
    Think rate: 1–3 seconds between attempts (realistic door-opening pace).
    """
    wait_time = between(1, 3)
    access_token: str = ''

    def on_start(self):
        """Authenticate once per simulated user."""
        creds = {
            'email':    os.getenv('FG_ADMIN_EMAIL',    'admin@faceguard.local'),
            'password': os.getenv('FG_ADMIN_PASSWORD', 'adminpassword'),
        }
        r = self.client.post(
            '/api/auth/login/',
            json=creds,
            name='[AUTH] login',
        )
        if r.status_code == 200:
            self.access_token = r.json().get('access', '')
        else:
            self.access_token = ''

    def _auth_headers(self):
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type':  'application/json',
        }

    # ── Tasks (weighted) ───────────────────────────────────────────── #

    @task(10)
    def verify_face(self):
        """Main load: verify-face endpoint (90% of traffic)."""
        self.client.post(
            '/api/verify-face/',
            data=json.dumps({'frames': FRAMES_PAYLOAD, 'camera_id': 'load-test-cam'}),
            headers=self._auth_headers(),
            name='/api/verify-face/',
        )

    @task(2)
    def list_persons(self):
        self.client.get(
            '/api/persons/',
            headers=self._auth_headers(),
            name='/api/persons/',
        )

    @task(2)
    def access_stats(self):
        self.client.get(
            '/api/zones/stats/?hours=1',
            headers=self._auth_headers(),
            name='/api/zones/stats/',
        )

    @task(1)
    def list_events(self):
        self.client.get(
            '/api/zones/events/?hours=1',
            headers=self._auth_headers(),
            name='/api/zones/events/',
        )

    @task(1)
    def refresh_token(self):
        """Simulate token refresh (every ~10 requests on average)."""
        pass  # Covered by on_start for now; add refresh logic in Phase 4


# ── Custom stats summary on test end ─────────────────────────────────── #

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    stats = environment.stats
    verify = stats.get('/api/verify-face/', 'POST')
    if verify:
        print('\n' + '─' * 60)
        print('FACEGUARD LOAD TEST SUMMARY')
        print('─' * 60)
        print(f'  Endpoint : POST /api/verify-face/')
        print(f'  Requests : {verify.num_requests}')
        print(f'  Failures : {verify.num_failures}  ({100*verify.fail_ratio:.1f}%)')
        print(f'  Avg (ms) : {verify.avg_response_time:.0f}')
        print(f'  p50 (ms) : {verify.get_response_time_percentile(0.5):.0f}')
        print(f'  p95 (ms) : {verify.get_response_time_percentile(0.95):.0f}')
        print(f'  p99 (ms) : {verify.get_response_time_percentile(0.99):.0f}')
        print(f'  RPS      : {verify.current_rps:.1f}')
        passed = verify.fail_ratio < 0.01 and verify.get_response_time_percentile(0.95) < 2000
        print(f'  RESULT   : {"✓ PASS" if passed else "✗ FAIL"} (target: p95 < 2000ms, error < 1%)')
        print('─' * 60)