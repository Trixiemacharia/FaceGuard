from rest_framework import serializers
from .models import EnrolledPerson, FaceEmbedding, VerificationLog


class FaceEmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceEmbedding
        fields = ['id', 'model_name', 'created_at']


class EnrolledPersonSerializer(serializers.ModelSerializer):
    embedding_count = serializers.ReadOnlyField()
    enrolled_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = EnrolledPerson
        fields = ['id', 'name', 'employee_id', 'department', 'is_active',
                  'enrolled_by', 'enrolled_at', 'notes', 'embedding_count']
        read_only_fields = ['id', 'enrolled_at', 'enrolled_by', 'embedding_count']


class EnrolmentSerializer(serializers.Serializer):
    name        = serializers.CharField(max_length=255)
    employee_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    department  = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes       = serializers.CharField(required=False, allow_blank=True)


class VerifyFaceSerializer(serializers.Serializer):
    frames    = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=30,
    )
    camera_id = serializers.CharField(required=False, allow_blank=True, default='')


class VerificationLogSerializer(serializers.ModelSerializer):
    matched_person = EnrolledPersonSerializer(read_only=True)

    class Meta:
        model = VerificationLog
        fields = ['id', 'matched_person', 'outcome', 'confidence', 'distance',
                  'liveness_pass', 'camera_id', 'created_at', 'error_detail']
        read_only_fields = fields
