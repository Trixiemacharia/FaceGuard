from rest_framework import serializers
from .models import EnrolledPerson, FaceEmbedding, VerificationLog


class FaceEmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceEmbedding
        fields = ['id', 'model_name', 'created_at']


class EnrolledPersonSerializer(serializers.ModelSerializer):
    embedding_count = serializers.ReadOnlyField()
    enrolled_by = serializers.StringRelatedField(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = EnrolledPerson
        fields = ['id', 'name', 'email', 'employee_id', 'department', 'is_active',
                  'enrolled_by', 'enrolled_at', 'notes', 'embedding_count']
        read_only_fields = ['id', 'enrolled_at', 'enrolled_by', 'embedding_count']


class EnrolmentSerializer(serializers.Serializer):
    name        = serializers.CharField(max_length=255)
    email       = serializers.EmailField(required=False, allow_blank=True)
    password    = serializers.CharField(required=False, allow_blank=True, min_length=8)
    role        = serializers.ChoiceField(choices=['admin', 'guard', 'viewer'], required=False, default='viewer')
    employee_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    department  = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes       = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        if email and not password:
            raise serializers.ValidationError({'password': 'Password is required when creating a login user.'})
        if password and not email:
            raise serializers.ValidationError({'email': 'Email is required when creating a login user.'})
        return attrs


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
