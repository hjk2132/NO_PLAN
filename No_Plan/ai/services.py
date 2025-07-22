# ai/services.py

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd
import re
import tiktoken
from openai import OpenAI, AsyncOpenAI
from sklearn.metrics.pairwise import cosine_similarity
from django.conf import settings


class BlogCrawler:
    _CONTROL = re.compile(r'[\u200b-\u200f\u202a-\u202e]')
    _EMOJI = re.compile("["
                        u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF"
                        u"\U0001F1E0-\U0001F1FF" u"\U0001F900-\U0001F9FF" u"\U0001FA70-\U0001FAFF"
                        u"\u2300-\u23FF" u"\u2600-\u26FF" u"\u2700-\u27BF" u"\u2B00-\u2BFF" u"\uFE0F"
                        "]+", flags=re.UNICODE)

    def __init__(self, model: str = "text-embedding-3-small", max_tokens: int = 1600,
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

    async def _search_blogs_aio(self, session: aiohttp.ClientSession, api_key: str, name: str) -> list[str]:
        URL = "https://dapi.kakao.com/v2/search/blog"
        headers = {"Authorization": f"KakaoAK {api_key}"}
        params = {"query": name, "size": 5}
        try:
            async with session.get(URL, headers=headers, params=params, timeout=5) as resp:
                if resp.status != 200:
                    print(f"Daum API Error for '{name}': Status {resp.status}, Response: {await resp.text()}")
                    return []
                data = await resp.json()
                return [doc['url'] for doc in data.get('documents', [])]
        except Exception as e:
            print(f"Daum API request failed for '{name}': {e}")
            return []

    # --- 핵심 수정 ---
    # 1. 단일 장소의 '검색->크롤링->결합' 로직을 처리하는 비동기 헬퍼 함수를 추가합니다.
    async def _crawl_and_process_place(self, session: aiohttp.ClientSession, api_key: str,
                                       place_info: tuple[str, str, str]) -> dict:
        """단일 장소에 대한 블로그 검색, 크롤링, 텍스트 결합을 수행합니다."""
        contentid, name, addr = place_info

        # 각 장소의 블로그 URL 검색
        urls = await self._search_blogs_aio(session, api_key, name)

        # 검색된 URL들 크롤링
        if not urls:
            combined_text = self.placeholder
        else:
            # 해당 장소의 블로그 5개를 동시에 크롤링합니다.
            crawl_tasks = [self.get_text(session, url) for url in urls]
            crawled_texts = await asyncio.gather(*crawl_tasks)
            truncated_texts = [self.truncate(text) for text in crawled_texts]
            combined_text = " ".join(truncated_texts)

        # contentid와 함께 결과 딕셔너리를 반환합니다.
        return {
            "contentid": contentid,
            "관광지명": name,
            "텍스트": combined_text
        }

    # 2. crawl_all 메소드를 수정하여 위 헬퍼 함수를 병렬로 실행합니다.
    async def crawl_all(self, place_infos_with_id: list[tuple[str, str, str]]) -> pd.DataFrame:
        """
        (contentid, title, address) 튜플 리스트를 받아, 모든 장소에 대한 블로그
        크롤링을 병렬로 수행하고 contentid를 포함한 DataFrame을 반환합니다.
        """
        daum_api_key = settings.DAUM_API_KEY

        async with aiohttp.ClientSession() as session:
            # 3. 모든 장소에 대한 작업(Task) 리스트를 생성합니다.
            #    이 시점에서는 코드가 실행되지 않고, 계획만 세워둡니다.
            tasks = [
                self._crawl_and_process_place(session, daum_api_key, place_info)
                for place_info in place_infos_with_id
            ]

            # 4. asyncio.gather를 사용하여 모든 작업을 병렬로 실행하고 결과를 한 번에 받습니다.
            #    이 부분이 성능 향상의 핵심입니다.
            final_results = await asyncio.gather(*tasks)

        # 결과가 비어있는 경우를 대비한 방어 코드
        if not final_results:
            return pd.DataFrame(columns=["contentid", "관광지명", "텍스트"])

        return pd.DataFrame(final_results)


class RecommendationEngine:
    def __init__(self, embedding_model: str = "text-embedding-3-small", chat_model: str = "gpt-3.5-turbo",
                 top_k: int = 5):
        api_key = settings.OPENAI_API_KEY
        self.embed_client = OpenAI(api_key=api_key)
        self.chat_client = AsyncOpenAI(api_key=api_key)
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.top_k = top_k

    def get_embedding(self, text: list[str]) -> list[list[float]]:
        res = self.embed_client.embeddings.create(input=text, model=self.embedding_model)
        return [list(r.embedding) for r in res.data]

    def get_query_embedding(self, text: str) -> list[float]:
        response = self.embed_client.embeddings.create(input=[text], model=self.embedding_model)
        return response.data[0].embedding

    @staticmethod
    def adjectives_to_query(adjectives: list[str]) -> str:
        return "이런 분위기의 장소: " + ", ".join(adjectives)

    def recommend_spots(self, df: pd.DataFrame, query_emb: list[float]) -> pd.DataFrame:
        df_embed = df.dropna(subset=['embedding'])
        if df_embed.empty: return pd.DataFrame()
        matrix = df_embed["embedding"].tolist()
        sims = cosine_similarity([query_emb], matrix)[0]
        df_copy = df_embed.copy()
        df_copy["similarity"] = sims
        return df_copy.sort_values(by="similarity", ascending=False).head(self.top_k)

    async def generate_reason_and_hashtags(self, spot_name: str, adjectives_str: str, summary: str) -> tuple[str, str]:
        prompt = f"""
당신은 장소 추천 도우미입니다. 아래는 블로그에서 발췌한 요약입니다. 여기서 장소의 특징, 음식, 서비스와 직접적으로 관련된 내용만 참고하여,추천 이유를 작성하세요. 주변 이야기나 관련 없는 정보는 절대 포함하지 마세요.
관광지 이름과 후기가 주어졌을 때, 사용자가 원하는 형용사와 잘 어울리는 추천 이유를 1줄로 작성해줘. **장소의 분위기와 추천하는 이유와 가게의 특징 모두 포함되도록 하고, 문장은 존댓말로 해줘.** 해당 장소를 잘 나타내는 명사와 형용사로 4~5개의 해시태그를 만들어 주세요.
- 형용사: {adjectives_str}
- 관광지명: {spot_name}
- 요약: {summary}
[출력 형식]
1. 추천 이유: (한 문장)
2. 해시태그: #(명사/형용사) #(명사/형용사) #(명사/형용사) #(명사/형용사)
"""
        try:
            resp = await self.chat_client.chat.completions.create(model=self.chat_model,
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

    @staticmethod
    def extract_context_around_place(text: str, place_name: str, window: int = 5, max_length: int = 1000) -> str:
        sentences = re.split(r'(?<=[.?!])\s*', text)
        has_name = any(place_name in s for s in sentences)
        if not has_name:
            s = text.replace("\n", " ").strip()
            return s[:max_length] + ("..." if len(s) > max_length else "")
        selected_indices = [i for i, sent in enumerate(sentences) if place_name in sent]
        content_indices = set()
        for i in selected_indices:
            start = max(i - window, 0)
            end = min(i + window + 1, len(sentences))
            content_indices.update(range(start, end))
        selected_sentences = [sentences[i] for i in sorted(list(content_indices))]
        comb = " ".join(selected_sentences).replace("\n", " ").strip()
        return comb[:max_length] + ("..." if len(comb) > max_length else "")

    async def add_reasons_and_hashtags(self, df: pd.DataFrame, adjectives: list[str]) -> pd.DataFrame:
        df_copy = df.copy()
        adj_str = ", ".join(sorted(adjectives))
        tasks = []
        for _, row in df_copy.iterrows():
            summary = self.extract_context_around_place(row["텍스트"], row["관광지명"], window=2, max_length=1500)
            tasks.append(self.generate_reason_and_hashtags(row["관광지명"], adj_str, summary))
        results = await asyncio.gather(*tasks)
        df_copy["추천이유"], df_copy["해시태그"] = zip(*results)
        return df_copy