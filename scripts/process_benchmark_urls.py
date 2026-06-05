"""
URL 처리 스크립트 — admin.html에서 등록한 쿠팡 URL을 처리하여
data/manual_candidates.json 후보 목록에 추가
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from config import DATA_DIR, LOG_DIR, NAVER_CLIENT_ID

PENDING_URLS_PATH  = os.path.join(DATA_DIR, "pending_benchmark_urls.json")
CANDIDATES_PATH    = os.path.join(DATA_DIR, "manual_candidates.json")
MAX_PER_BATCH      = 20

KST = timezone(timedelta(hours=9))

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "process_urls.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("process_urls")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize_coupang_url(url: str) -> str:
    """쿠팡 단축 URL 또는 파트너스 URL을 상품 URL로 정규화"""
    url = url.strip()
    # 쿠팡 파트너스 링크 (link.coupang.com) → 리다이렉트 따라가기
    if "link.coupang.com" in url or "coupang.com/vp/products" in url:
        return url
    return url


def _extract_product_id(url: str) -> str | None:
    """URL에서 상품 ID 추출"""
    m = re.search(r"/products/(\d+)", url)
    return m.group(1) if m else None


def _fetch_product_info_naver(name: str) -> dict:
    """네이버 쇼핑에서 상품 정보 보충"""
    if not NAVER_CLIENT_ID:
        return {}
    try:
        import requests, urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        from config import NAVER_CLIENT_SECRET
        headers = {
            "X-Naver-Client-Id":     NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }
        resp = requests.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers=headers,
            params={"query": name[:40], "display": 1},
            timeout=8, verify=False,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                item = items[0]
                price = item.get("lprice", "")
                return {
                    "price": f"{int(price):,}원" if price else "",
                    "brand": re.sub(r"<[^>]+>", "", item.get("brand", "")),
                    "category_hint": item.get("category1", ""),
                }
    except Exception as e:
        logger.warning(f"네이버 보충 실패: {e}")
    return {}


def _fetch_page_title(url: str) -> str:
    """상품 페이지 title 태그에서 상품명 추출"""
    try:
        import requests, urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10, verify=False, allow_redirects=True)
        if resp.status_code == 200:
            m = re.search(r"<title[^>]*>([^<]+)</title>", resp.text, re.I)
            if m:
                title = m.group(1).strip()
                # "상품명 - 쿠팡" 형식에서 상품명만
                title = re.sub(r"\s*[-|]\s*(쿠팡|Coupang).*$", "", title, flags=re.I).strip()
                return title
        # 최종 URL (리다이렉트 후)
        if resp.url != url:
            return resp.url
    except Exception as e:
        logger.warning(f"페이지 타이틀 수집 실패 ({url[:60]}): {e}")
    return ""


def _fetch_thumbnail(url: str) -> str:
    """상품 페이지 og:image 추출"""
    try:
        import requests, urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10, verify=False, allow_redirects=True)
        if resp.status_code == 200:
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)', resp.text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def process_url(url: str) -> dict | None:
    """URL 1개 처리 → candidate dict 반환"""
    url = _normalize_coupang_url(url)
    logger.info(f"처리 중: {url[:80]}")

    # 상품명 + 최종 URL
    title = _fetch_page_title(url)
    if not title:
        logger.warning(f"  상품명 수집 실패, 건너뜀")
        return None

    logger.info(f"  상품명: {title[:50]}")

    # 최종 상품 URL (파트너스 링크 → coupang.com 변환 시도)
    product_url = url
    m = re.search(r"(https://www\.coupang\.com/vp/products/\d+[^\s\"']*)", url)
    if m:
        product_url = m.group(1)

    # 썸네일
    image_url = _fetch_thumbnail(url)

    # 네이버로 가격/브랜드 보충
    extra = _fetch_product_info_naver(title)

    product = {
        "name":         title,
        "product_url":  product_url,
        "image_url":    image_url,
        "price":        extra.get("price", ""),
        "brand":        extra.get("brand", ""),
        "category_hint": extra.get("category_hint", ""),
        "source":       "url_input",
    }

    return {
        "product":        product,
        "source_account": "url_input",
        "added_at":       datetime.now(KST).isoformat(),
    }


def run():
    logger.info("=" * 50)
    logger.info(f"URL 처리 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    logger.info("=" * 50)

    pending = _load_json(PENDING_URLS_PATH, {"urls": []})
    urls = pending.get("urls", [])
    if not urls:
        logger.info("처리할 URL 없음")
        return

    logger.info(f"{len(urls)}개 URL 처리 예정")

    existing = _load_json(CANDIDATES_PATH, {"scanned_at": "", "candidates": []})
    candidates = existing.get("candidates", [])
    existing_urls = {c.get("product", {}).get("product_url", "")[:80] for c in candidates}

    added = 0
    for url in urls[:MAX_PER_BATCH]:
        try:
            c = process_url(url)
            if not c:
                continue
            key = c["product"].get("product_url", "")[:80]
            if key in existing_urls:
                logger.info(f"  이미 존재, 건너뜀")
                continue
            candidates.insert(0, c)
            existing_urls.add(key)
            added += 1
        except Exception as e:
            logger.error(f"URL 처리 오류 ({url[:60]}): {e}")

    # 최대 100개 유지
    candidates = candidates[:100]

    result = {
        "scanned_at": existing.get("scanned_at", ""),
        "updated_at": datetime.now(KST).isoformat(),
        "candidates": candidates,
    }
    _save_json(CANDIDATES_PATH, result)

    # pending URL 초기화
    _save_json(PENDING_URLS_PATH, {"urls": [], "submitted_at": "", "processed_at": datetime.now(KST).isoformat()})

    logger.info(f"완료: {added}개 추가, 총 {len(candidates)}개 후보")


if __name__ == "__main__":
    run()
