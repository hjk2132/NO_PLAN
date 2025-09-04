# users/admin.py

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from .models import LocationUsageLog # LocationUsageLog 모델 import

# LogEntry 모델을 관리자 페이지에 등록
@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag')
    list_filter = ('action_flag', 'content_type')
    search_fields = ('user__username', 'object_repr')

### ▼▼▼ 취급대장 관리자 페이지 설정 추가 ▼▼▼ ###
@admin.register(LocationUsageLog)
class LocationUsageLogAdmin(admin.ModelAdmin):
    # 관리자 페이지 목록에 표시될 필드를 지정합니다.
    list_display = (
        'get_user_email', 
        'acquisition_path', 
        'provided_service', 
        'recipient', 
        'usage_timestamp'
    )
    
    # 필터 기능을 추가하여 특정 서비스나 경로로 쉽게 찾아볼 수 있습니다.
    list_filter = ('provided_service', 'acquisition_path')
    
    # 검색 기능을 추가하여 특정 사용자의 이메일로 기록을 검색할 수 있습니다.
    search_fields = ('user__email',)

    # user 객체 대신 이메일 주소를 표시하기 위한 헬퍼 메소드입니다.
    def get_user_email(self, obj):
        return obj.user.email if obj.user else '알 수 없음'
    
    get_user_email.short_description = '대상 (이메일)' # 컬럼 제목 설정
