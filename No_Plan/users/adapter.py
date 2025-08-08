from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from .models import User  # 커스텀 User 모델 import


'''
class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        # 카카오 프로필 닉네임을 가져옴
        nickname = data.get('properties', {}).get('nickname')

        # 닉네임이 있다면 우리 User 모델의 'name' 필드에 저장
        if nickname:
            user_field(user, 'name', nickname)

        # username을 채우는 로직 (이메일이 있다면 이메일, 없다면 고유 ID)
        email = data.get('email')
        if email:
            user_field(user, 'email', email)
            user_field(user, 'username', email)

        return user
'''

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        # allauth의 기본 로직을 통해 user 객체를 가져옵니다.
        # (기존에 이메일로 가입한 유저가 있다면 연결해주는 등의 작업 포함)
        user = super().populate_user(request, sociallogin, data)

        # 카카오 프로필 닉네임을 가져와 User 모델의 'name' 필드에 저장
        nickname = data.get('properties', {}).get('nickname')
        if nickname and not user.name: # 기존에 이름이 없을 때만 설정
            user_field(user, 'name', nickname)

        # 카카오 계정 정보에서 이메일을 가져옴
        email = data.get('email')
        
        # User 모델의 username 필드를 채웁니다.
        # Django의 User 모델은 username이 필수이므로, 반드시 채워줘야 합니다.
        if email:
            # 이메일이 있다면 이메일을 username으로 사용
            if not user.username:
                user_field(user, 'username', email)
            if not user.email:
                user_field(user, 'email', email)
        else:
            # 이메일이 없다면, 고유한 카카오 ID를 username으로 사용
            # sociallogin 객체를 통해 고유 ID(uid)에 접근할 수 있습니다.
            uid = sociallogin.account.uid
            if not user.username:
                # 예시: "kakao_1234567890" 와 같은 형태로 저장
                user_field(user, 'username', f"kakao_{uid}")
        
        return user