from django.conf import settings
from django.urls import path

from apps.users import views

urlpatterns = [
    path('auth/login', views.login_view),
    path('auth/register', views.register_view),
    path('auth/change-password', views.change_password_view),
    path('auth/refresh', views.refresh_token_view),
    path('users/me', views.me_view),
]

if getattr(settings, 'ENABLE_LEGACY_BIDS', False):
    urlpatterns.append(path('users/<int:user_id>/bids', views.user_bids_view))
