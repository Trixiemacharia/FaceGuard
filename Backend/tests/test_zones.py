"""
Tests: zones app — zones CRUD, access events, stats endpoint.
"""

import pytest
from django.utils import timezone


@pytest.mark.django_db
class TestZoneAPI:
    def test_admin_can_create_zone(self, admin_client):
        r = admin_client.post('/api/zones/', {
            'name': 'Server Room',
            'description': 'Restricted area',
            'camera_ids': ['cam-sr-01'],
            'is_active': True,
        }, format='json')
        assert r.status_code == 201
        assert r.data['name'] == 'Server Room'

    def test_guard_cannot_create_zone(self, guard_client):
        r = guard_client.post('/api/zones/', {'name': 'X'}, format='json')
        assert r.status_code == 403

    def test_viewer_cannot_create_zone(self, viewer_client):
        r = viewer_client.post('/api/zones/', {'name': 'X'}, format='json')
        assert r.status_code == 403

    def test_list_zones(self, admin_client, access_zone):
        r = admin_client.get('/api/zones/')
        assert r.status_code == 200
        assert r.data['count'] >= 1

    def test_get_zone_detail(self, admin_client, access_zone):
        r = admin_client.get(f'/api/zones/{access_zone.id}/')
        assert r.status_code == 200
        assert r.data['name'] == access_zone.name

    def test_zone_not_found_returns_404(self, admin_client):
        r = admin_client.get('/api/zones/99999/')
        assert r.status_code == 404

    def test_update_zone(self, admin_client, access_zone):
        r = admin_client.patch(f'/api/zones/{access_zone.id}/', {
            'description': 'Updated description'
        }, format='json')
        assert r.status_code == 200
        assert r.data['description'] == 'Updated description'

    def test_delete_zone(self, admin_client, access_zone):
        r = admin_client.delete(f'/api/zones/{access_zone.id}/')
        assert r.status_code == 204

    def test_unauthenticated_returns_401(self, api_client):
        r = api_client.get('/api/zones/')
        assert r.status_code == 401


@pytest.mark.django_db
class TestZoneRules:
    def test_add_rule_to_zone(self, admin_client, access_zone, enrolled_person):
        r = admin_client.post(f'/api/zones/{access_zone.id}/rules/', {
            'person': enrolled_person.id,
            'permission': 'allow',
        }, format='json')
        assert r.status_code == 201
        assert r.data['permission'] == 'allow'

    def test_duplicate_rule_returns_400(self, admin_client, access_zone, enrolled_person):
        admin_client.post(f'/api/zones/{access_zone.id}/rules/', {
            'person': enrolled_person.id, 'permission': 'allow',
        }, format='json')
        r = admin_client.post(f'/api/zones/{access_zone.id}/rules/', {
            'person': enrolled_person.id, 'permission': 'deny',
        }, format='json')
        assert r.status_code == 400

    def test_list_rules_for_zone(self, admin_client, access_zone, enrolled_person):
        admin_client.post(f'/api/zones/{access_zone.id}/rules/', {
            'person': enrolled_person.id, 'permission': 'allow',
        }, format='json')
        r = admin_client.get(f'/api/zones/{access_zone.id}/rules/')
        assert r.status_code == 200
        assert len(r.data) >= 1


@pytest.mark.django_db
class TestAccessEvents:
    def test_list_events(self, admin_client, access_event):
        r = admin_client.get('/api/zones/events/')
        assert r.status_code == 200

    def test_filter_by_outcome(self, admin_client, access_event):
        r = admin_client.get('/api/zones/events/?outcome=granted')
        assert r.status_code == 200
        for ev in r.data['results']:
            assert ev['outcome'] == 'granted'

    def test_filter_by_hours(self, admin_client, access_event):
        r = admin_client.get('/api/zones/events/?hours=24')
        assert r.status_code == 200

    def test_viewer_cannot_list_events(self, viewer_client):
        r = viewer_client.get('/api/zones/events/')
        assert r.status_code == 403


@pytest.mark.django_db
class TestAccessStats:
    def test_stats_returns_correct_structure(self, admin_client, access_event):
        r = admin_client.get('/api/zones/stats/?hours=24')
        assert r.status_code == 200
        for key in ['total', 'granted', 'denied', 'errors', 'grant_rate', 'by_hour', 'by_zone']:
            assert key in r.data

    def test_stats_counts_correctly(self, admin_client, access_zone, enrolled_person):
        from zones.models import AccessEvent
        AccessEvent.objects.create(zone=access_zone, person=enrolled_person, outcome='granted', confidence=0.9, camera_id='cam-001')
        AccessEvent.objects.create(zone=access_zone, person=None,            outcome='denied',  confidence=0.2, camera_id='cam-001')

        r = admin_client.get('/api/zones/stats/?hours=24')
        assert r.data['granted'] >= 1
        assert r.data['denied']  >= 1

    def test_grant_rate_is_percentage(self, admin_client, access_event):
        r = admin_client.get('/api/zones/stats/?hours=24')
        assert 0.0 <= r.data['grant_rate'] <= 100.0

    def test_guard_can_view_stats(self, guard_client, access_event):
        r = guard_client.get('/api/zones/stats/?hours=24')
        assert r.status_code == 200

    def test_viewer_cannot_view_stats(self, viewer_client):
        r = viewer_client.get('/api/zones/stats/?hours=24')
        assert r.status_code == 403