from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('login/',    views.LoginView.as_view(),    name='token_obtain_pair'),
    path('refresh/',  TokenRefreshView.as_view(),   name='token_refresh'),
    path('logout/',   views.LogoutView.as_view(),   name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/',  views.ProfileView.as_view(),  name='profile'),
    path('users/',    views.UserListView.as_view(),  name='user_list'),
]