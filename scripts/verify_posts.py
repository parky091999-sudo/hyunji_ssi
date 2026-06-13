"""
Threads 게시 검증 + 포스팅 무결성 재점검.

1. feed_posts.json ↔ Threads API 매칭 (살아있는 글, 누락 글, 댓글 누락)
2. 무결성 체크: short_name 이상, post_text 잘림 감지 → registry 자동 수정
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from config import DATA_DIR
from poster.threads import _api, fetch_my_posts, THREADS_ACCESS_TOKEN, THREADS_USER_ID

FEED_POSTS_PATH    = os.path.join(DATA_DIR, "feed_posts.json")
REPLIED_PATH       = os.path.join(DATA_DIR, "replied_comments.json")
REGISTRY_PATH      = os.path.join(DATA_DIR, "product_registry.json")

_FOOTER_RE = re.compile(r'\n\n제품 정보는 프로필 링크에서 \[\d{3}\] 검색 👆\s*$')
_SENTENCE_END_RE = re.compile(r'[다요임어야겠네봄않함봐!?~\).♥]$')


def _shortcode(url: str) -> str:
    return url.rstrip("/").split("/post/")[-1] if url and "/post/" in url else ""


def _is_truncated(text: str) -> bool:
    """post_text 잘림 휴리스틱: 푸터 제거 후 마지막 단락이 문장으로 끝나는지."""
    body = _FOOTER_RE.sub("", text or "").strip()
    if not body:
        return False
    last_para = body.split('\n\n')[-1].strip()
    last_line = last_para.split('\n')[-1].strip()
    # 해시태그·체크마크·URL 종결 패턴(spec=숫자 등)으로 끝나면 완성된 것
    if last_line.startswith('#') or last_line.startswith('✔') or last_line.startswith('•'):
        return False
    if re.search(r'(spec|itemId|vendorItemId|pageKey|ctag|lptag)=\d+\s*$', last_line):
        return False
    return not bool(_SENTENCE_END_RE.search(last_line))


def _fallback_short_name(name: str) -> str:
    """규칙 기반 short_name 생성 (AI 없이)"""
    cleaned = re.sub(r"[\(\)\[\]\{\}/\\,~·]", " ", name or "")
    tokens = [t for t in cleaned.split() if t and not re.match(r"^[A-Z0-9\-]+\d", t)]
    tokens = [t for t in tokens if not re.fullmatch(r"\d+[가-힣]?", t)]
    return " ".join(tokens[:3])[:30]


# ─────────────────────────────────────────────────────────────
# 섹션 1: 무결성 체크 + registry 자동 수정
# ─────────────────────────────────────────────────────────────

def run_integrity_check(feed: list[dict]) -> bool:
    """
    1. product_registry의 short_name 이상값 자동 수정
    2. feed_posts의 post_text 잘림 경고
    반환: registry 수정 여부
    """
    print("\n" + "=" * 70, flush=True)
    print("무결성 재점검", flush=True)
    print("=" * 70, flush=True)

    # ── 1. registry short_name 체크 ──────────────────────────────────────
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        reg = json.load(f)

    fixes = []
    for v in reg["products"].values():
        if not v.get("posted") or v.get("removed"):
            continue
        code = v["code"]
        short_name = v.get("short_name", "")
        name = v.get("name", "")

        if len(short_name) < 2:
            new_sn = _fallback_short_name(name)
            v["short_name"] = new_sn
            fixes.append(f"  [{code}] short_name 수정: {short_name!r} → {new_sn!r}")

    if fixes:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        print(f"\n[short_name 자동 수정] {len(fixes)}건:", flush=True)
        for msg in fixes:
            print(msg, flush=True)
    else:
        print("\n[short_name] 이상 없음", flush=True)

    # ── 2. post_text 잘림 체크 ────────────────────────────────────────────
    truncated = []
    for p in feed:
        if p.get("status") != "posted":
            continue
        text = p.get("post_text", "")
        if text and _is_truncated(text):
            code = p.get("product_code", "?")
            preview = text.replace('\n', ' ')[-50:]
            truncated.append(f"  [{code}] ...{preview}")

    if truncated:
        print(f"\n[post_text 잘림 의심] {len(truncated)}건:", flush=True)
        for msg in truncated:
            print(msg, flush=True)
        print("  → 앱에서 직접 수정 필요 (Threads API 편집 미지원)", flush=True)
    else:
        print("[post_text] 잘림 이상 없음", flush=True)

    return bool(fixes)


# ─────────────────────────────────────────────────────────────
# 섹션 2: Threads API ↔ feed 매칭 검증
# ─────────────────────────────────────────────────────────────

def run_threads_verify(feed: list[dict]) -> None:
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        print("THREADS_ACCESS_TOKEN/USER_ID 없음 — Threads 검증 생략", flush=True)
        return

    print("\n" + "=" * 70, flush=True)
    print("Threads 실제 게시 검증", flush=True)
    print("=" * 70, flush=True)

    my_posts = fetch_my_posts(limit=100)
    print(f"\nThreads API: {len(my_posts)}개 게시글 반환", flush=True)

    api_by_sc = {}
    for p in my_posts:
        sc = _shortcode(p.get("permalink", ""))
        if sc:
            api_by_sc[sc] = p

    posted = [p for p in feed if p.get("status") == "posted"]
    print(f"feed_posts(status=posted): {len(posted)}건", flush=True)

    feed_by_sc = {}
    feed_no_url = []
    for f in posted:
        sc = _shortcode(f.get("threads_url", ""))
        if sc:
            feed_by_sc[sc] = f
        else:
            feed_no_url.append(f)

    matched  = set(feed_by_sc) & set(api_by_sc)
    feed_only = set(feed_by_sc) - set(api_by_sc)
    api_only  = set(api_by_sc) - set(feed_by_sc)

    print(f"\n[매칭] feed↔API 매칭: {len(matched)}건", flush=True)
    print(f"[누락] feed에 있고 API에 없음: {len(feed_only)}건", flush=True)
    print(f"[추가] API에만 있고 feed에 없음: {len(api_only)}건", flush=True)
    print(f"[URL없음] threads_url 비어있음: {len(feed_no_url)}건", flush=True)

    if feed_only:
        print("\n--- 누락 글 (feed엔 있는데 Threads엔 없음) ---", flush=True)
        for sc in sorted(feed_only):
            f = feed_by_sc[sc]
            print(f"  [{f.get('product_code','?'):>4}] {sc}  {f.get('timestamp','')[:16]}  {f.get('product_name','')[:35]}", flush=True)

    if api_only:
        print("\n--- 추가 글 (Threads엔 있는데 feed엔 없음) ---", flush=True)
        for sc in sorted(api_only):
            p = api_by_sc[sc]
            text = (p.get('text') or '')[:60].replace('\n', ' ')
            print(f"  {sc}  {text}", flush=True)

    # 댓글 검증
    print("\n" + "=" * 70, flush=True)
    print("댓글(reply) 검증", flush=True)
    print("=" * 70, flush=True)

    if os.path.exists(REPLIED_PATH):
        replied = json.load(open(REPLIED_PATH, encoding="utf-8"))
        replied_set = set(replied) if isinstance(replied, list) else set(replied.keys())
        print(f"replied_comments: {len(replied_set)}개 기록", flush=True)
    else:
        replied_set = set()
        print("replied_comments.json 없음", flush=True)

    targets = [
        f for f in posted
        if f.get("product_code") and f.get("product_code") != "preview"
        and f.get("threads_url")
    ]
    print(f"댓글 대상(코드+URL 있음): {len(targets)}건", flush=True)

    no_comment = []
    for f in targets:
        sc = _shortcode(f.get("threads_url", ""))
        if not sc:
            continue
        api_id = api_by_sc.get(sc, {}).get("id", "")
        if api_id and api_id not in replied_set:
            no_comment.append((f, sc, api_id))

    print(f"\n댓글 누락(replied 기록 없음): {len(no_comment)}건", flush=True)
    for f, sc, api_id in no_comment:
        print(f"  [{f.get('product_code','?'):>4}] {sc}  api_id={api_id}  {f.get('product_name','')[:30]}", flush=True)

    # 최근 20개 reply 수
    print("\n" + "=" * 70, flush=True)
    print("최근 글 reply 수 (살아있는 글 최신 20개)", flush=True)
    print("=" * 70, flush=True)
    for sc in sorted(matched, key=lambda s: feed_by_sc[s].get('timestamp', ''), reverse=True)[:20]:
        f = feed_by_sc[sc]
        api_id = api_by_sc[sc].get("id", "")
        try:
            data = _api("GET", f"/{api_id}/replies", params={
                "fields": "id,text",
                "access_token": THREADS_ACCESS_TOKEN,
            })
            replies = data.get("data", [])
            sample = (replies[0].get("text") or "")[:40].replace('\n', ' ') if replies else ""
            print(f"  [{f.get('product_code','?'):>4}] {sc}  reply수={len(replies)}  샘플: {sample}", flush=True)
        except Exception as e:
            print(f"  [{f.get('product_code','?'):>4}] {sc}  조회실패: {e}", flush=True)


def main() -> None:
    feed = json.load(open(FEED_POSTS_PATH, encoding="utf-8"))

    registry_fixed = run_integrity_check(feed)
    run_threads_verify(feed)

    # CI에서 수정된 경우 exit code 2로 알림 (commit 필요)
    if registry_fixed:
        sys.exit(2)


if __name__ == "__main__":
    main()
