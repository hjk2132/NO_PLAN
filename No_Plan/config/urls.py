"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/users/', include('users.urls')),
    path('api/v1/tours/', include('tour_api.urls')),

    # ===================================================================
    # [최종 수정된 부분]
    # allauth가 내부적으로 사용하는 URL들을 프로젝트에 포함시킵니다.
    # 이것이 'socialaccount_signup' 등의 URL을 찾을 수 있게 하여
    # NoReverseMatch 오류를 해결합니다.
    # 실제 웹 페이지를 사용하지 않더라도, 라이브러리의 정상 작동을 위해 반드시 필요합니다.
    # ===================================================================
    path('accounts/', include('allauth.urls')),
]
