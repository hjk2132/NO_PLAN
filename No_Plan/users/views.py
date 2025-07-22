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

# kakao social log-in
from allauth.socialaccount.providers.kakao.views import KakaoOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

# kakao map (x_y 2 addr)
from .utils import get_region_from_coords

# serializers import
from .serializers import (
    RegisterSerializer, UserSerializer, PasswordChangeSerializer
    , SetNameSerializer, UserInfoSerializer, TripSerializer, VisitedContentSerializer
    , BookmarkSerializer
)


# ===================================================================
# 소셜 로그인 (카카오)
# ===================================================================
class KakaoLogin(SocialLoginView):
    adapter_class = KakaoOAuth2Adapter
    client_class = OAuth2Client
    callback_url = "http://127.0.0.1:8000/api/v1/users/kakao/"

    def get(self, request, *args, **kwargs):
        # 1. request.data 대신 request.query_params에서 'code'를 가져옵니다.
        code = request.query_params.get('code')

        if not code:
            return Response({"error": "인가 코드가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. 이후 로직은 기존 post 메소드와 완전히 동일합니다.
        token_url = "https://kauth.kakao.com/oauth/token"
        client_id = settings.SOCIALACCOUNT_PROVIDERS['kakao']['APP']['client_id']
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": self.callback_url,  # 카카오 개발자 콘솔에 등록된 리디렉션 URI
            "code": code,
        }

        token_response = requests.post(token_url, data=data)
        token_json = token_response.json()

        if 'error' in token_json:
            return Response(
                {"error": token_json['error'], "error_description": token_json.get('error_description', '')},
                status=status.HTTP_400_BAD_REQUEST
            )

        kakao_access_token = token_json.get("access_token")

        # 3. dj-rest-auth의 SocialLoginView가 처리할 수 있도록 access_token을 request.data에 추가합니다.
        #    GET 요청에는 body(data)가 없지만, DRF의 Request 객체는 이를 허용합니다.
        request.data['access_token'] = kakao_access_token

        # 4. 부모 클래스의 post 메소드를 호출하여 최종 로그인 처리를 위임합니다.
        #    이것이 최종적으로 토큰을 발급하고 사용자 정보를 응답하는 부분입니다.
        return super().post(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        code = request.data.get('code')
        if not code:
            return Response({"error": "인가 코드가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        token_url = "https://kauth.kakao.com/oauth/token"
        client_id = settings.SOCIALACCOUNT_PROVIDERS['kakao']['APP']['client_id']
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": self.callback_url,
            "code": code,
        }

        token_response = requests.post(token_url, data=data)
        token_json = token_response.json()

        if 'error' in token_json:
            return Response(
                {"error": token_json['error'], "error_description": token_json.get('error_description', '')},
                status=status.HTTP_400_BAD_REQUEST
            )

        kakao_access_token = token_json.get("access_token")
        request.data['access_token'] = kakao_access_token

        return super().post(request, *args, **kwargs)

# ===================================================================
# 카카오 지도 (위경도 -> 주소)
# ===================================================================
def FindRegionView(request):
    # GET 파라미터에서 위도, 경도 값 가져오기
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')

    # 파라미터가 없는 경우 에러 응답
    if not lat or not lon:
        return JsonResponse({'error': 'Latitude and longitude parameters are required.'}, status=400)

    # 함수 호출하여 지역명 가져오기
    region_info = get_region_from_coords(latitude=lat, longitude=lon)

    # 결과에 따라 다른 JsonResponse 반환
    if region_info:
        # 딕셔너리를 그대로 JsonResponse에 전달합니다.
        return JsonResponse(region_info)
    else:
        return JsonResponse({'error': 'Could not find a region for the given coordinates.'}, status=404)


# ===================================================================
# 일반 회원가입, 정보 조회, 비밀번호 변경, 로그아웃
# ===================================================================

# 회원가입 API
class RegisterView(generics.CreateAPIView):
    def get_queryset(self):
        return User.objects.all()

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


# 현재 로그인된 사용자 정보 조회 API
class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# 비밀번호 변경 API
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

# 사용자 이름(name) 설정 API
class SetNameView(generics.UpdateAPIView):
    serializer_class = SetNameSerializer
    permission_classes = [IsAuthenticated] # 반드시 로그인한 사용자만 접근 가능

    def get_object(self):
        # 업데이트할 객체를 URL의 pk값에서 찾는 대신,
        # 현재 요청을 보낸 사용자 자신으로 지정합니다.
        return self.request.user

# 로그아웃 API
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
    """
    로그인한 사용자 본인의 계정을 삭제(회원탈퇴)합니다.
    DELETE 요청 시, 인증된 사용자의 계정이 삭제됩니다.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # 삭제할 객체를 현재 로그인된 사용자로 지정합니다.
        return self.request.user

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        # 기본 204 응답 대신, 커스텀 메시지를 포함한 200 응답을 반환합니다.
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

    # 정보 조회 (GET)
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            # 정보가 없으면 404 Not Found 에러를 반환합니다.
            return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    # 정보 생성 (POST)
    def post(self, request, *args, **kwargs):
        if UserInfo.objects.filter(user=request.user).exists():
            return Response({"detail": "이미 사용자 추가 정보가 존재합니다."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 1. User 모델의 name을 먼저 업데이트합니다.
        user = request.user
        user.name = serializer.validated_data.get('name', user.name)
        user.save()

        # 2. UserInfo를 생성합니다. user는 request.user를 사용합니다.
        serializer.save(user=user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # 정보 전체 수정 (PUT)
    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)

        # 1. User 모델의 name을 먼저 업데이트합니다.
        user = request.user
        user.name = serializer.validated_data.get('name', user.name)
        user.save()

        # 2. UserInfo를 수정합니다.
        serializer.save()
        return Response(serializer.data)

    # 정보 부분 수정
    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None:
            return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # 1. User 모델의 name을 먼저 업데이트합니다. (name이 요청에 포함된 경우에만)
        if 'name' in serializer.validated_data:
            user = request.user
            user.name = serializer.validated_data['name']
            user.save()

        # 2. UserInfo를 수정합니다.
        serializer.save()
        return Response(serializer.data)

# ===================================================================
# 여행 테이블 조회 및 생성
# ===================================================================
class TripListCreateView(generics.ListCreateAPIView):
    """
    로그인한 사용자의 여행 목록을 조회하거나 새로운 여행을 추가합니다.
    - GET: 사용자의 모든 여행 목록을 반환합니다.
    - POST: 새로운 여행을 생성합니다.
    """
    queryset = Trip.objects.all()
    serializer_class = TripSerializer
    permission_classes = [permissions.IsAuthenticated] # 반드시 로그인해야만 접근 가능

    def get_queryset(self):
        """
        이 view를 요청한 사용자(request.user)에게 속한 Trip 객체만 필터링하여 반환합니다.
        """
        user = self.request.user
        return Trip.objects.filter(user=user)

    def perform_create(self, serializer):
        """
        serializer.save()가 호출될 때, Trip 객체의 user 필드를
        현재 로그인된 사용자(request.user)로 자동 설정합니다.
        """
        serializer.save(user=self.request.user)


# ===================================================================
# 방문지 테이블 조회 및 생성
# ===================================================================
class VisitedContentListCreateView(generics.ListCreateAPIView):
    """
    로그인한 사용자의 방문지 목록을 조회(GET)하거나
    새로운 방문지를 추가(POST)합니다.
    """
    serializer_class = VisitedContentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        이 view를 요청한 사용자(request.user)에게 속한
        VisitedContent 객체만 필터링하여 반환합니다.
        """
        return VisitedContent.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """
        serializer.save()가 호출될 때, 추가 데이터를 자동으로 설정합니다.

        - user: 현재 로그인된 사용자(self.request.user)로 설정합니다.
        - trip: 현재 사용자의 가장 최근 여행(Trip)으로 설정합니다.
        """
        user = self.request.user

        # 1. 현재 사용자의 가장 최근 여행(Trip)을 찾습니다.
        # Trip 모델의 Meta.ordering에 따라 최신순으로 정렬되므로 first()로 가져옵니다.
        latest_trip = Trip.objects.filter(user=user).first()

        # 2. 만약 사용자가 생성한 여행이 하나도 없다면 에러를 발생시킵니다.
        if not latest_trip:
            raise ValidationError({"detail": "여행 기록이 없어 방문지를 추가할 수 없습니다. 여행을 먼저 생성해주세요."})

        # 3. serializer.save()를 호출하면서 user와 trip 객체를 전달합니다.
        #    이렇게 전달된 값은 read_only_fields라도 모델 객체 생성 시 사용됩니다.
        serializer.save(user=user, trip=latest_trip)


# ===================================================================
# 북마크 조회, 생성, 삭제
# ===================================================================

class BookmarkListCreateView(generics.ListCreateAPIView):
    """
    북마크 목록을 조회(GET)하거나 새로운 북마크를 생성(POST)합니다.
    """
    serializer_class = BookmarkSerializer
    permission_classes = [permissions.IsAuthenticated] # 반드시 로그인해야만 접근 가능

    def get_queryset(self):
        """
        이 view를 요청한 사용자(request.user)에게 속한 북마크 객체만 필터링하여 반환합니다.
        이를 통해 다른 사용자의 북마크를 조회하거나 수정하는 것을 방지합니다.
        """
        return Bookmark.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """
        serializer.save()가 호출될 때, Bookmark 객체의 user 필드를
        현재 로그인된 사용자(request.user)로 자동 설정합니다.
        """
        serializer.save(user=self.request.user)

class BookmarkDetailView(generics.DestroyAPIView):
    """
    특정 북마크를 삭제(DELETE)합니다.
    URL에서 전달된 pk를 기반으로 북마크를 식별합니다.
    """
    serializer_class = BookmarkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        여기서도 현재 로그인한 사용자의 북마크 내에서만 객체를 찾도록 제한하여,
        다른 사용자의 북마크를 삭제하려는 시도를 원천 차단합니다.
        """
        return Bookmark.objects.filter(user=self.request.user)