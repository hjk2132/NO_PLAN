# ai/services.py

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd
import re
import tiktoken
from openai import AsyncOpenAI
from sklearn.metrics.pairwise import cosine_similarity
from django.conf import settings


# --- Semaphore를 사용하기 위한 헬퍼 함수 ---
async def gather_with_concurrency(limit, *tasks):
    """
    동시 실행 개수를 제어하면서 asyncio.gather를 실행하는 헬퍼 함수
    """
    semaphore = asyncio.Semaphore(limit)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(task) for task in tasks))


class BlogCrawler:
    _CONTROL = re.compile(r'[\u200b-\u200f\u202a-\u202e]')
    _EMOJI = re.compile("["
                        u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF"
                        u"\U0001F1E0-\U0001F1FF" u"\U0001F900-\U0001F9FF" u"\U0001FA70-\U0001FAFF"
                        u"\u2300-\u23FF" u"\u2600-\u26FF" u"\u2700-\u27BF" u"\u2B00-\u2BFF" u"\uFE0F"
                        "]+", flags=re.UNICODE)

    def __init__(self, model: str = "text-embedding-3-small", max_tokens: int = 2500,
                 placeholder: str = "<NO_CONTENT>"):
        self.encoding = tiktoken.encoding_for_model(model)
        self.max_tokens = max_tokens
        self.placeholder = placeholder

    async def fetch(self, session, url: str, referer: str = None) -> str | None:
        headers = {"User-Agent": "Mozilla/5.0"}
        if referer: headers["Referer"] = referer
        try:
            async with session.get(url, headers=headers, timeout=5) as resp:
                return await resp.text()
        except Exception:
            return None

    def clean(self, text: str) -> str:
        text = self._CONTROL.sub("", text)
        return self._EMOJI.sub("", text)

    def truncate(self, text: str) -> str:
        toks = self.encoding.encode(text)
        if len(toks) > self.max_tokens:
            return self.encoding.decode(toks[:self.max_tokens])
        return text

    async def get_text(self, session, url: str) -> str:
        html = await self.fetch(session, url)
        if not html: return self.placeholder
        soup = BeautifulSoup(html, "lxml")
        iframe = soup.find("iframe", id="mainFrame")
        if iframe and iframe.get("src"):
            html = await self.fetch(session, "https://blog.naver.com" + iframe["src"], referer=url)
            if not html: return self.placeholder
            soup = BeautifulSoup(html, "lxml")
        cont = soup.find("div", class_="se-main-container")
        if not cont: return self.placeholder
        return self.clean(cont.get_text(strip=True))

    async def _search_blogs_aio(self, session: aiohttp.ClientSession, api_key: str, name: str, addr: str) -> list[str]:
        URL = "https://dapi.kakao.com/v2/search/blog"
        headers = {"Authorization": f"KakaoAK {api_key}"}
        addr = ' '.join(addr.split()[:2]) # 주소의 시, 구만 사용
        params = {"query": f'{name} {addr}', "size": 10}
        try:
            async with session.get(URL, headers=headers, params=params, timeout=5) as resp:
                if resp.status != 200:
                    print(f"Daum API Error for '{name}': Status {resp.status}, Response: {await resp.text()}")
                    return []
                data = await resp.json()
                urls = [doc['url'] for doc in data.get('documents', [])]
                return [url for url in urls if 'https://blog.naver.com' in url][:3] # 네이버 블로그만을 추출
        except Exception as e:
            print(f"Daum API request failed for '{name}': {e}")
            return []

    async def crawl_all(self, place_infos_with_id: list[tuple[str, str, str]], print_text = False) -> pd.DataFrame:
        daum_api_key = settings.DAUM_API_KEY

        # 각 장소에 대한 전체 처리 프로세스를 동시 30개로 제한
        CONCURRENCY_LIMIT_PLACES = 30

        async def process_place(contentid, name, addr, session):
            urls = await self._search_blogs_aio(session, daum_api_key, name, addr)
            if not urls:
                combined_text = self.placeholder
            else:
                crawl_tasks = [self.get_text(session, url) for url in urls]
                # 각 장소 내부의 블로그 크롤링은 동시 5개로 제한
                crawled_texts = await gather_with_concurrency(5, *crawl_tasks)
                truncated_texts = [self.truncate(text) for text in crawled_texts]
                incorrect_texts = [text if (text == self.placeholder)
                                           or (re.sub(r'\([^)]*\)', '', name.split()[0]) in text.replace(" ", "")) # 이름에서 지졈명과 괄호 안 내용 삭제, 공백을 삭제한 블로그 텍스트와 비교
                    else '<INCORRECT_CONTENT>'
                    for text in truncated_texts]
                
                # 블로그 결과 디버깅용 print_text
                if print_text:
                    combined_text = " ".join(incorrect_texts)
                    return {"contentid": contentid, "관광지명": name, "텍스트": combined_text, 'urls': urls}
                
                # placeholder 제거 
                clean_text = [t for t in incorrect_texts if t not in ("<INCORRECT_CONTENT>", self.placeholder)]
                combined_text = " ".join(clean_text)
                # 결과가 없거나 불일치한 블로그만 있는 경우 None반환
                if not combined_text.strip():
                    return None
                    
            return {"contentid": contentid, "관광지명": name, "텍스트": combined_text, 'urls': urls}

        async with aiohttp.ClientSession() as session:
            tasks = [process_place(cid, n, a, session) for cid, n, a in place_infos_with_id]
            raw_results = await gather_with_concurrency(CONCURRENCY_LIMIT_PLACES, *tasks)
            final_results = [r for r in raw_results if r is not None] # 크롤링 결과가 없는 장소 제거

        return pd.DataFrame(final_results)


class RecommendationEngine:
    def __init__(self, embedding_model: str = "text-embedding-3-small", chat_model: str = "gpt-4.1-nano",
                 top_k: int = 5):
        api_key = settings.OPENAI_API_KEY
        self.client = AsyncOpenAI(api_key=api_key)
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.top_k = top_k

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.client, 'close'):
            await self.client.close()

    async def get_embedding(self, text: list[str]) -> list[list[float]]:
        res = await self.client.embeddings.create(input=text, model=self.embedding_model)
        return [list(r.embedding) for r in res.data]

    async def get_query_embedding(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(input=[text], model=self.embedding_model)
        return response.data[0].embedding

    @staticmethod
    def adjectives_to_query(adjectives: list[str]) -> str:
        adj_mean_mapping_dict = {'고즈넉한':'고요하고 아늑하고 잠잠하다', 
                                 '낭만적인':'현실적이지 않고 신비적이며 공상적인 것. 또는 감동적이며 달콤한 분위기가 있다.', 
                                 '모던한':'세련되고 현대적이다.', 
                                 '힙한':'고유한 개성과 감각을 가지고 있으면서도 최신 유행에 밝고 신선하다', 
                                 '고급스러운':'물건이나 시설 따위의 품질이 뛰어나고 값이 비싼 듯하다.', 
                                 '전통적인':'예로부터 이어져 내려오는 듯하다.', 
                                 '활동적인':'몸을 움직여 행동하다.', 
                                 '산뜻한':'기분이나 느낌이 깨끗하고 시원하다',
                                 '정겨운':'정이 넘칠 정도로 매우 다정하다.' }
        return " ".join(adj_mean_mapping_dict[adj] for adj in adjectives)

    def recommend_spots(self, df: pd.DataFrame, query_emb: list[float]) -> pd.DataFrame:
        df_embed = df.dropna(subset=['embedding'])
        if df_embed.empty: return pd.DataFrame()
        matrix = df_embed["embedding"].tolist()
        sims = cosine_similarity([query_emb], matrix)[0]
        df_copy = df_embed.copy()
        df_copy["similarity"] = sims
        return df_copy.sort_values(by="similarity", ascending=False).head(self.top_k)

    async def generate_reason_and_hashtags(self, spot_name: str, adjectives: list[str], adjectives_query: str, blog_text: str, place_type: str) -> tuple[str, str]:
        prompt = f"""
당신의 역할은 "관광지명"과 해당 관광지의 블로그 후기인 "블로그" 텍스트를 활용하여 사용자에게 장소를 추천해주는 것입니다.
아래 "형용사"는 사용자가 장소에 대해 원하는 분위기이고, "형용사 의미"는 "형용사의 사전적 의미에 대한 정보입니다.
(1) '블로그' 텍스트에서 '장소유형'에 맞는 장소의 특징, 서비스 등의 직접적으로 관련된 내용을 추출하여 요약하세요. 이때, 주변 이야기나 "관광지명"과 관련 없는 정보는 절대 포함하지 마세요.
(2) (1)에서 요약한 정보로 사용자가 제시한 "형용사"가 잘 어울리는 이유를 작성하세요. 이때, 제시된 형용사를 직접적으로 언급하는 건 지양하고, '관광지명'으로 시작하세요. 
지시사항을 기반으로 해요체를 사용하여 해당 장소의 추천이유를 1~2 문장으로 작성하세요.
또한, 형용사를 배제하고 (1)에서 요약한 내용을 기반으로, 해당 장소를 잘 나타내는 명사와 형용사로 3~5개의 해시태그를 만드세요.
추천이유 예시: "다동 황소 막창은 쫄깃하고 고소한 막창과 깔끔한 반찬이 어우러져 맛과 품질 모두 뛰어난 곳이에요."
- 형용사: {adjectives}
- 형용사 의미: {adjectives_query}
- 관광지명: {spot_name}
- 장소유형: {place_type}
- 블로그: {blog_text}
[출력 형식]
1. 추천 이유: (1~2 문장)
2. 해시태그: #(명사/형용사) #(명사/형용사) #(명사/형용사) #(명사/형용사)
"""
        try:
            resp = await self.client.chat.completions.create(model=self.chat_model,
                                                             messages=[{"role": "user", "content": prompt}],
                                                             temperature=0.7, max_tokens=200)
            text = resp.choices[0].message.content.strip()
            reason = re.search(r"추천 이유[:：]\s*(.+)", text)
            tags = re.search(r"해시태그[:：]\s*(.+)", text)
            return (reason.group(1).strip() if reason else "추천 이유를 생성하지 못했습니다.",
                    tags.group(1).strip() if tags else "#해시태그_없음")
        except Exception as e:
            print(f"[오류] {spot_name} 추천 이유 생성 실패: {e}")
            return ("추천 이유 생성 실패", "해시태그 생성 실패")

    async def add_reasons_and_hashtags(self, df: pd.DataFrame, adjectives: list[str], place_type: str) -> pd.DataFrame:
        df_copy = df.copy()
        adj_query = self.adjectives_to_query(adjectives)
        tasks = []
        for _, row in df_copy.iterrows():
            tasks.append(self.generate_reason_and_hashtags(row["관광지명"], adjectives, adj_query, row['텍스트'], place_type))

        # OpenAI API는 Rate Limit이 엄격하므로, 동시 요청을 10개로 제한합니다.
        CONCURRENCY_LIMIT = 10
        results = await gather_with_concurrency(CONCURRENCY_LIMIT, *tasks)

        df_copy["추천이유"], df_copy["해시태그"] = zip(*results)
        return df_copy


    # ===================================================================
    # 여행 요약 생성 (08.08 추가 내용)
    # ===================================================================
    async def generate_trip_summary(self, trip_context: str) -> str:
        """
        주어진 여행 정보 콘텍스트를 바탕으로 AI 여행 요약을 생성합니다.
        """
        prompt = f"""
당신은 여행의 추억을 아름답게 정리해주는 여행 작가입니다. 아래는 사용자의 여행 기록 데이터입니다. 이 데이터를 바탕으로 전체 여행을 아우르는 감성적이고 구체적인 여행 요약을 3~4개의 문장으로 작성해주세요.

- 여행의 전체적인 분위기(사용자가 원했던 형용사)와 방문했던 장소 1~2곳의 특징을 자연스럽게 연결해주세요.
- 친구에게 여행 후기를 말해주는 것처럼 친근하고 부드러운 존댓말을 사용해주세요.
- 최종 결과물은 다른 설명 없이 오직 '요약 문장'만 있어야 합니다.

[여행 기록 데이터]
{trip_context}
"""
        try:
            resp = await self.client.chat.completions.create(
                model=self.chat_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=500
            )
            summary = resp.choices[0].message.content.strip()
            return summary
        except Exception as e:
            print(f"[오류] 여행 요약 생성 실패: {e}")
            return "여행 요약을 생성하는 데 실패했습니다."