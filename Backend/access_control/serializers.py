from rest_framework import serializers
from .models import AccessPoint,AccessEvent

class AccessPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessPoint
        fields = '__all__'

class AccessEventSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source='zone.name', read_only=True)
    ussername = serializers.CharField(source='user.username',read_only=True, default='Unknown')

    class Meta:
        model = AccessEvent
        fields = ['id','zone','zone_name','user','username','result','confidence','timestamp','ip_address']