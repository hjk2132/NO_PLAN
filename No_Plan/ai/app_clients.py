# ai/app_clients.py
from .services import BlogCrawler, RecommendationEngine

# Django 앱이 로드될 때 단 한 번만 객체를 생성합니다.
blog_crawler = BlogCrawler()
recommendation_engine = RecommendationEngine()