# users/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class User(AbstractUser):
    first_name = None
    last_name = None

    # name 필드를 NULL 허용으로 변경
    name = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        verbose_name='이름'
    )

class UserInfo(models.Model):
    # 성별 선택을 위한 상수 정의
    MALE = 'M'
    FEMALE = 'F'
    OTHER = 'O'
    GENDER_CHOICES = [
        (MALE, '남성'),
        (FEMALE, '여성'),
        (OTHER, '기타'),
    ]

    # 1:1 관계 설정 (기본 키 및 외래 키)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name='사용자'
    )

    # 이름 필드 (필수)
    # User 모델의 name 필드와 동기화될 필드
    name = models.CharField(max_length=150, verbose_name='이름')

    # 나이 필드 (필수)
    # null=True, blank=True 옵션을 제거하여 필수 입력 항목으로 만듦.
    age = models.PositiveSmallIntegerField(verbose_name='나이')

    # 성별 필드 (필수)
    # null=True, blank=True 옵션을 제거하여 필수 입력 항목으로 만듦.
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        verbose_name='성별'
    )

    def __str__(self):
        return f"{self.name}님의 추가 정보"

    class Meta:
        db_table = 'users_userinfo'
        verbose_name = '사용자 추가 정보'
        verbose_name_plural = '사용자 추가 정보 목록'

class Trip(models.Model):
    """
    사용자의 여행 정보를 저장하는 모델.
    한 명의 사용자는 여러 개의 여행 정보를 가질 수 있습니다. (User:Trip = 1:N)
    """
    # 기본 키(id)는 Django가 자동으로 생성해주는 auto-increment 정수 필드를 사용합니다.

    # 사용자 외래 키
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trips',  # user.trips.all() 형태로 조회 가능
        verbose_name='사용자'
    )

    # 지역명
    region = models.CharField(
        max_length=100,
        verbose_name='지역명'
    )

    # 생성 시각
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='생성 시각'
    )

    # 대중교통
    transportation = models.CharField(
        max_length=100,
        blank=True, null=True,  # 기존 데이터가 있으므로 NULL 허용
        verbose_name='이동수단'
    )

    # 동행자
    companion = models.CharField(
        max_length=100,
        blank=True, null=True,  # 기존 데이터가 있으므로 NULL 허용
        verbose_name='동행자'
    )

    # 형용사
    adjectives = models.TextField(
        blank=True,
        null=True,
        verbose_name='선택한 형용사'
    )

    # AI 요약
    summary = models.TextField(
        blank=True,
        null=True,
        verbose_name='AI 여행 요약'
    ) 

    def __str__(self):
        # Admin 페이지 등에서 객체를 쉽게 식별할 수 있도록 문자열 표현을 정의합니다.
        return f"{self.user.username}의 {self.region} 여행"

    class Meta:
        db_table = 'users_trip'  # 데이터베이스 테이블 이름 지정
        verbose_name = '여행 정보'
        verbose_name_plural = '여행 정보 목록'
        ordering = ['-created_at'] # 최신순으로 정렬


class VisitedContent(models.Model):
    """
    사용자가 특정 여행에서 방문한 장소(콘텐츠) 정보를 저장하는 모델.
    """
    # 기본 키(id): Django가 자동으로 auto-increment 정수 필드를 생성합니다.

    # 사용자 외래 키: 어떤 사용자가 저장했는지 식별
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='사용자'
    )

    # 여행 외래 키: 어떤 여행에 속한 방문 기록인지 식별
    trip = models.ForeignKey(
        'Trip',  # 문자열로 모델 이름을 지정하면 순환 참조 에러를 방지할 수 있습니다.
        on_delete=models.CASCADE,
        verbose_name='여행'
    )

    # 방문지 고유 ID (외부 API의 ID 등)
    content_id = models.IntegerField(verbose_name='콘텐츠 ID')

    # 방문지 이름
    title = models.CharField(max_length=200, verbose_name='방문지 이름')

    # 대표 이미지 URL
    first_image = models.URLField(max_length=512, blank=True, null=True, verbose_name='대표 이미지 URL')

    # 주소
    addr1 = models.CharField(max_length=255, blank=True, null=True, verbose_name='주소')

    # 경도 (Longitude)
    mapx = models.DecimalField(max_digits=30, decimal_places=20, verbose_name='경도')

    # 위도 (Latitude)
    mapy = models.DecimalField(max_digits=30, decimal_places=20, verbose_name='위도')

    # 개요/설명
    overview = models.TextField(blank=True, null=True, verbose_name='개요')

    # 저장 시각 (row 생성 시각)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='저장 시각')

    # 해시태그
    hashtags = models.TextField(
        blank=True, null=True,
        verbose_name='해시태그'
    )

    # 추천이유
    recommend_reason = models.TextField(
        blank=True, null=True,
        verbose_name='추천이유'
    ) 

    def __str__(self):
        return f"[{self.trip.region}] {self.title} (사용자: {self.user.username})"

    class Meta:
        db_table = 'users_visited_content'
        verbose_name = '방문한 여행 콘텐츠'
        verbose_name_plural = '방문한 여행 콘텐츠 목록'
        ordering = ['-created_at']  # 최신순으로 정렬

class Bookmark(models.Model):
    """
    사용자가 북마크한 장소(콘텐츠) 정보를 저장하는 모델.
    한 명의 사용자는 여러 개의 북마크를 가질 수 있습니다. (User:Bookmark = 1:N)
    """
    # 기본 키(id)는 Django가 자동으로 생성해주는 auto-increment 정수 필드를 사용합니다.

    # 사용자 외래 키
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookmarks',  # user.bookmarks.all() 형태로 조회 가능
        verbose_name='사용자'
    )

    # 방문지 고유 ID (외부 API의 ID 등)
    content_id = models.IntegerField(verbose_name='콘텐츠 ID')

    # 방문지 이름
    title = models.CharField(max_length=200, verbose_name='방문지 이름')

    # 대표 이미지 URL (이미지가 없을 수도 있으므로 null/blank 허용)
    first_image = models.URLField(max_length=512, blank=True, null=True, verbose_name='대표 이미지 URL')

    # 주소 (주소가 없을 수도 있으므로 null/blank 허용)
    addr1 = models.CharField(max_length=255, blank=True, null=True, verbose_name='주소')

    # 개요/설명 (설명이 없을 수도 있으므로 null/blank 허용)
    overview = models.TextField(blank=True, null=True, verbose_name='개요')

    # 북마크 생성 시각 (자동으로 현재 시각 저장)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='북마크 생성 시각')

    # 해시태그
    hashtags = models.TextField(
        blank=True, null=True,
        verbose_name='해시태그'
    )

    # 추천이유
    recommend_reason = models.TextField(
        blank=True, null=True,
        verbose_name='추천이유'
    ) 

    def __str__(self):
        # Admin 페이지 등에서 객체를 쉽게 식별할 수 있도록 문자열 표현을 정의합니다.
        return f"{self.user.username}의 북마크: {self.title}"

    class Meta:
        db_table = 'users_bookmark'  # 데이터베이스 테이블 이름 지정
        verbose_name = '북마크'
        verbose_name_plural = '북마크 목록'
        ordering = ['-created_at']  # 최신순으로 정렬
        # 한 사용자가 동일한 content_id를 중복해서 북마크하는 것을 방지
        unique_together = ('user', 'content_id')
