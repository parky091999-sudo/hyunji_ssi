"""
Google News RSS로 한국 이슈/트렌드 키워드 수집
- F타입(이슈/논란형) 일상글 생성 시 활용
"""
import logging
import re
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
_SKIP_RE = re.compile(
    r"북한|무기|전쟁|핵|미사일|테러|사망|사고|화재|재해|폭력|범죄|살인|강간|마약|자살|천재지변"
)


def get_trending_topics(limit: int = 8) -> list[str]:
    """한국 Google News에서 현재 이슈 키워드 목록 반환 (최대 limit개)"""
    try:
        resp = requests.get(
            _GOOGLE_NEWS_RSS,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        root = ElementTree.fromstring(resp.content)
        items = root.findall(".//item/title")
        topics = []
        for item in items:
            title = (item.text or "").strip()
            if not title or _SKIP_RE.search(title):
                continue
            title = re.sub(r"\s+-\s+\S+$", "", title).strip()
            if len(title) > 5:
                topics.append(title)
            if len(topics) >= limit:
                break
        logger.info(f"트렌딩 {len(topics)}개 수집: {topics[:3]}")
        return topics
    except Exception as e:
        logger.warning(f"트렌딩 뉴스 수집 실패: {e}")
        return []
