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
    UserInfoSerializer, TripSerializer, VisitedContentSerializer, BookmarkSerializer, CustomJWTSerializer,
    SocialConnectSerializer
)
from allauth.socialaccount.models import SocialAccount


# ##################################################################
# ### ▼▼▼ KakaoAPIView 의 로직이 완전히 개선되었습니다 ▼▼▼ ###
# ##################################################################
class KakaoAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        access_token = request.data.get('access_token')
        if not access_token:
            return Response({"error": "Access token is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. 카카오 서버로부터 사용자 정보 가져오기
        profile_request = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_request.status_code != 200:
            return Response({"error": "Failed to get user info from Kakao.", "detail": profile_request.json()}, status=profile_request.status_code)

        profile_json = profile_request.json()
        kakao_id = profile_json.get('id')
        kakao_account = profile_json.get('kakao_account')
        email = kakao_account.get('email')
        nickname = kakao_account.get('profile', {}).get('nickname')
        
        if not email:
            return Response({"error": "카카오 계정에 이메일 정보가 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 2. (핵심 변경) 카카오 고유 ID(uid)로 SocialAccount를 먼저 찾습니다.
            try:
                social_account = SocialAccount.objects.get(provider='kakao', uid=str(kakao_id))
                # SocialAccount가 존재하면, 연결된 사용자를 바로 가져옵니다.
                user = social_account.user
                
            # 3. SocialAccount가 없다면, 그 때 이메일로 사용자를 찾거나 새로 만듭니다.
            except SocialAccount.DoesNotExist:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={'username': email, 'name': nickname}
                )
                # 새로운 SocialAccount를 생성하여 연결해줍니다.
                SocialAccount.objects.create(
                    user=user,
                    provider='kakao',
                    uid=str(kakao_id),
                    extra_data=profile_json
                )
            
            # 4. (부가 로직) 사용자의 이름이 비어있다면 카카오 닉네임으로 업데이트
            if not user.name and nickname:
                user.name = nickname
                user.save(update_fields=['name'])

            # 5. 최종적으로 찾거나 생성된 사용자로 JWT 토큰 발급
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===================================================================
# 기타 유틸리티 및 인증 관련 Views
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

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    def get_object(self):
        return self.request.user

class KakaoConnectView(APIView):
    """
    현재 로그인된 사용자의 계정에 카카오 계정을 연결(Connect)합니다.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SocialConnectSerializer

    def post(self, request, *args, **kwargs):
        if SocialAccount.objects.filter(user=request.user, provider='kakao').exists():
            return Response(
                {"error": "이미 카카오 계정이 이 계정에 연결되어 있습니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        access_token = serializer.validated_data['access_token']
        profile_request = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_request.status_code != 200:
            return Response(
                {"error": "Failed to get user info from Kakao."},
                status=status.HTTP_400_BAD_REQUEST
            )
        profile_json = profile_request.json()
        kakao_id = profile_json.get('id')
        kakao_email = profile_json.get('kakao_account', {}).get('email')
        kakao_profile = profile_json.get('kakao_account', {}).get('profile', {})
        nickname = kakao_profile.get('nickname')
        if SocialAccount.objects.filter(provider='kakao', uid=kakao_id).exists():
            return Response(
                {"error": "이 카카오 계정은 이미 다른 사용자와 연결되어 있습니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if kakao_email and User.objects.filter(email=kakao_email).exclude(id=request.user.id).exists():
             return Response(
                {"error": "해당 소셜 계정의 이메일이 이미 다른 계정에서 사용 중입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            SocialAccount.objects.create(
                user=request.user,
                provider='kakao',
                uid=str(kakao_id),
                extra_data=profile_json
            )
            if not request.user.name and nickname:
                request.user.name = nickname
                request.user.save(update_fields=['name'])
        except Exception as e:
            return Response({"error": f"계정 연결 중 오류가 발생했습니다: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"detail": "카카오 계정이 성공적으로 연결되었습니다."}, status=status.HTTP_200_OK)


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

class UserWithdrawalView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"detail": "회원탈퇴가 성공적으로 처리되었습니다."}, status=status.HTTP_200_OK)

class UserInfoView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserInfoSerializer
    def get_object(self):
        try: return UserInfo.objects.get(user=self.request.user)
        except UserInfo.DoesNotExist: return None
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None: return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    def post(self, request, *args, **kwargs):
        if UserInfo.objects.filter(user=request.user).exists(): return Response({"detail": "이미 사용자 추가 정보가 존재합니다."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.name = serializer.validated_data.get('name', user.name)
        user.save()
        serializer.save(user=user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None: return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.name = serializer.validated_data.get('name', user.name)
        user.save()
        serializer.save()
        return Response(serializer.data)
    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance is None: return Response({"detail": "사용자 추가 정보가 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if 'name' in serializer.validated_data:
            user = request.user
            user.name = serializer.validated_data['name']
            user.save()
        serializer.save()
        return Response(serializer.data)

class TripListCreateView(generics.ListCreateAPIView):
    queryset = Trip.objects.all()
    serializer_class = TripSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        user = self.request.user
        return Trip.objects.filter(user=user)
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class TripDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        user = self.request.user
        return Trip.objects.filter(user=user)

class VisitedContentListCreateView(generics.ListCreateAPIView):
    serializer_class = VisitedContentSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        return VisitedContent.objects.filter(user=self.request.user)
    def perform_create(self, serializer):
        user = self.request.user
        latest_trip = Trip.objects.filter(user=user).first()
        if not latest_trip: raise ValidationError({"detail": "여행 기록이 없어 방문지를 추가할 수 없습니다. 여행을 먼저 생성해주세요."})
        serializer.save(user=user, trip=latest_trip)

### ▼▼▼ 여기에 새로운 클래스가 추가되었습니다 ▼▼▼ ###
class VisitedContentDetailView(generics.RetrieveDestroyAPIView):
    """
    특정 방문 기록을 조회(GET)하거나 삭제(DELETE)하는 뷰
    """
    serializer_class = VisitedContentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # 사용자는 자신의 방문 기록만 조회/삭제할 수 있도록 쿼리셋을 필터링합니다.
        return VisitedContent.objects.filter(user=self.request.user)
### ▲▲▲ 여기까지 추가 ▲▲▲ ###

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
