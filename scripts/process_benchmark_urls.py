"""
컬렉션 URL 처리 스크립트
- admin.html에서 inpock 프로필/컬렉션 페이지 URL을 받아
  페이지 안의 모든 상품을 수집 → data/manual_candidates.json 에 추가
- 개별 쿠팡 상품 URL도 처리 (직접 입력용)
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from config import DATA_DIR, LOG_DIR, NAVER_CLIENT_ID

PENDING_URLS_PATH = os.path.join(DATA_DIR, "pending_benchmark_urls.json")
CANDIDATES_PATH   = os.path.join(DATA_DIR, "manual_candidates.json")
MAX_PER_PAGE      = 30   # 컬렉션 1개당 최대 수집 상품 수
MAX_TOTAL         = 100  # manual_candidates.json 최대 보관 수

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

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get(url, timeout=15) -> requests.Response | None:
    try:
        return requests.get(url, headers=_HEADERS, timeout=timeout, verify=False, allow_redirects=True)
    except Exception as e:
        logger.warning(f"  GET 실패 ({url[:60]}): {e}")
        return None


def _follow_to_coupang(url: str) -> str | None:
    """어떤 링크든 최종 쿠팡 상품 URL로 추적. 실패 시 None."""
    if re.search(r"coupang\.com/vp/products/\d+", url):
        return url
    resp = _get(url, timeout=10)
    if not resp:
        return None
    final = resp.url
    html  = resp.text
    # 최종 URL
    m = re.search(r"(https?://(?:www\.)?coupang\.com/vp/products/\d+)", final)
    if m:
        return m.group(1)
    # HTML 내 직접 URL
    m2 = re.search(r"(https?://(?:www\.)?coupang\.com/vp/products/\d+)", html)
    if m2:
        return m2.group(1)
    # link.coupang.com → 한번 더 따라가기
    m3 = re.search(r'"(https://link\.coupang\.com/[^"]+)"', html)
    if m3:
        r2 = _get(m3.group(1), timeout=8)
        if r2:
            m4 = re.search(r"(https?://(?:www\.)?coupang\.com/vp/products/\d+)", r2.url)
            if m4:
                return m4.group(1)
    return None


def _product_id(url: str) -> str | None:
    m = re.search(r"/products/(\d+)", url)
    return m.group(1) if m else None


# ── 네이버 상품 정보 보충 ─────────────────────────────────────────────────────

def _naver_enrich(name: str) -> dict:
    if not NAVER_CLIENT_ID:
        return {}
    try:
        from config import NAVER_CLIENT_SECRET
        resp = requests.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers={
                "X-Naver-Client-Id":     NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={"query": name[:40], "display": 1},
            timeout=8, verify=False,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                it = items[0]
                price = it.get("lprice", "")
                return {
                    "price":         f"{int(price):,}원" if price else "",
                    "brand":         re.sub(r"<[^>]+>", "", it.get("brand", "")),
                    "category_hint": it.get("category1", ""),
                }
    except Exception as e:
        logger.warning(f"  네이버 보충 실패: {e}")
    return {}


# ── 쿠팡 상품 정보 수집 ───────────────────────────────────────────────────────

def _fetch_coupang_product(product_url: str) -> dict | None:
    """쿠팡 상품 페이지에서 이름·이미지 수집"""
    resp = _get(product_url)
    if not resp or resp.status_code != 200:
        return None
    html = resp.text
    # 상품명
    name = ""
    m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
    if m:
        name = re.sub(r'\s*[-|]\s*(쿠팡|Coupang).*$', '', m.group(1), flags=re.I).strip()
    if not name:
        return None
    # og:image
    img = ""
    m2 = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)', html)
    if m2:
        img = m2.group(1)
    return {"name": name, "image_url": img, "product_url": product_url}


# ── inpock 컬렉션 스크래퍼 ───────────────────────────────────────────────────

def _scrape_inpock(page_url: str, source_label: str) -> list[dict]:
    """
    inpock 컬렉션/프로필 페이지에서 상품 목록 수집
    반환: candidate dict 리스트
    """
    logger.info(f"inpock 페이지 수집: {page_url}")
    resp = _get(page_url)
    if not resp:
        return []
    html = resp.text

    affiliate_links: list[str] = []
    seen_links: set[str] = set()

    # 1. __NEXT_DATA__ JSON 파싱 (Next.js 기반 inpock)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            raw = json.dumps(data)
            # JSON 안의 모든 link.coupang.com URL
            found = re.findall(r'https://link\.coupang\.com/[A-Za-z0-9/_\-?=&%]+', raw)
            affiliate_links.extend(found)
            logger.info(f"  __NEXT_DATA__ 에서 파트너스 링크 {len(found)}개 발견")
        except Exception as e:
            logger.warning(f"  __NEXT_DATA__ 파싱 실패: {e}")

    # 2. HTML 원문에서 link.coupang.com 직접 추출
    found2 = re.findall(r'https://link\.coupang\.com/[A-Za-z0-9/_\-?=&%]+', html)
    affiliate_links.extend(found2)

    # 3. 직접 coupang.com/vp/products URL
    direct = re.findall(r'https?://(?:www\.)?coupang\.com/vp/products/\d+[^\s"\'<>&]*', html)
    affiliate_links.extend(direct)

    # 중복 제거
    unique_links = []
    for lnk in affiliate_links:
        key = lnk[:80]
        if key not in seen_links:
            seen_links.add(key)
            unique_links.append(lnk)

    logger.info(f"  총 {len(unique_links)}개 링크 발견 → 최대 {MAX_PER_PAGE}개 처리")

    candidates = []
    seen_pids: set[str] = set()

    for lnk in unique_links[:MAX_PER_PAGE * 2]:  # 여유분 처리
        if len(candidates) >= MAX_PER_PAGE:
            break

        coupang_url = _follow_to_coupang(lnk)
        if not coupang_url:
            continue

        pid = _product_id(coupang_url)
        if not pid or pid in seen_pids:
            continue
        seen_pids.add(pid)

        # 상품 정보 수집
        product_info = _fetch_coupang_product(coupang_url)
        if not product_info:
            continue

        # 네이버 가격/카테고리 보충
        extra = _naver_enrich(product_info["name"])

        product = {
            "name":          product_info["name"],
            "product_url":   coupang_url,
            "image_url":     product_info.get("image_url", ""),
            "price":         extra.get("price", ""),
            "brand":         extra.get("brand", ""),
            "category_hint": extra.get("category_hint", ""),
            "source":        "collection_scrape",
        }

        candidates.append({
            "product":        product,
            "source_account": source_label,
            "added_at":       datetime.now(KST).isoformat(),
        })
        logger.info(f"  [{len(candidates)}] {product['name'][:40]}")

    logger.info(f"  → {len(candidates)}개 수집 완료")
    return candidates


# ── 개별 상품 URL 처리 (직접 입력용) ─────────────────────────────────────────

def _process_single_url(url: str) -> dict | None:
    """단일 상품 URL 처리 → candidate dict"""
    coupang_url = _follow_to_coupang(url)
    if not coupang_url:
        logger.warning(f"  쿠팡 URL 변환 실패: {url[:60]}")
        return None

    product_info = _fetch_coupang_product(coupang_url)
    if not product_info:
        logger.warning(f"  상품 정보 수집 실패: {coupang_url[:60]}")
        return None

    extra = _naver_enrich(product_info["name"])
    product = {
        "name":          product_info["name"],
        "product_url":   coupang_url,
        "image_url":     product_info.get("image_url", ""),
        "price":         extra.get("price", ""),
        "brand":         extra.get("brand", ""),
        "category_hint": extra.get("category_hint", ""),
        "source":        "direct_url",
    }
    return {
        "product":        product,
        "source_account": "직접입력",
        "added_at":       datetime.now(KST).isoformat(),
    }


# ── 메인 ──────────────────────────────────────────────────────────────────────

def run():
    logger.info("=" * 50)
    logger.info(f"URL 처리 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    logger.info("=" * 50)

    pending = _load_json(PENDING_URLS_PATH, {"urls": []})
    urls = pending.get("urls", [])
    if not urls:
        logger.info("처리할 URL 없음")
        return

    logger.info(f"{len(urls)}개 URL 입력됨")

    existing = _load_json(CANDIDATES_PATH, {"scanned_at": "", "candidates": []})
    candidates: list[dict] = existing.get("candidates", [])
    existing_pids = set()
    for c in candidates:
        pid = _product_id(c.get("product", {}).get("product_url", ""))
        if pid:
            existing_pids.add(pid)

    total_added = 0

    for url in urls:
        url = url.strip()
        if not url:
            continue

        # inpock 또는 다른 컬렉션 페이지인지 판단
        is_collection = (
            "inpock.co.kr" in url
            or "linktr.ee" in url
            or "lnk.bio" in url
        )
        # 직접 쿠팡/파트너스 상품 URL이면 단일 처리
        is_single = (
            re.search(r"coupang\.com/vp/products/\d+", url)
            or "link.coupang.com" in url
        )

        if is_single:
            logger.info(f"[단일] {url[:60]}")
            c = _process_single_url(url)
            if c:
                pid = _product_id(c["product"]["product_url"])
                if pid and pid not in existing_pids:
                    existing_pids.add(pid)
                    candidates.insert(0, c)
                    total_added += 1
                    logger.info(f"  추가: {c['product']['name'][:40]}")
        else:
            # 컬렉션/프로필 페이지
            label = url.split("/")[-1] or url.split("/")[-2]  # URL 마지막 세그먼트를 출처로
            logger.info(f"[컬렉션] {url[:60]} → @{label}")
            new_items = _scrape_inpock(url, f"@{label}")
            for c in new_items:
                pid = _product_id(c["product"]["product_url"])
                if pid and pid not in existing_pids:
                    existing_pids.add(pid)
                    candidates.insert(0, c)
                    total_added += 1

    # 최대 MAX_TOTAL개 유지
    candidates = candidates[:MAX_TOTAL]

    result = {
        "scanned_at": existing.get("scanned_at", ""),
        "updated_at": datetime.now(KST).isoformat(),
        "candidates": candidates,
    }
    _save_json(CANDIDATES_PATH, result)

    # pending 초기화
    _save_json(PENDING_URLS_PATH, {
        "urls": [],
        "submitted_at": "",
        "processed_at": datetime.now(KST).isoformat(),
    })

    logger.info(f"완료: {total_added}개 신규 추가, 총 {len(candidates)}개 후보")


if __name__ == "__main__":
    run()
