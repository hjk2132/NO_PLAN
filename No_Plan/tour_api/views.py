# tour_api/views.py

import aiohttp
import asyncio
import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
import ssl
import json
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from urllib3 import poolmanager
import time
from asgiref.sync import sync_to_async
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist

import livepopulartimes

from ai.services import BlogCrawler, RecommendationEngine
from users.models import Trip, VisitedContent


# ===================================================================
# 08.08 AsyncAPIView의 dispatch 메소드 수정
# ===================================================================
class AsyncAPIView(APIView):
    async def dispatch(self, request, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers
        try:
            # 동기적으로 실행되는 initial 메소드를 sync_to_async로 감싸서 호출합니다.
            # 이 부분이 인증(authentication)과 권한(permission) 체크를 포함합니다.
            # thread_sensitive=True는 Django의 데이터베이스 연결을 안전하게 처리하기 위한 권장 옵션입니다.
            await sync_to_async(self.initial, thread_sensitive=True)(request, *args, **kwargs)

            if request.method.lower() in self.http_method_names:
                handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed
            response = await handler(request, *args, **kwargs)

        except Exception as exc:
            response = self.handle_exception(exc)
        self.response = self.finalize_response(request, response, *args, **kwargs)
        return self.response


async def get_populartimes_async(place_title: str, place_address: str):
    if not place_address:
        return None
    try:
        formatted_query = f"{place_title}, {place_address}"
        data = await asyncio.to_thread(
            livepopulartimes.get_populartimes_by_address,
            formatted_query
        )
        if data and data.get('popular_times'):
            return data
        return None
    except Exception as e:
        print(f"'{place_title}' 혼잡도 조회 중 오류 발생: {e}")
        return None


async def get_ai_recommendations(places: list, adjectives: list, place_type: str) -> list:
    print("\n==============[AI 추천 파이프라인 시작]===============")
    total_start_time = time.time()
    if not places or not adjectives:
        return places
    place_infos_with_id = [(p['contentid'], p['title'], p.get('addr1', '')) for p in places]

    async with RecommendationEngine() as recomm_engine:
        crawler = BlogCrawler()
        query = recomm_engine.adjectives_to_query(adjectives)
        crawl_task = crawler.crawl_all(place_infos_with_id)
        query_emb_task = recomm_engine.get_query_embedding(query)
        populartimes_tasks = [get_populartimes_async(p['title'], p.get('addr1', '')) for p in places]

        t1 = time.time()
        all_results = await asyncio.gather(
            crawl_task,
            query_emb_task,
            *populartimes_tasks
        )
        crawling_df = all_results[0]
        query_emb = all_results[1]
        populartimes_results = all_results[2:]
        t2 = time.time()
        print(f"  [1/4] 블로그 크롤링, 쿼리 임베딩, 혼잡도 조회 동시 완료: {t2 - t1:.2f} 초 ({len(places)}개 중 {len(crawling_df)}개 장소)")
        
        valid_ids = set(crawling_df['contentid'])
        places = [p for p in places if p['contentid'] in valid_ids]
        if crawling_df.empty or crawling_df['텍스트'].str.strip().eq('').all():
            return places

        t3 = time.time()
        texts_to_embed = crawling_df[crawling_df['텍스트'].str.strip().ne('')]
        if not texts_to_embed.empty:
            embeddings = await recomm_engine.get_embedding(texts_to_embed['텍스트'].tolist())
            crawling_df['embedding'] = None
            crawling_df.loc[texts_to_embed.index, 'embedding'] = pd.Series(embeddings, index=texts_to_embed.index)
        t4 = time.time()
        print(f"  [2/4] 텍스트 임베딩 생성 완료: {t4 - t3:.2f} 초")

        t5 = time.time()
        df_embed = crawling_df.dropna(subset=['embedding'])
        if not df_embed.empty:
            matrix = df_embed["embedding"].tolist()
            sims = cosine_similarity([query_emb], matrix)[0]
            crawling_df.loc[df_embed.index, 'similarity'] = sims
        t6 = time.time()
        print(f"  [3/4] 유사도 계산 완료: {t6 - t5:.2f} 초")

        t7 = time.time()
        top_30_df = crawling_df.sort_values(by="similarity", ascending=False).head(30)
        if not top_30_df.empty:
            result_df = await recomm_engine.add_reasons_and_hashtags(top_30_df, adjectives, place_type)
            crawling_df = crawling_df.merge(result_df[['contentid', '추천이유', '해시태그']], on='contentid', how='left')
        t8 = time.time()
        print(f"  [4/4] 추천 이유/해시태그 생성 완료: {t8 - t7:.2f} 초")

    crawling_df = crawling_df.replace({np.nan: None})
    original_place_map = {p['contentid']: p for p in places}

    contentid_to_populartimes = {
        place['contentid']: pop_result
        for place, pop_result in zip(places, populartimes_results)
    }

    for _, row in crawling_df.iterrows():
        contentid = row['contentid']
        if contentid in original_place_map:
            original_place_map[contentid]['similarity'] = row.get('similarity')
            original_place_map[contentid]['recommend_reason'] = row.get('추천이유')
            original_place_map[contentid]['hashtags'] = row.get('해시태그')
            original_place_map[contentid]['populartimes'] = contentid_to_populartimes.get(contentid)

    sorted_places = sorted(
        original_place_map.values(),
        key=lambda p: p.get('similarity') if p.get('similarity') is not None else -1.0,
        reverse=True
    )
    total_end_time = time.time()
    print(f"  [AI 추천 파이프라인 종료] 총 소요 시간: {total_end_time - total_start_time:.2f} 초")
    print("======================================================\n")
    return sorted_places


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

MAX_PLACES_FOR_AI = 30


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
        base_params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'numOfRows': '50'}
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_restaurants_from_tour_api(session, {**base_params, 'cat3': cat}) for cat in food_categories]
            results = await asyncio.gather(*tasks)
        all_restaurants = [item for sublist in results for item in sublist]
        unique_restaurants = list({p['contentid']: p for p in all_restaurants}.values())
        sorted_restaurants = sorted(unique_restaurants, key=lambda x: float(x.get('dist', 0)))

        if adjectives_str:
            places_for_ai = sorted_restaurants[:MAX_PLACES_FOR_AI]
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(places_for_ai, adjectives, place_type = '음식점')
            return Response(final_results, status=status.HTTP_200_OK)
        else:
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

        params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'cat3': 'A05020900', 'numOfRows': '50'}
        async with aiohttp.ClientSession() as session:
            cafes = await fetch_restaurants_from_tour_api(session, params)
        sorted_cafes = sorted(cafes, key=lambda x: float(x.get('dist', 0)))

        if adjectives_str:
            places_for_ai = sorted_cafes[:MAX_PLACES_FOR_AI]
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(places_for_ai, adjectives, place_type = '카페')
            return Response(final_results, status=status.HTTP_200_OK)
        else:
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

        params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'contentTypeId': '12', 'numOfRows': '50'}
        async with aiohttp.ClientSession() as session:
            attractions = await fetch_attractions_from_tour_api(session, params)
        sorted_attractions = sorted(attractions, key=lambda x: float(x.get('dist', 0)))

        if adjectives_str:
            places_for_ai = sorted_attractions[:MAX_PLACES_FOR_AI]
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(places_for_ai, adjectives, place_type = '관광지')
            return Response(final_results, status=status.HTTP_200_OK)
        else:
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

        params = {'mapX': map_x, 'mapY': map_y, 'radius': radius, 'contentTypeId': '32', 'numOfRows': '50'}
        async with aiohttp.ClientSession() as session:
            accommodations = await fetch_attractions_from_tour_api(session, params)
        sorted_accommodations = sorted(accommodations, key=lambda x: float(x.get('dist', 0)))

        if adjectives_str:
            places_for_ai = sorted_accommodations[:MAX_PLACES_FOR_AI]
            adjectives = [adj.strip() for adj in adjectives_str.split(',')]
            final_results = await get_ai_recommendations(places_for_ai, adjectives, place_type = '숙소')
            return Response(final_results, status=status.HTTP_200_OK)
        else:
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

'''
08.08 TripSummaryView API 추가
'''

class TripSummaryView(AsyncAPIView):
    permission_classes = [IsAuthenticated]

    def _prepare_trip_context(self, trip: Trip, visited_places: list[VisitedContent]) -> str:
        context_parts = [
            f"- 여행 지역: {trip.region}",
            f"- 동행자: {trip.companion or '정보 없음'}",
            f"- 이동수단: {trip.transportation or '정보 없음'}",
            f"- 원했던 여행 분위기(형용사): {trip.adjectives or '정보 없음'}"
        ]
        visited_descriptions = ["\n[방문한 장소 목록]"]
        if not visited_places:
            visited_descriptions.append("방문한 장소가 없습니다.")
        else:
            for i, place in enumerate(visited_places):
                description = (
                    f"{i+1}. {place.title}: "
                    f"이곳에 대해 사용자가 남긴 추천 이유는 '{place.recommend_reason or '특이사항 없음'}' 이며, "
                    f"관련 해시태그는 '{place.hashtags or '없음'}' 입니다."
                )
                visited_descriptions.append(description)
        return "\n".join(context_parts + visited_descriptions)

    @sync_to_async
    def _get_trip_and_places(self, trip_id: int, user):
        trip = get_object_or_404(Trip, id=trip_id, user=user)
        visited_places = list(VisitedContent.objects.filter(trip=trip).order_by('created_at'))
        return trip, visited_places
    
    @sync_to_async
    def _save_trip_summary(self, trip: Trip, summary: str):
        trip.summary = summary
        trip.save(update_fields=['summary'])

    async def post(self, request, trip_id: int):
        try:
            trip, visited_places = await self._get_trip_and_places(trip_id, request.user)
        except ObjectDoesNotExist:
             return Response({"error": "해당 여행을 찾을 수 없거나 접근 권한이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        if not visited_places:
            return Response({"error": "요약을 생성할 방문 기록이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        trip_context = self._prepare_trip_context(trip, visited_places)
        print("--- AI에게 전달될 콘텍스트 ---")
        print(trip_context)
        print("--------------------------")

        try:
            async with RecommendationEngine() as recomm_engine:
                summary_text = await recomm_engine.generate_trip_summary(trip_context)
        except Exception as e:
            return Response({"error": f"AI 요약 생성 중 서버 오류 발생: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        await self._save_trip_summary(trip, summary_text)

        return Response({
            "trip_id": trip.id,
            "summary": summary_text
        }, status=status.HTTP_200_OK)