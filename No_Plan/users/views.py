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
    , BookmarkSerializer, CustomJWTSerializer  # CustomJWTSerializer를 직접 사용하기 위해 import
)


# ===================================================================
# 소셜 로그인 (카카오)
# ===================================================================
class KakaoLogin(SocialLoginView):
    """
    웹 브라우저/웹뷰와 React Native 앱 모두를 위한 통합 카카오 로그인 엔드포인트.
    - 웹: 카카오 로그인 후 리디렉션되면 GET 요청으로 code를 받아 처리.
    - 앱: 카카오 SDK로 얻은 access_token을 POST 요청으로 받아 처리.
    두 경우 모두 최종적으로 서비스의 JWT 토큰을 JSON으로 반환합니다.
    """
    adapter_class = KakaoOAuth2Adapter
    client_class = OAuth2Client
    callback_url = "https://www.no-plan.cloud/api/v1/users/kakao/" # 카카오 개발자 콘솔에 등록된 리디렉션 URI

    def get(self, request, *args, **kwargs):
        # 1. 웹 브라우저 환경에서 카카오 로그인 후 리디렉션되어 '인가 코드'를 GET 파라미터로 받음
        code = request.query_params.get('code')
        if not code:
            return Response(
                {"error": "인가 코드가 URL 파라미터에 없습니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 2. 받은 인가 코드로 카카오에 access_token을 요청
        token_url = "https://kauth.kakao.com/oauth/token"
        
        # settings.py의 SOCIALACCOUNT_PROVIDERS 설정에서 client_id를 가져옴
        client_id = settings.SOCIALACCOUNT_PROVIDERS['kakao']['APP']['client_id']
        
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": self.callback_url,
            "code": code,
        }
        
        # 카카오 서버로 토큰 요청
        token_response = requests.post(token_url, data=data)
        token_json = token_response.json()

        # 토큰 요청 실패 시 에러 응답
        if 'error' in token_json:
            return Response(
                {"error": token_json.get('error_description', '카카오 토큰 발급에 실패했습니다.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        kakao_access_token = token_json.get("access_token")

        # 3. 받은 access_token을 사용하여 이 클래스의 post 메소드를 호출
        #    이렇게 하면 웹 요청(code)을 앱 요청(access_token)과 동일한 로직으로 처리할 수 있음
        request.data['access_token'] = kakao_access_token
        return self.post(request, *args, **kwargs)


    def post(self, request, *args, **kwargs):
        # dj-rest-auth의 기본 로직을 타되, HTML 리디렉션 대신 JSON을 직접 만들어 반환하도록 오버라이딩.
        
        # 1. 부모 클래스의 시리얼라이저를 통해 sociallogin 객체를 가져옴
        #    이 과정에서 access_token 유효성 검증, 유저 생성/조회(어댑터 실행)가 일어남
        try:
            self.serializer = self.get_serializer(data=request.data)
            self.serializer.is_valid(raise_exception=True)
            # sociallogin 객체는 유효성 검사 후 serializer 내부에 저장됨
            sociallogin = self.serializer.validated_data.get('sociallogin')
        except Exception as e:
            # 토큰이 유효하지 않거나 다른 문제가 발생했을 때
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 2. allauth의 표준 로그인/연결 로직을 실행
        sociallogin.login(request)

        # 3. 로그인된 사용자 객체를 가져옴
        user = sociallogin.user

        # 4. 직접 JWT 토큰을 생성하여 응답 (CustomJWTSerializer 사용)
        #    CustomJWTSerializer는 'user' 속성을 가진 객체를 인스턴스로 기대하므로,
        #    간단한 컨테이너 클래스를 만들어 user 객체를 감싸서 전달합니다.
        class UserContainer:
            def __init__(self, user_instance):
                self.user = user_instance

        jwt_serializer = CustomJWTSerializer(instance=UserContainer(user), context={'request': request})
        response_data = jwt_serializer.to_representation(UserContainer(user))
        
        # 5. 성공적으로 생성된 토큰과 사용자 정보가 담긴 JSON을 반환
        return Response(response_data, status=status.HTTP_200_OK)


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
    def get_queryset(self):
        return User.objects.all()
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