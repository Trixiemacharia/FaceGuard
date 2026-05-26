from rest_framework import generics, permissions
from .models import SystemLog
from .serializers import SystemLogSerializer

class SystemLogListView(generics.ListAPIView):
    queryset = SystemLog.objects.all()
    serializer_class = SystemLogSerializer
    permission_classes = [permissions.IsAdminUser]