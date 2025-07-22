from pathlib import Path
from dotenv import load_dotenv
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# .env 파일 로드
load_dotenv(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

#Tour API KEY
TOUR_API_SERVICE_KEY = os.getenv('TOUR_API_SERVICE_KEY')

# 카카오 API KEY (REST형, 모바일은 다른 키 필요)
KAKAO_API_KEY = os.getenv('KAKAO_API_KEY')

# Daum Blog 검색을 위한 Kakao REST API KEY
DAUM_API_KEY = os.getenv('DAUM_API_KEY')

# OpenAI API 키
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# 카카오 소셜 로그인 설정
SOCIALACCOUNT_PROVIDERS = {
    'kakao': {
        'APP': {
            'client_id': os.getenv(KAKAO_API_KEY),
            'secret': '',
            'key': ''
        }
    }
}

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
allowed_hosts_str = os.getenv('ALLOWED_HOSTS')
if allowed_hosts_str:
    # .env 파일에서 가져온 문자열을 쉼표로 쪼개고, 각 항목의 공백을 제거하여 리스트로 만듭니다.
    ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',')]
else:
    # .env 파일에 ALLOWED_HOSTS가 정의되지 않았을 경우를 대비한 기본값
    ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    #기본 apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    #3rd Party Apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',

    #3rd Party Apps for Kakao Social Log-in
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.kakao',

    #user apps
    'users.apps.LogInConfig',
    'tour_api.apps.TourApiConfig',
    'ai.apps.AiConfig',
]

AUTHENTICATION_BACKENDS = (
    # Django의 기본 인증 백엔드 (username/password)
    'django.contrib.auth.backends.ModelBackend',
    # allauth의 소셜 계정 인증
    'allauth.account.auth_backends.AuthenticationBackend',
)

# ===================================================================
# dj-rest-auth 및 allauth 관련 설정
# ===================================================================

# 1. 로그인 시 사용할 주된 식별자 방식
# 'email' 또는 'username' 중 선택할 수 있으며, 여러 개를 넣을 수도 있음
ACCOUNT_LOGIN_METHODS = ['email']

# 2. 회원가입 시 받을 필드 지정 (신식)
# 'email'만 포함하여 이메일 필수를 강제하고, username은 폼에서 받지 않음
ACCOUNT_SIGNUP_FIELDS = ['email']

# 3. 이메일 인증 절차는 사용하지 않음
ACCOUNT_EMAIL_VERIFICATION = 'none'

# 4. 소셜 로그인 시 사용할 커스텀 어댑터 경로 지정
SOCIALACCOUNT_ADAPTER = 'users.adapter.CustomSocialAccountAdapter'

# 5. dj-rest-auth가 JWT를 사용하도록 설정
REST_USE_JWT = True

# 6. dj-rest-auth의 세부 설정
REST_AUTH = {
    'REGISTER_SERIALIZER': 'users.serializers.RegisterSerializer',
    'USER_DETAILS_SERIALIZER': 'users.serializers.UserSerializer',

    'LOGIN_SERIALIZER': 'users.serializers.CustomLoginSerializer',
    #'TOKEN_SERIALIZER': 'users.serializers.CustomJWTSerializer',
    #'JWT_SERIALIZER': 'users.serializers.CustomJWTSerializer',

    # 세션 로그인 사용 안 함
    'SESSION_LOGIN': False,
    # JWT 토큰 쿠키 사용 안 함
    'USE_JWT': True,
    # 응답에 JWT 토큰 포함
    'JWT_AUTH_HTTPONLY': False,
}

# 만든 User 모델을 기본 사용자로 지정
AUTH_USER_MODEL = 'users.User'
ROOT_URLCONF = 'config.urls'

WSGI_APPLICATION = 'config.wsgi.application'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

# ===================================================================
# 템플릿 설정 (수정된 부분)
# ===================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # DIRS에 프로젝트 최상위의 templates 폴더 경로를 추가합니다.
        # 이렇게 해야 우리가 만든 templates/rest_framework/api.html을 찾을 수 있습니다.
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER' : os.getenv('DB_USER'),
        'PASSWORD' : os.getenv('DB_PASSWORD'),
        'HOST' : os.getenv('DB_HOST'),
        'PORT' : os.getenv('DB_PORT'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset' : 'utf8mb4',
        }
    }
}

# Rest_Framework
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    }, {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    }, {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    }, {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SITE_ID = 1