from rest_framework import serializers
from .models import AccessPoint

class AccessPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessPoint
        fields = '__all__'