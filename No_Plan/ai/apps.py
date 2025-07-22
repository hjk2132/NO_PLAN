# ai/apps.py
from django.apps import AppConfig

class AiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai'

    def ready(self):
        # Django 앱이 시작될 때 app_clients 모듈을 로드하여
        # 공유 클라이언트 객체들을 초기화합니다.
        from . import app_clients