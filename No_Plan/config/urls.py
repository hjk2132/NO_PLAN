# /home/user/NO_PLAN/No_Plan/config/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/users/', include('users.urls')),
    path('api/v1/tours/', include('tour_api.urls')),
    path('accounts/', include('allauth.urls')),
]
