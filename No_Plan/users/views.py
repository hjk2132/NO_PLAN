# users/views.py
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
from .utils import get_region_from_coords
from .serializers import (
    RegisterSerializer, UserSerializer, PasswordChangeSerializer, SetNameSerializer,
    UserInfoSerializer, TripSerializer, VisitedContentSerializer, BookmarkSerializer, CustomJWTSerializer
)


# ===================================================================
# 소셜 로그인 (카카오) - 직접 구현 (최종 해결책)
# ===================================================================
class KakaoAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # 1. 프론트엔드로부터 'access_token'을 받습니다.
        access_token = request.data.get('access_token')
        if not access_token:
            return Response({"error": "Access token is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. 받은 access_token을 사용하여 카카오 서버에 사용자 정보를 요청합니다.
        profile_request = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # 2-1. 만약 카카오 서버가 에러를 반환하면, 그 내용을 그대로 출력하고 에러를 반환합니다.
        if profile_request.status_code != 200:
            return Response(
                {"error": "Failed to get user info from Kakao.", "detail": profile_request.json()},
                status=profile_request.status_code
            )

        profile_json = profile_request.json()
        kakao_account = profile_json.get('kakao_account')
        email = kakao_account.get('email')
        nickname = kakao_account.get('profile', {}).get('nickname')

        # 3. 받아온 이메일로 우리 데이터베이스에서 유저를 찾거나, 새로 만듭니다.
        try:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,  # username 필드는 email과 동일하게 설정
                    'name': nickname,
                }
            )

            # 만약 기존 유저인데 이름이 없다면, 카카오 닉네임으로 업데이트합니다.
            if not created and not user.name:
                user.name = nickname
                user.save()

            # 4. 우리 서비스의 JWT 토큰 (access, refresh)을 생성합니다.
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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