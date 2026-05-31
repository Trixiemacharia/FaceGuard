from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/',     admin.site.urls),
    path('api/auth/',  include('users.urls')),
    path('api/',       include('recognition.urls')),
    path('api/',       include('logs.urls')),
    path('api/',       include('alerts.urls')),
    path('api/',       include('access_control.urls')),
    path('api/',       include('zones.urls')),
    path('api/',       include('reports.urls')),
    path('',           TemplateView.as_view(template_name='index.html'),     name='home'),
    path('dashboard/', TemplateView.as_view(template_name='admin_dashboard.html'), name='dashboard'),
    path('guard/',     TemplateView.as_view(template_name='guard.html'),     name='guard'),
    path('enrol/',     TemplateView.as_view(template_name='enrol_person.html'), name='enrol'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
