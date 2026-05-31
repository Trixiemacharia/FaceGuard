from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncHour
from django.utils import timezone
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AccessEvent, Zone, ZoneRule
from .serializers import AccessEventSerializer, ZoneRuleSerializer, ZoneSerializer


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsAdminOrGuard(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'guard')


class ZoneListView(generics.ListCreateAPIView):
    queryset = Zone.objects.all().order_by('name')
    serializer_class = ZoneSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.IsAuthenticated()]
        return [IsAdmin()]


class ZoneDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [IsAdmin()]


class ZoneRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = ZoneRuleSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return ZoneRule.objects.filter(zone_id=self.kwargs['zone_id']).select_related('person', 'zone').order_by('id')

    def perform_create(self, serializer):
        zone = Zone.objects.get(pk=self.kwargs['zone_id'])
        person = serializer.validated_data['person']
        if ZoneRule.objects.filter(zone=zone, person=person).exists():
            raise serializers.ValidationError({'person': 'This person already has a rule for this zone.'})
        serializer.save(zone=zone)


class AccessEventListView(generics.ListAPIView):
    serializer_class = AccessEventSerializer
    permission_classes = [IsAdminOrGuard]

    def get_queryset(self):
        qs = AccessEvent.objects.select_related('zone', 'person')
        outcome = self.request.query_params.get('outcome')
        hours = self.request.query_params.get('hours')

        if outcome:
            qs = qs.filter(outcome=outcome)
        if hours:
            try:
                since = timezone.now() - timedelta(hours=int(hours))
                qs = qs.filter(created_at__gte=since)
            except ValueError:
                pass
        return qs


class AccessStatsView(APIView):
    permission_classes = [IsAdminOrGuard]

    def get(self, request):
        try:
            hours = int(request.query_params.get('hours', 24))
        except ValueError:
            hours = 24

        since = timezone.now() - timedelta(hours=hours)
        qs = AccessEvent.objects.filter(created_at__gte=since)
        total = qs.count()
        granted = qs.filter(outcome=AccessEvent.Outcome.GRANTED).count()
        denied = qs.filter(outcome=AccessEvent.Outcome.DENIED).count()
        errors = qs.filter(outcome=AccessEvent.Outcome.ERROR).count()

        by_hour = (
            qs.annotate(hour=TruncHour('created_at'))
            .values('hour', 'outcome')
            .annotate(count=Count('id'))
            .order_by('hour')
        )
        by_zone = (
            qs.values('zone_id', 'zone__name')
            .annotate(count=Count('id'))
            .order_by('zone__name')
        )

        return Response({
            'total': total,
            'granted': granted,
            'denied': denied,
            'errors': errors,
            'grant_rate': round((granted / total) * 100, 2) if total else 0.0,
            'by_hour': list(by_hour),
            'by_zone': list(by_zone),
        })
