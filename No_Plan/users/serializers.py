from .models import User, UserInfo, Trip, VisitedContent, Bookmark
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from dj_rest_auth.serializers import LoginSerializer, JWTSerializer

# --- 회원 정보 조회를 위한 시리얼라이저 ---
class UserSerializer(serializers.ModelSerializer):
    is_info_exist = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name', 'email', 'is_info_exist') # fields에도 추가

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
        # User 모델의 username 필드도 unique=True 이므로, email을 username으로 사용한다면
        # email 중복 체크만으로 username 중복 체크도 함께 처리됩니다.
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
    # email, password 필드는 부모 클래스(LoginSerializer)에 이미 정의되어 있으므로
    # 따로 정의할 필요가 없습니다.

    def validate(self, attrs):
        # email과 password는 attrs 딕셔너리에서 가져옵니다.
        # 부모 클래스는 username을 사용하지만, 우리는 email로 인증할 것입니다.
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            # 1. 아이디(이메일) 존재 여부 확인
            User = get_user_model()
            try:
                user_obj = User.objects.get(email=email)
            except User.DoesNotExist:
                # 사용자가 존재하지 않을 때, 우리가 원하는 에러 메시지를 발생시킵니다.
                raise serializers.ValidationError(
                    {"error": "아이디가 존재하지 않습니다."}
                )

            # 2. Django의 내장 인증 함수 authenticate()를 사용합니다.
            # 이 함수는 username과 password를 받지만, 우리의 커스텀 User 모델은
            # USERNAME_FIELD = 'username'으로 되어 있고, 우리는 username 필드에 email을 저장하고 있습니다.
            # 따라서 username 파라미터에 email을 전달해야 합니다.
            user = authenticate(request=self.context.get('request'), username=email, password=password)

            # authenticate() 함수는 인증에 실패하면 None을 반환합니다.
            if not user:
                # 이메일은 맞지만 비밀번호가 틀린 경우에 해당합니다.
                raise serializers.ValidationError(
                    {"error": "비밀번호가 일치하지 않습니다."}
                )

            # 3. 계정 활성화 여부 확인
            if not user.is_active:
                raise serializers.ValidationError({"error": "비활성화된 계정입니다."})
        else:
            raise serializers.ValidationError("이메일과 비밀번호를 모두 입력해주세요.")

        # 모든 검증을 통과하면, 인증된 user 객체를 attrs에 담아 반환합니다.
        attrs['user'] = user
        return attrs


# --- 사용자 추가 정보(UserInfo)를 위한 시리얼라이저 ---
class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInfo
        # API를 통해 다룰 필드들을 명시합니다.
        fields = ('name', 'age', 'gender')



# --- 이름 설정을 위한 시리얼라이저 추가 ---
class SetNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('name',) # , 꼭 남겨둬야

    def validate_name(self, value):
        # 이름이 비어있거나 공백으로만 이루어진 경우를 방지.
        if not value or not value.strip():
            raise serializers.ValidationError("이름은 비워둘 수 없습니다.")
        # User 모델에 정의된 max_length를 초과하는지 ModelSerializer가 자동으로 검사.
        return value


# --- 로그인/회원가입 시 사용자 정보를 포함하기 위한 커스텀 JWT 시리얼라이저 ---
class CustomJWTSerializer(JWTSerializer):
    user = UserSerializer(read_only=True)
    is_info_exist = serializers.SerializerMethodField()

    def get_is_info_exist(self, obj):
        # obj는 Token 객체이므로, obj.user로 접근합니다.
        user = obj.user
        return UserInfo.objects.filter(user=user).exists()

    def to_representation(self, instance):
        # to_representation을 오버라이드하여 user와 is_info_exist 필드를 포함시킵니다.
        representation = super().to_representation(instance)

        user_serializer = UserSerializer(instance.user)
        representation['user'] = user_serializer.data

        # is_info_exist 필드 값을 직접 계산하여 추가합니다.
        representation['is_info_exist'] = self.get_is_info_exist(instance)

        return representation

'''
class CustomJWTSerializer(JWTSerializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)

    # SerializerMethodField를 사용하여 계산된 값을 필드에 추가
    is_info_exist = serializers.SerializerMethodField()

    def get_is_info_exist(self, obj):
        user = obj.get('user')
        if user:
            # 해당 user와 연결된 UserInfo가 존재하는지 여부(True/False)를 반환합니다.
            return UserInfo.objects.filter(user=user).exists()
        return False
'''

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
    # user 필드를 읽기 전용으로 설정하고, 사용자의 username을 보여주도록 설정합니다.
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Trip
        fields = ('id', 'user', 'region', 'created_at')
        # API를 통해 클라이언트가 직접 입력하는 필드는 'region' 뿐이므로
        # 나머지 필드는 읽기 전용으로 설정하여 안정성을 높입니다.
        read_only_fields = ('id', 'user', 'created_at')


# --- 방문 내역을(VisitedContent) 위한 시리얼라이저 ---
class VisitedContentSerializer(serializers.ModelSerializer):
    """
    방문한 여행 콘텐츠(VisitedContent)를 위한 시리얼라이저
    """
    # user와 trip 필드는 응답에 포함될 때 username과 trip의 id를 보여주도록 설정
    user = serializers.ReadOnlyField(source='user.username')
    trip = serializers.ReadOnlyField(source='trip.id')

    class Meta:
        model = VisitedContent
        # API를 통해 보여줄 필드 목록
        fields = (
            'id',
            'user',
            'trip',
            'content_id',
            'title',
            'first_image',
            'addr1',
            'mapx',
            'mapy',
            'overview',
            'created_at'
        )
        # 클라이언트가 직접 입력하지 않고 서버에서 자동 설정할 필드
        # 'id': 자동 생성
        # 'user': 현재 로그인한 사용자로 자동 설정
        # 'trip': 사용자의 가장 최근 여행으로 자동 설정
        # 'created_at': 자동 생성
        read_only_fields = ('id', 'user', 'trip', 'created_at')

# --- 북마크(Bookmark)를 위한 시리얼라이저 ---
class BookmarkSerializer(serializers.ModelSerializer):
    """
    북마크(Bookmark) 생성을 위한 시리얼라이저
    """
    # user 필드는 응답에 포함될 때 username을 보여주도록 설정 (읽기 전용)
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Bookmark
        # API를 통해 보여주거나 입력받을 필드 목록
        fields = (
            'id',           # 북마크 고유 ID (응답용)
            'user',         # 북마크한 사용자 (응답용)
            'content_id',
            'title',
            'first_image',
            'addr1',
            'overview',
            'created_at'    # 북마크 생성 시각 (응답용)
        )
        # 클라이언트가 직접 입력하지 않고, 서버에서 자동 설정할 필드들
        # 'id', 'user', 'created_at'는 서버에서 자동 처리되므로 읽기 전용으로 설정
        read_only_fields = ('id', 'user', 'created_at')

    def validate(self, data):
        """
        중복 북마크 생성 방지를 위한 검증 로직 추가
        """
        # 현재 로그인한 사용자를 context에서 가져옵니다.
        user = self.context['request'].user
        content_id = data.get('content_id')

        # 해당 사용자가 이미 이 content_id를 북마크했는지 확인
        if Bookmark.objects.filter(user=user, content_id=content_id).exists():
            # 이미 존재한다면 ValidationError를 발생시켜 중복 저장을 막습니다.
            raise serializers.ValidationError({"detail": "이미 북마크에 추가된 장소입니다."})

        return data