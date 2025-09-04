# config/settings.py

from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
TOUR_API_SERVICE_KEY = os.getenv('TOUR_API_SERVICE_KEY')
KAKAO_API_KEY = os.getenv('KAKAO_API_KEY')
DAUM_API_KEY = os.getenv('DAUM_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

SOCIALACCOUNT_PROVIDERS = {
    'kakao': {
        'VERIFIED_EMAIL': True
    }
}
SOCIALACCOUNT_LOGIN_ON_GET = True

DEBUG = True
allowed_hosts_str = os.getenv('ALLOWED_HOSTS')
if allowed_hosts_str:
    ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',')]
else:
    ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.kakao',
    'users.apps.LogInConfig',
    'tour_api.apps.TourApiConfig',
    'ai.apps.AiConfig',
    # --- 개인정보처리방침 페이지를 위해 추가한 앱 ---
    'pages.apps.PagesConfig',
]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'

SOCIALACCOUNT_ADAPTER = 'users.adapter.CustomSocialAccountAdapter'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_EMAIL = True

REST_USE_JWT = True

REST_AUTH = {
    'REGISTER_SERIALIZER': 'users.serializers.RegisterSerializer',
    'USER_DETAILS_SERIALIZER': 'users.serializers.UserSerializer',
    'LOGIN_SERIALIZER': 'users.serializers.CustomLoginSerializer',
    'SOCIAL_LOGIN_SERIALIZER': 'users.serializers.CustomSocialLoginSerializer', # ### 이 줄을 추가합니다! ###
    'SESSION_LOGIN': False,
    'USE_JWT': True,
    'JWT_AUTH_HTTPONLY': False,
    'JWT_SERIALIZER': 'users.serializers.CustomJWTSerializer',
}

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

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
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

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'KST'
USE_I18N = True
TIME_ZONE = 'Asia/Seoul'
USE_TZ = False 
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static',]
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SITE_ID = 1
