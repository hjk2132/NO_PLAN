from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        # allauth의 기본 로직을 통해 user 객체를 먼저 가져옵니다.
        # (이메일이 일치하는 기존 유저를 찾아주는 등의 작업이 이미 처리된 상태)
        user = super().populate_user(request, sociallogin, data)

        # 1. 닉네임 채우기 (부가 정보)
        # 카카오 프로필 닉네임이 있고, 우리 DB에 이름이 아직 없을 때만 채웁니다.
        nickname = data.get('properties', {}).get('nickname')
        if nickname and not user.name:
            user_field(user, 'name', nickname)

        # 2. 이메일이 없는 비상시에만 username 채우기
        # Django User 모델은 username이 필수 필드입니다.
        # allauth는 settings.py 설정에 따라 이메일로 username을 채우려고 시도합니다.
        # 이메일이 없는 경우에만 우리가 직접 고유 ID로 username을 설정해줍니다.
        if not user.username:
            email = data.get('email')
            if not email:
                uid = sociallogin.account.uid
                user.username = f"kakao_{uid}"

        return user