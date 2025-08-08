# users/views.py

# 기본 import
from .models import User, UserInfo, Trip, VisitedContent, Bookmark
from django.http import JsonResponse
from django.conf import settings
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from allauth.socialaccount.providers.kakao.views import KakaoOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.exceptions import ValidationError # ValidationError 임포트
import requests
import concurrent.futures

# kakao social log-in 관련 import
from allauth.socialaccount.providers.kakao.views import KakaoOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

# kakao map (x_y 2 addr)
from .utils import get_region_from_coords

# serializers import
from .serializers import (
    RegisterSerializer, UserSerializer, PasswordChangeSerializer
    , SetNameSerializer, UserInfoSerializer, TripSerializer, VisitedContentSerializer
    , BookmarkSerializer, CustomJWTSerializer
)


# ===================================================================
# 소셜 로그인 (카카오)
# ===================================================================
class KakaoLogin(SocialLoginView):
    """
    웹뷰 방식(GET)과 네이티브 SDK 방식(POST)을 모두 지원하는 통합 카카오 로그인 엔드포인트.
    """
    adapter_class = KakaoOAuth2Adapter
    client_class = OAuth2Client
    # 실제 운영 환경의 Redirect URI를 사용해야 합니다.
    callback_url = "https://www.no-plan.cloud/api/v1/users/kakao/"

    def get(self, request, *args, **kwargs):
        code = request.query_params.get('code')
        if not code:
            return Response({"error": "URL 쿼리 파라미터에 'code'가 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_url = "https://kauth.kakao.com/oauth/token"
            client_id = settings.SOCIALACCOUNT_PROVIDERS['kakao']['APP']['client_id']
            data = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": self.callback_url,
                "code": code,
            }
            token_response = requests.post(token_url, data=data)
            token_response.raise_for_status()
            token_json = token_response.json()
            access_token = token_json.get("access_token")

            if not access_token:
                # 카카오 응답에 access_token이 없는 경우
                error_description = token_json.get("error_description", "알 수 없는 오류")
                return Response(
                    {"error": "카카오로부터 액세스 토큰을 받아오지 못했습니다.", "details": error_description},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except requests.exceptions.RequestException as e:
            return Response({"error": f"카카오 서버 통신 오류: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
        auth_data = {'access_token': access_token}
        return self.process_login(request, auth_data)

    def post(self, request, *args, **kwargs):
        auth_data = request.data
        if not auth_data.get('access_token'):
            return Response({"error": "POST 본문에 'access_token'이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)
        return self.process_login(request, auth_data)

    def process_login(self, request, auth_data):
        # [수정된 헬퍼 메소드]
        try:
            # dj-rest-auth의 시리얼라이저를 통해 SocialLogin 객체 생성 시도
            self.serializer = self.get_serializer(data=auth_data)
            self.serializer.is_valid(raise_exception=True)
            
            # validated_data에서 sociallogin 객체를 가져옴
            sociallogin = self.serializer.validated_data.get('sociallogin')
            
            # 만약의 경우를 대비한 방어 코드 (adapter 수정으로 해결되지만, 유지하는 것이 안전)
            if not sociallogin:
                return Response(
                    {"error": "SocialLogin 객체를 생성하지 못했습니다. 서버 로그를 확인해주세요."}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except ValidationError as e:
            # dj-rest-auth 또는 allauth에서 발생한 유효성 검사 오류
            return Response({'error': '소셜 로그인 처리 중 오류가 발생했습니다.', 'details': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # 그 외 예상치 못한 모든 오류
            return Response({'error': f'알 수 없는 서버 오류가 발생했습니다: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # allauth를 통해 실제 Django 세션에 로그인 처리
        sociallogin.login(request)
        
        # JWT 토큰 생성 및 반환
        user = sociallogin.user
        refresh = RefreshToken.for_user(user)
        token_data = {
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': user  # user 객체를 넘겨주어야 CustomJWTSerializer가 인식
        }
        
        # 커스텀 JWT 시리얼라이저로 최종 응답 생성
        jwt_serializer = CustomJWTSerializer(instance=token_data, context={'request': request})
        return Response(jwt_serializer.data, status=status.HTTP_200_OK)


# ===================================================================
# 카카오 지도 (위경도 -> 주소)
# ===================================================================
def FindRegionView(request):
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')

    if not lat or not lon:
        return JsonResponse({'error': 'Latitude and longitude parameters are required.'}, status=400)

    region_info = get_region_from_coords(latitude=lat, longitude=lon)

    if region_info:
        return JsonResponse(region_info)
    else:
        return JsonResponse({'error': 'Could not find a region for the given coordinates.'}, status=404)


# ===================================================================
# 일반 회원가입, 정보 조회, 비밀번호 변경, 로그아웃
# ===================================================================
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class PasswordChangeView(generics.UpdateAPIView):
    serializer_class = PasswordChangeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            self.object.set_password(serializer.validated_data['new_password1'])
            self.object.save()
            return Response({"detail": "비밀번호가 성공적으로 변경되었습니다."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetNameView(generics.UpdateAPIView):
    serializer_class = SetNameSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)


# ===================================================================
# 회원 탈퇴
# ===================================================================
class UserWithdrawalView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"detail": "회원탈퇴가 성공적으로 처리되었습니다."}, status=status.HTTP_200_OK)


# ===================================================================
# 사용자 추가 정보 관리
# ===================================================================
class UserInfoView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserInfoSerializer

    def get_object(self):
        try:
            return UserInfo.objects.get(user=self.request.user)
        except UserInfo.DoesNotExist:
            return None

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        if UserInfo.objects.filter(user=request.user).exists():
            return Response({"detail": "이미 사용자 추가 정보가 존재합니다."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.name = serializer.validated_data.get('name', user.name)
        user.save()
        serializer.save(user=user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.name = serializer.validated_data.get('name', user.name)
        user.save()
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if 'name' in serializer.validated_data:
            user = request.user
            user.name = serializer.validated_data['name']
            user.save()
        serializer.save()
        return Response(serializer.data)

# ===================================================================
# 여행 테이블 조회 및 생성
# ===================================================================
class TripListCreateView(generics.ListCreateAPIView):
    queryset = Trip.objects.all()
    serializer_class = TripSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Trip.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ===================================================================
# 방문지 테이블 조회 및 생성
# ===================================================================
class VisitedContentListCreateView(generics.ListCreateAPIView):
    serializer_class = VisitedContentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return VisitedContent.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        latest_trip = Trip.objects.filter(user=user).first()
        if not latest_trip:
            raise ValidationError({"detail": "여행 기록이 없어 방문지를 추가할 수 없습니다. 여행을 먼저 생성해주세요."})
        serializer.save(user=user, trip=latest_trip)


# ===================================================================
# 북마크 조회, 생성, 삭제
# ===================================================================

class BookmarkListCreateView(generics.ListCreateAPIView):
    serializer_class = BookmarkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class BookmarkDetailView(generics.DestroyAPIView):
    serializer_class = BookmarkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user)
