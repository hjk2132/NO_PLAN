# tour_api/views.py

import requests
import concurrent.futures
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import ssl
from urllib3 import poolmanager
import json


# SSL/TLS 호환성 어댑터
class TlsAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        self.poolmanager = poolmanager.PoolManager(
            num_pools=connections, maxsize=maxsize, block=block,
            ssl_version=ssl.PROTOCOL_TLS, ssl_context=ctx)


# ===================================================================
# TourAPI 기반 주변 음식점 정보 조회
# ===================================================================

def fetch_restaurants_from_tour_api(params):
    base_url = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2"

    default_params = {
        'serviceKey': settings.TOUR_API_SERVICE_KEY,
        'MobileOS': 'ETC',
        'MobileApp': 'MyTourApp',
        '_type': 'json',
        'contentTypeId': '39',
        'cat1': 'A05',
        'cat2': 'A0502'
    }

    request_params = {**default_params, **params}
    session = requests.Session()
    session.mount('https://', TlsAdapter())

    try:
        response = session.get(base_url, params=request_params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('body', {}).get('items') == '':
            return []

        return data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

    except json.JSONDecodeError:
        print(f"JSON 파싱 실패. 서버 응답: {response.text}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"API 요청 실패: {e}")
        return []


# RestaurantListView는 변경할 필요가 없습니다.
class RestaurantListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')

        if not map_x or not map_y:
            return Response(
                {"error": "mapX (경도)와 mapY (위도)는 필수 파라미터입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        food_categories = {
            'korean': 'A05020100', 'western': 'A05020200',
            'japanese': 'A05020300', 'chinese': 'A05020400',
            'unique': 'A05020700',
        }
        all_restaurants = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_category = {
                executor.submit(
                    fetch_restaurants_from_tour_api,
                    {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'cat3': cat_code}
                ): category for category, cat_code in food_categories.items()
            }
            for future in concurrent.futures.as_completed(future_to_category):
                try:
                    restaurants = future.result()
                    # ★★★ API 응답 형식이 리스트가 아닐 수 있으므로 안전장치 추가 ★★★
                    if isinstance(restaurants, list):
                        all_restaurants.extend(restaurants)
                    elif isinstance(restaurants, dict):
                        # API가 결과가 1개일 때 리스트가 아닌 딕셔너리를 주는 경우
                        all_restaurants.append(restaurants)
                except Exception as e:
                    category_name = future_to_category[future]
                    print(f"{category_name} 카테고리 조회 중 에러 발생: {e}")

        unique_restaurants = {item['contentid']: item for item in all_restaurants}.values()
        # API에서 거리순 정렬을 못해주므로, 코드에서 직접 정렬합니다.
        sorted_restaurants = sorted(list(unique_restaurants), key=lambda x: float(x.get('dist', 0)))
        return Response(sorted_restaurants, status=status.HTTP_200_OK)


# ===================================================================
# TourAPI 기반 주변 카페 정보 조회
# ===================================================================
class CafeListView(APIView):
    """
    사용자 주변의 카페 목록을 TourAPI에서 조회하여 반환하는 API
    """
    permission_classes = [AllowAny]  # 누구나 접근 가능

    def get(self, request):
        # 1. 쿼리 파라미터에서 위도(mapY), 경도(mapX), 반경(radius) 값 가져오기
        # 이 로직은 RestaurantListView와 완전히 동일합니다.
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')  # 기본값 5km

        if not map_x or not map_y:
            return Response(
                {"error": "mapX (경도)와 mapY (위도)는 필수 파라미터입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 조회할 카페 카테고리 코드 정의
        cafe_category_code = 'A05020900'

        # 3. 기존 함수를 사용하여 API 호출
        # 여러 개를 호출할 필요가 없으므로 병렬 처리 로직은 필요 없습니다.
        params = {
            'mapX': map_x,
            'mapY': map_y,
            'radius': radius,
            'cat3': cafe_category_code
        }
        cafes = fetch_restaurants_from_tour_api(params)

        # 4. TourAPI가 결과가 1개일 때 리스트가 아닌 딕셔너리를 반환하는 경우에 대비
        all_cafes = []
        if isinstance(cafes, list):
            all_cafes = cafes
        elif isinstance(cafes, dict):
            all_cafes.append(cafes)

        # 5. 거리(dist) 순으로 최종 정렬
        sorted_cafes = sorted(all_cafes, key=lambda x: float(x.get('dist', 0)))

        return Response(sorted_cafes, status=status.HTTP_200_OK)


# ===================================================================
# TourAPI 기반 주변 관광지 정보 조회
# ===================================================================

def fetch_attractions_from_tour_api(params):
    """
    관광지 정보 조회를 위해 TourAPI를 호출하는 새로운 함수
    """
    base_url = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2"

    default_params = {
        'serviceKey': settings.TOUR_API_SERVICE_KEY,
        'MobileOS': 'ETC',
        'MobileApp': 'MyTourApp',
        '_type': 'json'
        # 음식점과 달리 contentTypeId, cat1, cat2를 기본값으로 두지 않습니다.
    }

    request_params = {**default_params, **params}
    session = requests.Session()
    session.mount('https://', TlsAdapter())

    try:
        response = session.get(base_url, params=request_params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('body', {}).get('items') == '':
            return []

        return data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

    except json.JSONDecodeError:
        print(f"JSON 파싱 실패. 서버 응답: {response.text}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"API 요청 실패: {e}")
        return []


class TouristAttractionListView(APIView):
    """
    사용자 주변의 관광지 목록을 TourAPI에서 조회하여 반환하는 API
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # 1. 쿼리 파라미터에서 위도(mapY), 경도(mapX), 반경(radius) 값 가져오기
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')  # 기본값 5km

        if not map_x or not map_y:
            return Response(
                {"error": "mapX (경도)와 mapY (위도)는 필수 파라미터입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. TourAPI 호출을 위한 파라미터 설정
        params = {
            'mapX': map_x,
            'mapY': map_y,
            'radius': radius,
            'contentTypeId': '12',  # 관광지 타입 ID
            'numOfRows': '30'  # 최대 30개 결과 요청
        }

        # 3. 위에서 새로 만든 함수를 사용하여 API 호출
        attractions = fetch_attractions_from_tour_api(params)

        # 4. TourAPI가 결과가 1개일 때 리스트가 아닌 딕셔너리를 반환하는 경우에 대비
        all_attractions = []
        if isinstance(attractions, list):
            all_attractions = attractions
        elif isinstance(attractions, dict):
            all_attractions.append(attractions)

        # 5. 거리(dist) 순으로 최종 정렬
        sorted_attractions = sorted(all_attractions, key=lambda x: float(x.get('dist', 0)))

        return Response(sorted_attractions, status=status.HTTP_200_OK)


# ===================================================================
# TourAPI 기반 주변 숙소 정보 조회
# ===================================================================

def fetch_accommodations_from_tour_api(params):
    """
    숙소 정보 조회를 위해 TourAPI를 호출하는 새로운 함수
    """
    base_url = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2"

    default_params = {
        'serviceKey': settings.TOUR_API_SERVICE_KEY,
        'MobileOS': 'ETC',
        'MobileApp': 'MyTourApp',
        '_type': 'json'
    }

    request_params = {**default_params, **params}
    session = requests.Session()
    session.mount('https://', TlsAdapter())

    try:
        response = session.get(base_url, params=request_params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('body', {}).get('items') == '':
            return []

        return data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

    except json.JSONDecodeError:
        print(f"JSON 파싱 실패. 서버 응답: {response.text}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"API 요청 실패: {e}")
        return []


class AccommodationListView(APIView):
    """
    사용자 주변의 숙소 목록을 TourAPI에서 조회하여 반환하는 API
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # 1. 쿼리 파라미터에서 위도(mapY), 경도(mapX), 반경(radius) 값 가져오기
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')  # 기본값 5km

        if not map_x or not map_y:
            return Response(
                {"error": "mapX (경도)와 mapY (위도)는 필수 파라미터입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. TourAPI 호출을 위한 파라미터 설정
        params = {
            'mapX': map_x,
            'mapY': map_y,
            'radius': radius,
            'contentTypeId': '32',  # 숙박 타입 ID
            'numOfRows': '30'  # 최대 30개 결과 요청
        }

        # 3. 위에서 새로 만든 함수를 사용하여 API 호출
        accommodations = fetch_accommodations_from_tour_api(params)

        # 4. TourAPI가 결과가 1개일 때 리스트가 아닌 딕셔너리를 반환하는 경우에 대비
        all_accommodations = []
        if isinstance(accommodations, list):
            all_accommodations = accommodations
        elif isinstance(accommodations, dict):
            all_accommodations.append(accommodations)

        # 5. 거리(dist) 순으로 최종 정렬
        sorted_accommodations = sorted(all_accommodations, key=lambda x: float(x.get('dist', 0)))

        return Response(sorted_accommodations, status=status.HTTP_200_OK)


# ===================================================================
# TourAPI 기반 상세 정보 조회 (contentId 기반)
# ===================================================================

def fetch_detail_from_tour_api(content_id):
    """
    contentId를 기반으로 상세 정보를 조회하기 위해 TourAPI (detailCommon2)를 호출하는 함수
    """
    base_url = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"

    default_params = {
        'serviceKey': settings.TOUR_API_SERVICE_KEY,
        'MobileOS': 'ETC',
        'MobileApp': 'MyTourApp',
        '_type': 'json',
        'contentId': content_id
    }

    session = requests.Session()
    session.mount('https://', TlsAdapter())

    try:
        # 이 API는 파라미터가 적으므로 default_params를 바로 사용합니다.
        response = session.get(base_url, params=default_params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('body', {}).get('items') == '':
            return None

        # 상세 정보는 항상 아이템이 하나이므로, 리스트의 첫 번째 요소를 반환
        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        return items[0] if items else None

    except json.JSONDecodeError:
        print(f"JSON 파싱 실패. 서버 응답: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API 요청 실패: {e}")
        return None


class TourDetailView(APIView):
    """
    contentId를 경로 파라미터로 받아 해당 장소의 상세 정보를 반환하는 API
    """
    permission_classes = [AllowAny]

    def get(self, request, content_id):
        # 1. URL 경로에서 content_id를 직접 받습니다.
        if not content_id:
            return Response(
                {"error": "contentId가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 위에서 새로 만든 함수를 사용하여 API 호출
        detail_data = fetch_detail_from_tour_api(content_id)

        # 3. 조회 결과에 따라 응답 처리
        if detail_data:
            # 성공적으로 데이터를 가져왔으면 그대로 반환
            return Response(detail_data, status=status.HTTP_200_OK)
        else:
            # 데이터를 찾지 못했거나 오류가 발생한 경우
            return Response(
                {"error": "해당 contentId에 대한 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND
            )