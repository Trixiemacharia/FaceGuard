"""
Tests: security — JWT tampering, IDOR, auth bypass, input validation.
These mirror what Burp Suite would test manually.
"""

import pytest
import base64
import json


@pytest.mark.django_db
class TestJWTSecurity:
    """Tests that mirror Burp Suite JWT tampering checks."""

    def test_no_token_returns_401(self, api_client):
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401

    def test_malformed_token_returns_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION='Bearer not.a.jwt')
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401

    def test_empty_bearer_returns_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION='Bearer ')
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401

    def test_none_algorithm_attack(self, api_client, admin_user):
        """Forge a token with alg=none — must be rejected."""
        header  = base64.urlsafe_b64encode(json.dumps({'alg': 'none', 'typ': 'JWT'}).encode()).decode().rstrip('=')
        payload = base64.urlsafe_b64encode(json.dumps({'user_id': admin_user.id, 'role': 'admin'}).encode()).decode().rstrip('=')
        forged  = f'{header}.{payload}.'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {forged}')
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401

    def test_wrong_signature_rejected(self, api_client, admin_user):
        """Modify the payload and keep original signature — must fail."""
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(admin_user).access_token)
        parts = token.split('.')
        # Tamper with payload
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps({'user_id': 9999, 'role': 'admin'}).encode()
        ).decode().rstrip('=')
        tampered = f'{parts[0]}.{tampered_payload}.{parts[2]}'
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {tampered}')
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401

    def test_basic_auth_not_accepted(self, api_client, admin_user):
        creds = base64.b64encode(b'admin@test.com:adminpass123').decode()
        api_client.credentials(HTTP_AUTHORIZATION=f'Basic {creds}')
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401


@pytest.mark.django_db
class TestIDOR:
    """Insecure Direct Object Reference tests."""

    def test_guard_cannot_list_all_users(self, guard_client):
        r = guard_client.get('/api/auth/users/')
        assert r.status_code == 403

    def test_viewer_cannot_list_all_users(self, viewer_client):
        r = viewer_client.get('/api/auth/users/')
        assert r.status_code == 403

    def test_viewer_cannot_delete_zone(self, viewer_client, access_zone):
        r = viewer_client.delete(f'/api/zones/{access_zone.id}/')
        assert r.status_code == 403

    def test_viewer_cannot_enrol_person(self, viewer_client):
        r = viewer_client.post('/api/enrol/', {'name': 'Hack'}, format='multipart')
        assert r.status_code == 403

    def test_guard_cannot_delete_person(self, guard_client, enrolled_person):
        r = guard_client.delete(f'/api/persons/{enrolled_person.id}/')
        assert r.status_code == 403

    def test_guard_cannot_access_admin_panel(self, guard_client):
        # Django admin should redirect non-staff
        r = guard_client.get('/admin/', follow=False)
        assert r.status_code in (302, 403)


@pytest.mark.django_db
class TestInputValidation:
    """Input validation and injection-resistance tests."""

    def test_sql_injection_in_login(self, api_client):
        r = api_client.post('/api/auth/login/', {
            'email': "admin@test.com' OR '1'='1",
            'password': "' OR '1'='1",
        }, format='json')
        assert r.status_code in (400, 401)

    def test_xss_payload_in_zone_name(self, admin_client):
        r = admin_client.post('/api/zones/', {
            'name': '<script>alert(1)</script>',
            'camera_ids': [],
        }, format='json')
        # Should either reject or store safely — must not return 500
        assert r.status_code in (201, 400)
        if r.status_code == 201:
            # Value is stored but JSON-encoded, not executed
            assert '<script>' in r.data['name']  # stored as-is (safe — JSON encoded)

    def test_oversized_frames_list_rejected(self, admin_client):
        r = admin_client.post('/api/verify-face/', {
            'frames': ['dGVzdA=='] * 31  # 31 > max of 30
        }, format='json')
        assert r.status_code == 400

    def test_empty_json_body_returns_400(self, admin_client):
        r = admin_client.post('/api/verify-face/', {}, format='json')
        assert r.status_code == 400

    def test_login_with_very_long_password(self, api_client):
        r = api_client.post('/api/auth/login/', {
            'email': 'admin@test.com',
            'password': 'A' * 10000,
        }, format='json')
        assert r.status_code in (400, 401)  # Must not 500


@pytest.mark.django_db
class TestRateAndHeaders:
    def test_verify_requires_json_content_type(self, admin_client):
        """Sending form data to a JSON-only endpoint should return 400/415."""
        r = admin_client.post('/api/verify-face/', 'frames=test', content_type='application/x-www-form-urlencoded')
        assert r.status_code in (400, 415)