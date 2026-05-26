from django.urls import path
from . import views

urlpatterns = [
    path('logs/', views.SystemLogListView.as_view(), name='system_logs'),
]