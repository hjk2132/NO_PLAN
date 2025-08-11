# users/urls.py

from django.urls import path
from dj_rest_auth.views import LoginView
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, LogoutView, UserDetailView, PasswordChangeView,
    KakaoAPIView, SetNameView, UserInfoView, FindRegionView, TripListCreateView,
    VisitedContentListCreateView, BookmarkListCreateView, BookmarkDetailView,
    UserWithdrawalView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='rest_login'),
    path('logout/', LogoutView.as_view(), name='rest_logout'),
    path('set_name/', SetNameView.as_view(), name='set_name'),
    path('me/', UserDetailView.as_view(), name='user_detail'),
    path('me/withdraw/', UserWithdrawalView.as_view(), name='user-withdrawal'),
    path('me/info/', UserInfoView.as_view(), name='user_info'),
    path('password/change/', PasswordChangeView.as_view(), name='password_change'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),


    path('kakao/', KakaoAPIView.as_view(), name='kakao_login'),
    path('find-region/', FindRegionView, name='find_region'),
    path('trips/', TripListCreateView.as_view(), name='trip-list-create'),
    path('visited-contents/', VisitedContentListCreateView.as_view(), name='visited-content-list-create'),
    path('bookmarks/', BookmarkListCreateView.as_view(), name='bookmark-list-create'),
    path('bookmarks/<int:pk>/', BookmarkDetailView.as_view(), name='bookmark-detail'),
]
