# users/urls.py

# 기본 import
from django.urls import path
# dj-rest-auth가 제공하는 View
from dj_rest_auth.views import LoginView
# simple-jwt가 제공하는 View
from rest_framework_simplejwt.views import TokenRefreshView
# 직접 만든 View
from .views import (
    RegisterView, LogoutView, UserDetailView, PasswordChangeView
, KakaoLogin, SetNameView, UserInfoView, FindRegionView, TripListCreateView,
    VisitedContentListCreateView, BookmarkListCreateView, BookmarkDetailView,
    UserWithdrawalView, KakaoConnectView,
)

urlpatterns = [
    # 일반 회원가입
    path('register/', RegisterView.as_view(), name='register'),

    # 로그인 (dj-rest-auth의 LoginView 사용으로 변경)
    path('login/', LoginView.as_view(), name='rest_login'),

    # 로그아웃 (user 앱의 LogoutView 사용으로 변경)
    path('logout/', LogoutView.as_view(), name='rest_logout'),

    # 사용자 이름 설정
    path('set_name/', SetNameView.as_view(), name='set_name'),

    # 사용자 정보 (user 모델의 정보)
    path('me/', UserDetailView.as_view(), name='user_detail'),

    # 회원탈퇴
    path('me/withdraw/', UserWithdrawalView.as_view(), name='user-withdrawal'),

    # 사용자 추가 정보 (UserInfo 모델의 정보)
    path('me/info/', UserInfoView.as_view(), name='user_info'),

    # 비밀번호 변경
    path('password/change/', PasswordChangeView.as_view(), name='password_change'),

    # 토큰 재발급
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 카카오 소셜 로그인
    path('kakao/', KakaoLogin.as_view(), name='kakao_login'),

    # 카카오 계정 연동을 위한 새로운 경로
    path('kakao/connect/', KakaoConnectView.as_view(), name='kakao_connect'),

    # 카카오 지도 위경도 -> 지역
    path('find-region/', FindRegionView, name='find_region'),

    # 여행 테이블 조회 및 생성
    path('trips/', TripListCreateView.as_view(), name='trip-list-create'),

    # 방문한 장소(콘텐츠) 조회 및 생성
    path('visited-contents/', VisitedContentListCreateView.as_view(), name='visited-content-list-create'),

    # 북마크 목록 조회 및 생성
    path('bookmarks/', BookmarkListCreateView.as_view(), name='bookmark-list-create'),

    # 북마크 상세 조회(삭제)
    path('bookmarks/<int:pk>/', BookmarkDetailView.as_view(), name='bookmark-detail'),
]