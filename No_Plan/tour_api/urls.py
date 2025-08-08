from django.urls import path
from .views import RestaurantListView, CafeListView, TouristAttractionListView, AccommodationListView, TourDetailView, TripSummaryView

urlpatterns = [
    # 식당 조회 API
    path('restaurants/', RestaurantListView.as_view(), name='restaurant-list'),

    # 카페 조회 API
    path('cafes/', CafeListView.as_view(), name='cafe-list'),

    # 관광지 조회 API
    path('attractions/', TouristAttractionListView.as_view(), name='attraction-list'),

    # 숙소 조회 API
    path('accommodations/', AccommodationListView.as_view(), name='accommodation-list'),

    # contentId 기반 장소 조회 API
    path('detail/<int:content_id>/', TourDetailView.as_view(), name='tour-detail'),

    # 여행 요약 생성 API
    path('trips/<int:trip_id>/summarize/', TripSummaryView.as_view(), name='trip-summary'),
]
