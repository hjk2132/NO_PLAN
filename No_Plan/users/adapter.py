# users/adapter.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model  # User 모델을 직접 가져오기 위해 추가

# User 모델을 가져옵니다.
User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        """
        소셜 로그인이 거의 완료되었을 때 호출되는 훅(hook)입니다.
        이메일이 중복되는 경우, 새 계정을 만들지 않고 기존 계정에 연결합니다.
        """
        # 소셜 계정이 이미 기존 유저와 연결되어 있다면, 아무것도 하지 않습니다.
        if sociallogin.is_existing:
            return

        # 소셜 계정 정보에서 이메일 주소를 가져옵니다.
        email = sociallogin.account.extra_data.get('email')

        # 만약 이메일이 있고, 해당 이메일로 가입한 유저가 이미 존재한다면,
        if email and User.objects.filter(email=email).exists():
            try:
                # 해당 이메일을 가진 유저를 찾습니다.
                user = User.objects.get(email=email)

                # 이 소셜 계정(sociallogin)을 기존 유저(user)와 연결합니다.
                # allauth는 이 과정에서 SOCIALACCOUNT_LOGIN_ON_EMAIL=True 설정을
                # 활용하여 자동으로 연결을 처리합니다.
                sociallogin.connect(request, user)

                # allauth의 EmailAddress 테이블에서 해당 이메일이 '인증'되었는지 확인하고,
                # 인증되지 않았다면 강제로 인증 상태로 변경합니다. (보안 정책 우회)
                try:
                    email_address = EmailAddress.objects.get(user=user, email=email)
                    if not email_address.verified:
                        email_address.verified = True
                        email_address.save()
                except EmailAddress.DoesNotExist:
                    # EmailAddress 레코드가 없는 경우(일반 회원가입 등) 새로 만들고 인증 처리합니다.
                    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)

            except User.DoesNotExist:
                # 만약 어떤 이유로 유저를 찾지 못한 경우, 예외를 발생시키지 않고
                # allauth가 새 계정을 만들도록 기본 로직에 맡깁니다.
                pass

    def populate_user(self, request, sociallogin, data):
        """
        새로운 사용자가 소셜 계정으로 회원가입할 때 사용자 모델 필드를 채우는 함수.
        """
        user = super().populate_user(request, sociallogin, data)

        # 닉네임만 채워주는 가장 기본적인 기능만 남깁니다.
        nickname = data.get('properties', {}).get('nickname')
        # user.name이 없을 수도 있으므로 getattr를 사용하여 안전하게 접근합니다.
        if nickname and not getattr(user, 'name', None):
            user_field(user, 'name', nickname)

        return user
