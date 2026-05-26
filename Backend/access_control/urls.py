from django.urls import path
from . import views

urlpatterns = [
    path('access-points/', views.AccessPointListView.as_view(), name='access_point_list'),
    path('access-points/<int:pk>/', views.AccessPointDetailView.as_view(), name='access_point_detail'),
]