from rest_framework import generics, permissions
from .models import Alert
from .serializers import AlertSerializer

class AlertListView(generics.ListCreateAPIView):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]

class AlertDetailView(generics.RetrieveUpdateAPIView):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]

