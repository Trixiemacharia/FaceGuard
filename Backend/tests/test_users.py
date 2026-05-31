"""
Tests: users app — registration, login, JWT, roles, logout.
"""

import pytest
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, admin_user):
        r = api_client.post('/api/auth/login/', {
            'email': 'admin@test.com', 'password': 'adminpass123'
        }, format='json')
        assert r.status_code == 200
        assert 'access' in r.data
        assert 'refresh' in r.data
        assert r.data['user']['role'] == 'admin'

    def test_login_wrong_password(self, api_client, admin_user):
        r = api_client.post('/api/auth/login/', {
            'email': 'admin@test.com', 'password': 'wrongpassword'
        }, format='json')
        assert r.status_code == 401

    def test_login_unknown_email(self, api_client):
        r = api_client.post('/api/auth/login/', {
            'email': 'nobody@test.com', 'password': 'pass'
        }, format='json')
        assert r.status_code == 401

    def test_login_missing_fields(self, api_client):
        r = api_client.post('/api/auth/login/', {}, format='json')
        assert r.status_code == 400

    def test_jwt_payload_contains_role(self, api_client, guard_user):
        r = api_client.post('/api/auth/login/', {
            'email': 'guard@test.com', 'password': 'guardpass123'
        }, format='json')
        assert r.status_code == 200
        assert r.data['user']['role'] == 'guard'


@pytest.mark.django_db
class TestTokenRefresh:
    def test_refresh_success(self, api_client, admin_user):
        refresh = str(RefreshToken.for_user(admin_user))
        r = api_client.post('/api/auth/refresh/', {'refresh': refresh}, format='json')
        assert r.status_code == 200
        assert 'access' in r.data

    def test_refresh_invalid_token(self, api_client):
        r = api_client.post('/api/auth/refresh/', {'refresh': 'bad.token.here'}, format='json')
        assert r.status_code == 401


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_token(self, admin_client, admin_user):
        refresh = str(RefreshToken.for_user(admin_user))
        r = admin_client.post('/api/auth/logout/', {'refresh': refresh}, format='json')
        assert r.status_code == 205

    def test_logout_requires_auth(self, api_client, admin_user):
        refresh = str(RefreshToken.for_user(admin_user))
        r = api_client.post('/api/auth/logout/', {'refresh': refresh}, format='json')
        assert r.status_code == 401

    def test_logout_missing_refresh_token(self, admin_client):
        r = admin_client.post('/api/auth/logout/', {}, format='json')
        assert r.status_code == 400


@pytest.mark.django_db
class TestRegister:
    def test_admin_can_register_user(self, admin_client):
        r = admin_client.post('/api/auth/register/', {
            'email': 'newguard@test.com',
            'first_name': 'New', 'last_name': 'Guard',
            'role': 'guard',
            'password': 'newpass123', 'password2': 'newpass123',
        }, format='json')
        assert r.status_code == 201
        assert r.data['role'] == 'guard'

    def test_non_admin_cannot_register(self, guard_client):
        r = guard_client.post('/api/auth/register/', {
            'email': 'x@test.com', 'first_name': 'X', 'last_name': 'Y',
            'role': 'viewer', 'password': 'pass1234', 'password2': 'pass1234',
        }, format='json')
        assert r.status_code == 403

    def test_register_password_mismatch(self, admin_client):
        r = admin_client.post('/api/auth/register/', {
            'email': 'z@test.com', 'first_name': 'Z', 'last_name': 'Z',
            'role': 'viewer', 'password': 'pass1234', 'password2': 'different',
        }, format='json')
        assert r.status_code == 400

    def test_register_duplicate_email(self, admin_client, admin_user):
        r = admin_client.post('/api/auth/register/', {
            'email': 'admin@test.com', 'first_name': 'Dup', 'last_name': 'User',
            'role': 'viewer', 'password': 'pass1234', 'password2': 'pass1234',
        }, format='json')
        assert r.status_code == 400


@pytest.mark.django_db
class TestProfile:
    def test_get_own_profile(self, admin_client, admin_user):
        r = admin_client.get('/api/auth/profile/')
        assert r.status_code == 200
        assert r.data['email'] == 'admin@test.com'

    def test_unauthenticated_cannot_get_profile(self, api_client):
        r = api_client.get('/api/auth/profile/')
        assert r.status_code == 401

    def test_patch_own_profile(self, admin_client):
        r = admin_client.patch('/api/auth/profile/', {'first_name': 'Updated'}, format='json')
        assert r.status_code == 200
        assert r.data['first_name'] == 'Updated'


@pytest.mark.django_db
class TestUserModel:
    def test_role_properties(self, admin_user, guard_user, viewer_user):
        assert admin_user.is_admin is True
        assert admin_user.is_guard is False
        assert guard_user.is_guard is True
        assert viewer_user.is_viewer is True

    def test_get_full_name(self, admin_user):
        assert admin_user.get_full_name() == 'Admin User'

    def test_str_representation(self, admin_user):
        assert 'admin@test.com' in str(admin_user)
        assert 'admin' in str(admin_user)