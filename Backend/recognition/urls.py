from django.urls import path
from . import views

urlpatterns = [
    path('enrol/', views.EnrolView.as_view(), name='enrol'),
    path('self-enrol/', views.SelfEnrolView.as_view(), name='self_enrol'),
    path('verify-face/', views.VerifyFaceView.as_view(), name='verify_face'),
    path('persons/', views.PersonListView.as_view(), name='person_list'),
    path('persons/<int:pk>/', views.PersonDetailView.as_view(), name='person_detail'),
    path('verification-logs/', views.VerificationLogListView.as_view(), name='verification_logs'),
]
