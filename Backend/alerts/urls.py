from django.urls import path
from . import views

urlpatterns = [
    path('alerts/', views.AlertListView.as_view(), name='alert_list'),
    path('alerts/<int:pk>/', views.AlertDetailView.as_view(), name='alert_detail'),
]