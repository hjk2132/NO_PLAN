import requests
from django.conf import settings  # settings.py의 변수를 가져오기 위함


def get_region_from_coords(latitude, longitude):
    """
    위도, 경도를 받아 카카오 API를 통해 지역명(1depth, 2depth)이 담긴
    딕셔너리를 반환하는 함수
    """
    api_key = settings.KAKAO_API_KEY
    headers = {'Authorization': f'KakaoAK {api_key}'}
    params = {'x': longitude, 'y': latitude}
    url = "https://dapi.kakao.com/v2/local/geo/coord2address.json"

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()

        if not data.get('documents'):
            return None

        address_info = data['documents'][0].get('address')
        if address_info:
            # 여기를 수정합니다. 두 정보를 딕셔너리에 담아 반환합니다.
            return {
                'region_1depth_name': address_info.get('region_1depth_name'),
                'region_2depth_name': address_info.get('region_2depth_name')
            }
        else:
            return None

    except requests.exceptions.RequestException as e:
        print(f"API 요청 실패: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"JSON 파싱 오류: {e}")
        return None