# tour_api/views.py

import aiohttp
import asyncio
import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import ssl
import json
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from urllib3 import poolmanager
import time  # <<< 시간 측정을 위해 time 모듈 임포트

from ai.services import BlogCrawler, RecommendationEngine


# ===================================================================
# 커스텀 비동기 APIView 클래스 정의 (이전과 동일)
# ===================================================================
class AsyncAPIView(APIView):
    async def dispatch(self, request, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers
        try:
            self.initial(request, *args, **kwargs)
            if request.method.lower() in self.http_method_names:
                handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed
            response = await handler(request, *args, **kwargs)
        except Exception as exc:
            response = self.handle_exception(exc)
        self.response = self.finalize_response(request, response, *args, **kwargs)
        return self.response


# ===================================================================
# 공통 헬퍼 함수 (디버깅 출력 추가)
# ===================================================================

async def get_ai_recommendations(places: list, adjectives: list) -> list:
    # <<< 디버깅 출력 추가 시작
    print("\n==============[AI 추천 파이프라인 시작]===============")
    total_start_time = time.time()
    # >>> 디버깅 출력 추가 끝

    if not places or not adjectives:
        return places

    place_infos_with_id = [(p['contentid'], p['title'], p.get('addr1', '')) for p in places]

    crawler = BlogCrawler()
    recomm_engine = RecommendationEngine()

    # <<< 디버깅 출력 추가 시작
    t1 = time.time()
    # >>> 디버깅 출력 추가 끝
    crawling_df = await crawler.crawl_all(place_infos_with_id)
    # <<< 디버깅 출력 추가 시작
    t2 = time.time()
    print(f"  [1/4] 블로그 크롤링 완료: {t2 - t1:.2f} 초")
    # >>> 디버깅 출력 추가 끝

    if crawling_df.empty or crawling_df['텍스트'].str.strip().eq('').all():
        return places

    # <<< 디버깅 출력 추가 시작
    t3 = time.time()
    # >>> 디버깅 출력 추가 끝
    texts_to_embed = crawling_df[crawling_df['텍스트'].str.strip().ne('')]
    if not texts_to_embed.empty:
        embeddings = recomm_engine.get_embedding(texts_to_embed['텍스트'].tolist())
        crawling_df['embedding'] = None
        crawling_df.loc[texts_to_embed.index, 'embedding'] = pd.Series(embeddings, index=texts_to_embed.index)
    # <<< 디버깅 출력 추가 시작
    t4 = time.time()
    print(f"  [2/4] 텍스트 임베딩 생성 완료: {t4 - t3:.2f} 초")
    # >>> 디버깅 출력 추가 끝

    # <<< 디버깅 출력 추가 시작
    t5 = time.time()
    # >>> 디버깅 출력 추가 끝
    df_embed = crawling_df.dropna(subset=['embedding'])
    if not df_embed.empty:
        query = recomm_engine.adjectives_to_query(adjectives)
        query_emb = recomm_engine.get_query_embedding(query)
        matrix = df_embed["embedding"].tolist()
        sims = cosine_similarity([query_emb], matrix)[0]
        crawling_df.loc[df_embed.index, 'similarity'] = sims
    # <<< 디버깅 출력 추가 시작
    t6 = time.time()
    print(f"  [3/4] 유사도 계산 완료: {t6 - t5:.2f} 초")
    # >>> 디버깅 출력 추가 끝

    # <<< 디버깅 출력 추가 시작
    t7 = time.time()
    # >>> 디버깅 출력 추가 끝
    top_30_df = crawling_df.sort_values(by="similarity", ascending=False).head(30)
    if not top_30_df.empty:
        result_df = await recomm_engine.add_reasons_and_hashtags(top_30_df, adjectives)
        crawling_df = crawling_df.merge(result_df[['contentid', '추천이유', '해시태그']], on='contentid', how='left')
    # <<< 디버깅 출력 추가 시작
    t8 = time.time()
    print(f"  [4/4] 추천 이유/해시태그 생성 완료: {t8 - t7:.2f} 초")
    # >>> 디버깅 출력 추가 끝

    crawling_df = crawling_df.replace({np.nan: None})

    original_place_map = {p['contentid']: p for p in places}
    for _, row in crawling_df.iterrows():
        contentid = row['contentid']
        if contentid in original_place_map:
            original_place_map[contentid]['similarity'] = row.get('similarity')
            original_place_map[contentid]['recommend_reason'] = row.get('추천이유')
            original_place_map[contentid]['hashtags'] = row.get('해시태그')

    sorted_places = sorted(
        original_place_map.values(),
        key=lambda p: p.get('similarity') if p.get('similarity') is not None else -1.0,
        reverse=True
    )

    # <<< 디버깅 출력 추가 시작
    total_end_time = time.time()
    print(f"[AI 추천 파이프라인 종료] 총 소요 시간: {total_end_time - total_start_time:.2f} 초")
    print("\n======================================================\n")
    # >>> 디버깅 출력 추가 끝

    return sorted_places


# ===================================================================
# 나머지 코드는 이전과 동일
# ===================================================================

ssl_context = ssl.create_default_context()
ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')


async def fetch_from_tour_api(session: aiohttp.ClientSession, params: dict):
    base_url = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2"
    default_params = {'serviceKey': settings.TOUR_API_SERVICE_KEY, 'MobileOS': 'ETC', 'MobileApp': 'MyTourApp',
                      '_type': 'json'}
    request_params = {**default_params, **params}
    try:
        async with session.get(base_url, params=request_params, ssl=ssl_context, timeout=10) as response:
            response.raise_for_status()
            data = await response.json()
            if data.get('response', {}).get('body', {}).get('items') == '': return []
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            return [items] if isinstance(items, dict) else items
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
        print(f"API 요청 실패: {e}")
        return []


async def fetch_restaurants_from_tour_api(session, params):
    restaurant_params = {'contentTypeId': '39', 'cat1': 'A05', 'cat2': 'A0502', **params}
    return await fetch_from_tour_api(session, restaurant_params)


async def fetch_attractions_from_tour_api(session, params):
    return await fetch_from_tour_api(session, params)


class RestaurantListView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')
        adjectives_str = request.query_params.get('adjectives')
        if not map_x or not map_y:
            return Response({"error": "mapX, mapY는 필수 파라미터입니다."}, status=status.HTTP_400_BAD_REQUEST)
        food_categories = ['A05020100', 'A05020200', 'A05020300', 'A05020400', 'A05020700']
        base_params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'numOfRows': '30'}
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_restaurants_from_tour_api(session, {**base_params, 'cat3': cat}) for cat in food_categories]
            results = await asyncio.gather(*tasks)
        all_restaurants = [item for sublist in results for item in sublist]
        unique_restaurants = list({p['contentid']: p for p in all_restaurants}.values())
        if adjectives_str:
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(unique_restaurants, adjectives)
            return Response(final_results, status=status.HTTP_200_OK)
        else:
            sorted_restaurants = sorted(unique_restaurants, key=lambda x: float(x.get('dist', 0)))
            return Response(sorted_restaurants, status=status.HTTP_200_OK)


class CafeListView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')
        adjectives_str = request.query_params.get('adjectives')
        if not map_x or not map_y:
            return Response({"error": "mapX, mapY는 필수 파라미터입니다."}, status=status.HTTP_400_BAD_REQUEST)
        params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'cat3': 'A05020900', 'numOfRows': '30'}
        async with aiohttp.ClientSession() as session:
            cafes = await fetch_restaurants_from_tour_api(session, params)
        if adjectives_str:
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(cafes, adjectives)
            return Response(final_results, status=status.HTTP_200_OK)
        else:
            sorted_cafes = sorted(cafes, key=lambda x: float(x.get('dist', 0)))
            return Response(sorted_cafes, status=status.HTTP_200_OK)


class TouristAttractionListView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')
        adjectives_str = request.query_params.get('adjectives')
        if not map_x or not map_y:
            return Response({"error": "mapX, mapY는 필수 파라미터입니다."}, status=status.HTTP_400_BAD_REQUEST)
        params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'contentTypeId': '12', 'numOfRows': '30'}
        async with aiohttp.ClientSession() as session:
            attractions = await fetch_attractions_from_tour_api(session, params)
        if adjectives_str:
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(attractions, adjectives)
            return Response(final_results, status=status.HTTP_200_OK)
        else:
            sorted_attractions = sorted(attractions, key=lambda x: float(x.get('dist', 0)))
            return Response(sorted_attractions, status=status.HTTP_200_OK)


class AccommodationListView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        map_x = request.query_params.get('mapX')
        map_y = request.query_params.get('mapY')
        radius = request.query_params.get('radius', '5000')
        adjectives_str = request.query_params.get('adjectives')
        if not map_x or not map_y:
            return Response({"error": "mapX, mapY는 필수 파라미터입니다."}, status=status.HTTP_400_BAD_REQUEST)
        params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'contentTypeId': '32', 'numOfRows': '30'}
        async with aiohttp.ClientSession() as session:
            accommodations = await fetch_attractions_from_tour_api(session, params)
        if adjectives_str:
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(accommodations, adjectives)
            return Response(final_results, status=status.HTTP_200_OK)
        else:
            sorted_accommodations = sorted(accommodations, key=lambda x: float(x.get('dist', 0)))
            return Response(sorted_accommodations, status=status.HTTP_200_OK)


class TlsAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        self.poolmanager = poolmanager.PoolManager(num_pools=connections, maxsize=maxsize, block=block,
                                                   ssl_version=ssl.PROTOCOL_TLS, ssl_context=ctx)


def fetch_detail_from_tour_api_sync(content_id):
    base_url = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
    default_params = {'serviceKey': settings.TOUR_API_SERVICE_KEY, 'MobileOS': 'ETC', 'MobileApp': 'MyTourApp',
                      '_type': 'json', 'contentId': content_id}
    session = requests.Session()
    session.mount('https://', TlsAdapter())
    try:
        response = session.get(base_url, params=default_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('response', {}).get('body', {}).get('items') == '': return None
        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        return items[0] if items else None
    except (json.JSONDecodeError, requests.exceptions.RequestException) as e:
        print(f"API 요청 실패: {e}")
        return None


class TourDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, content_id):
        if not content_id:
            return Response({"error": "contentId가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        detail_data = fetch_detail_from_tour_api_sync(content_id)
        if detail_data:
            return Response(detail_data, status=status.HTTP_200_OK)
        else:
            return Response({"error": "해당 contentId에 대한 정보를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)