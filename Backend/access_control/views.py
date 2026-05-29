from rest_framework import generics, permissions
from .models import AccessPoint, AccessEvent
from .serializers import AccessPointSerializer

class AccessPointListView(generics.ListCreateAPIView):
    queryset = AccessPoint.objects.all()
    serializer_class = AccessPointSerializer
    permission_classes = [permissions.IsAdminUser]

class AccessPointDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = AccessPoint.objects.all()
    serializer_class = AccessPointSerializer
    permission_classes = [permissions.IsAdminUser]