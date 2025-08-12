# users/urls.py

from django.urls import path
from dj_rest_auth.views import LoginView
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, LogoutView, UserDetailView, PasswordChangeView,
    KakaoAPIView, SetNameView, UserInfoView, FindRegionView,
    TripListCreateView, TripDetailView,
    VisitedContentListCreateView, BookmarkListCreateView, BookmarkDetailView,
    UserWithdrawalView,
    # ##################################################################
    # ### ▼▼▼ 여기에 새로운 View가 import 되었습니다 ▼▼▼ ###
    # ##################################################################
    KakaoConnectView
)

urlpatterns = [
    # 인증 및 사용자 정보 관련 URL
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='rest_login'),
    path('logout/', LogoutView.as_view(), name='rest_logout'),
    path('set_name/', SetNameView.as_view(), name='set_name'),
    path('me/', UserDetailView.as_view(), name='user_detail'),
    # ##################################################################
    # ### ▼▼▼ 여기에 새로운 URL 패턴이 추가되었습니다 ▼▼▼ ###
    # ##################################################################
    path('me/connect-kakao/', KakaoConnectView.as_view(), name='kakao-connect'),
    path('me/withdraw/', UserWithdrawalView.as_view(), name='user-withdrawal'),
    path('me/info/', UserInfoView.as_view(), name='user_info'),
    path('password/change/', PasswordChangeView.as_view(), name='password_change'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 소셜 로그인
    path('kakao/', KakaoAPIView.as_view(), name='kakao_login'),

    # 유틸리티
    path('find-region/', FindRegionView, name='find_region'),

    # 여행, 방문기록, 북마크
    path('trips/', TripListCreateView.as_view(), name='trip-list-create'),
    path('trips/<int:pk>/', TripDetailView.as_view(), name='trip-detail'),
    path('visited-contents/', VisitedContentListCreateView.as_view(), name='visited-content-list-create'),
    path('bookmarks/', BookmarkListCreateView.as_view(), name='bookmark-list-create'),
    path('bookmarks/<int:pk>/', BookmarkDetailView.as_view(), name='bookmark-detail'),
]
