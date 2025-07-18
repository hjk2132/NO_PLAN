from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from .models import User  # 커스텀 User 모델 import

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