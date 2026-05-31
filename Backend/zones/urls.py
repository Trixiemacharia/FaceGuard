from django.urls import path

from . import views

urlpatterns = [
    path('zones/', views.ZoneListView.as_view(), name='zone-list'),
    path('zones/<int:pk>/', views.ZoneDetailView.as_view(), name='zone-detail'),
    path('zones/<int:zone_id>/rules/', views.ZoneRuleListCreateView.as_view(), name='zone-rules'),
    path('zones/events/', views.AccessEventListView.as_view(), name='access-events'),
    path('zones/stats/', views.AccessStatsView.as_view(), name='access-stats'),
]
