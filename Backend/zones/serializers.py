from rest_framework import serializers

from .models import AccessEvent, Zone, ZoneRule


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ['id', 'name', 'description', 'location', 'camera_ids', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class ZoneRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZoneRule
        fields = ['id', 'zone', 'person', 'permission', 'created_at']
        read_only_fields = ['id', 'zone', 'created_at']


class AccessEventSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source='zone.name', read_only=True)
    person_name = serializers.CharField(source='person.name', read_only=True)

    class Meta:
        model = AccessEvent
        fields = [
            'id',
            'zone',
            'zone_name',
            'person',
            'person_name',
            'outcome',
            'confidence',
            'camera_id',
            'liveness_pass',
            'denial_reason',
            'processing_ms',
            'frame_path',
            'ip_address',
            'created_at',
        ]
        read_only_fields = fields
