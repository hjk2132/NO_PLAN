# users/serializers.py

from .models import User, UserInfo, Trip, VisitedContent, Bookmark
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from dj_rest_auth.serializers import LoginSerializer, JWTSerializer
# --- 아래 4개의 import를 파일 상단에 추가해주세요 ---
from dj_rest_auth.registration.serializers import SocialLoginSerializer
from allauth.account.utils import complete_signup
from allauth.socialaccount.helpers import complete_social_login
from requests.exceptions import HTTPError


# --- 회원 정보 조회를 위한 시리얼라이저 ---
class UserSerializer(serializers.ModelSerializer):
    is_info_exist = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name', 'email', 'is_info_exist')

    def get_is_info_exist(self, obj):
        return UserInfo.objects.filter(user=obj).exists()


# --- 일반 회원가입을 위한 시리얼라이저 ---
class RegisterSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(write_only=True, required=True, error_messages={'required': '비밀번호 확인을 입력해주세요.'})

    class Meta:
        model = User
        fields = ('email', 'password', 'password2')
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {
                'error_messages': {
                    'unique': '이미 사용 중인 이메일입니다. 다른 이메일을 입력해주세요.'
                }
            }
        }

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "비밀번호가 일치하지 않습니다."})
        return data

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("이미 가입된 이메일 주소입니다.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


# --- 로그인 시 에러 메시지 커스터마이징을 위한 시리얼라이저 ---
class CustomLoginSerializer(LoginSerializer):
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            User = get_user_model()
            try:
                user_obj = User.objects.get(email=email)
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"error": "아이디가 존재하지 않습니다."}
                )

            user = authenticate(request=self.context.get('request'), username=email, password=password)

            if not user:
                raise serializers.ValidationError(
                    {"error": "비밀번호가 일치하지 않습니다."}
                )

            if not user.is_active:
                raise serializers.ValidationError({"error": "비활성화된 계정입니다."})
        else:
            raise serializers.ValidationError("이메일과 비밀번호를 모두 입력해주세요.")

        attrs['user'] = user
        return attrs


# --- 사용자 추가 정보(UserInfo)를 위한 시리얼라이저 ---
class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInfo
        fields = ('name', 'age', 'gender')


# --- 이름 설정을 위한 시리얼라이저 추가 ---
class SetNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('name',)

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("이름은 비워둘 수 없습니다.")
        return value


# --- 로그인/회원가입 시 사용자 정보를 포함하기 위한 커스텀 JWT 시리얼라이저 ---
class CustomJWTSerializer(JWTSerializer):
    user = UserSerializer(read_only=True)
    is_info_exist = serializers.SerializerMethodField()

    def get_is_info_exist(self, obj):
        user_instance = obj.get('user')
        if user_instance:
            return UserInfo.objects.filter(user=user_instance).exists()
        return False


# --- 비밀번호 변경을 위한 시리얼라이저 ---
class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password1 = serializers.CharField(required=True, write_only=True)
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("기존 비밀번호가 일치하지 않습니다.")
        return value

    def validate(self, data):
        if data['new_password1'] != data['new_password2']:
            raise serializers.ValidationError({"new_password2": "새 비밀번호가 일치하지 않습니다."})
        return data


# --- 여행 정보(Trip)를 위한 시리얼라이저 ---
class TripSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Trip
        fields = ('id', 'user', 'region', 'created_at', 'transportation', 'companion', 'adjectives', 'summary')
        read_only_fields = ('id', 'user', 'created_at')


# --- 방문 내역을(VisitedContent) 위한 시리얼라이저 ---
class VisitedContentSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.username')
    trip = serializers.ReadOnlyField(source='trip.id')

    class Meta:
        model = VisitedContent
        fields = (
            'id', 'user', 'trip', 'content_id', 'title', 'first_image', 'addr1', 'mapx',
            'mapy', 'overview', 'created_at', 'hashtags', 'recommend_reason'
        )
        read_only_fields = ('id', 'user', 'trip', 'created_at')


# --- 북마크(Bookmark)를 위한 시리얼라이저 ---
class BookmarkSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Bookmark
        fields = (
            'id', 'user', 'content_id', 'title', 'first_image', 'addr1', 'overview',
            'created_at', 'hashtags', 'recommend_reason'
        )
        read_only_fields = ('id', 'user', 'created_at')

    def validate(self, data):
        user = self.context['request'].user
        content_id = data.get('content_id')
        if Bookmark.objects.filter(user=user, content_id=content_id).exists():
            raise serializers.ValidationError({"detail": "이미 북마크에 추가된 장소입니다."})
        return data


# ### 이 클래스 전체를 파일 맨 아래에 추가해주세요! ###
# 이메일 중복 및 allauth 버전 호환성 오류를 모두 해결하는 커스텀 소셜 로그인 시리얼라이저
class CustomSocialLoginSerializer(SocialLoginSerializer):
    def validate(self, attrs):
        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("Request context is not available.")

        try:
            # dj-rest-auth의 기본 유효성 검사를 먼저 시도합니다.
            return super().validate(attrs)
        except serializers.ValidationError as e:
            # 유효성 검사에서 '이미 가입된 유저' 오류가 발생했을 때만 아래 로직을 실행합니다.
            if 'User is already registered with this e-mail address.' in str(e):

                # allauth 어댑터와 클라이언트를 동적으로 가져옵니다.
                from allauth.socialaccount.providers.oauth2.client import OAuth2Client
                from allauth.socialaccount.providers.kakao.views import KakaoOAuth2Adapter

                adapter = KakaoOAuth2Adapter(request)
                provider = adapter.get_provider()
                app = provider.app

                # dj-rest-auth가 사용하는 client를 재구성합니다.
                client = OAuth2Client(
                    request,
                    app.client_id,
                    app.secret,
                    adapter.access_token_method,
                    adapter.access_token_url,
                    # ### 여기가 핵심 수정 부분입니다! ###
                    # adapter.callback_url 대신 adapter.get_callback_url()을 호출합니다.
                    adapter.get_callback_url(request),
                    provider.get_scope(request),
                    key=app.key,
                    cert=app.cert,
                )

                token = {'access_token': attrs.get('access_token')}
                access_token = adapter.parse_token_response(token)
                sociallogin = adapter.complete_login(request, app, access_token)
                sociallogin.token = access_token

                # allauth의 로그인 완료 헬퍼 함수를 호출합니다.
                complete_social_login(request, sociallogin)

                # request.user에 로그인된 사용자가 있는지 최종 확인합니다.
                if not getattr(request, 'user', None) or not request.user.is_authenticated:
                    raise serializers.ValidationError(
                        "Failed to log in the user after attempting to connect social account.")

                # 성공적으로 로그인된 user 객체를 attrs에 담아 반환합니다.
                attrs['user'] = request.user
                return attrs
            else:
                # '이미 가입된 유저' 문제가 아닌 다른 유효성 오류는 그대로 발생시킵니다.
                raise e
        except HTTPError as e:
            # 카카오 서버와의 통신 자체에서 에러가 발생한 경우
            raise serializers.ValidationError(str(e))
