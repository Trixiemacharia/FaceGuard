import logging

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role',
                  'is_active', 'date_joined', 'last_login']
        read_only_fields = ['id', 'date_joined']


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label='Confirm password')

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email']     = user.email
        token['role']      = user.role
        token['full_name'] = user.get_full_name()
        return token

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            email = attrs.get(self.username_field, '')
            request = self.context.get('request')
            logger.warning('Failed password login attempt for %s', email or 'unknown user')
            try:
                from logs.models import SystemLog
                SystemLog.objects.create(
                    level=SystemLog.Level.WARNING,
                    source='auth',
                    message=f'Failed password login attempt for {email or "unknown user"}',
                    user=User.objects.filter(email=email).first() if email else None,
                )
            except Exception as exc:
                logger.warning('Could not persist failed login event: %s', exc)
            if request:
                request.failed_login_flagged = True
            raise
        data['user'] = UserSerializer(self.user).data
        return data
