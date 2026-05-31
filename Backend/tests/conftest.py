# tests/conftest.py
import pytest
from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from zones.models import AccessEvent, Zone
from recognition.models import EnrolledPerson, FaceEmbedding


def _get_client_for_user(user):
    """Helper: returns a Django test Client with JWT auth header set."""
    token = RefreshToken.for_user(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token.access_token)}')
    return c


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email='admin@test.com',
        password='adminpass123',
        first_name='Admin',
        last_name='User',
        role='admin',
        is_staff=True,
    )

@pytest.fixture
def guard_user(db):
    return User.objects.create_user(
        email='guard@test.com',
        password='guardpass123',
        first_name='Guard',
        last_name='User',
        role='guard',
    )

@pytest.fixture
def viewer_user(db):
    return User.objects.create_user(
        email='viewer@test.com',
        password='viewerpass123',
        first_name='Viewer',
        last_name='User',
        role='viewer',
    )

@pytest.fixture
def admin_client(admin_user):
    return _get_client_for_user(admin_user)

@pytest.fixture
def guard_client(guard_user):
    return _get_client_for_user(guard_user)

@pytest.fixture
def viewer_client(viewer_user):
    return _get_client_for_user(viewer_user)

@pytest.fixture
def api_client(db):
    """Unauthenticated client."""
    return APIClient()

@pytest.fixture
def access_zone(db):
    return Zone.objects.create(
        name='Test Zone',
        description='A test zone',
        camera_ids=['cam-01'],
        is_active=True,
    )

@pytest.fixture
def enrolled_person(db):
    return EnrolledPerson.objects.create(
        name='Test Person',
        employee_id='EMP-001',
    )


@pytest.fixture
def face_embedding(db, enrolled_person):
    embedding = FaceEmbedding(person=enrolled_person)
    embedding.set_vector(__import__('numpy').array([0.0, 1.0, 0.0]))
    embedding.save()
    return embedding


@pytest.fixture
def access_event(db, access_zone, enrolled_person):
    return AccessEvent.objects.create(
        zone=access_zone,
        person=enrolled_person,
        outcome='granted',
        confidence=0.9,
        camera_id='cam-01',
    )
