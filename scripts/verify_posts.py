"""
실제 Threads 게시 검증 (1회성 진단).

feed_posts.json의 status=posted 항목과 Threads Graph API의 실제 게시 목록을
shortcode 기준으로 매칭해서:
  - 살아있는 글
  - feed에는 있는데 Threads엔 없는 글 (게시 실패였지만 posted로 잘못 기록)
  - Threads엔 있는데 feed엔 없는 글
  - 댓글(reply) 상태
출력해서 진단.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from config import DATA_DIR
from poster.threads import _api, fetch_my_posts, THREADS_ACCESS_TOKEN, THREADS_USER_ID

FEED_POSTS_PATH = os.path.join(DATA_DIR, "feed_posts.json")
REPLIED_PATH    = os.path.join(DATA_DIR, "replied_comments.json")


def _shortcode(url: str) -> str:
    return url.rstrip("/").split("/post/")[-1] if url and "/post/" in url else ""


def main() -> None:
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        print("THREADS_ACCESS_TOKEN/USER_ID 없음 — 종료", flush=True)
        sys.exit(1)

    print("=" * 70, flush=True)
    print("Threads 실제 게시 검증", flush=True)
    print("=" * 70, flush=True)

    # 1) Threads API에서 내 게시글 받기
    my_posts = fetch_my_posts(limit=100)
    print(f"\nThreads API: {len(my_posts)}개 게시글 반환", flush=True)

    api_by_sc = {}
    for p in my_posts:
        sc = _shortcode(p.get("permalink", ""))
        if sc:
            api_by_sc[sc] = p

    # 2) feed_posts 로드
    feed = json.load(open(FEED_POSTS_PATH, encoding="utf-8"))
    posted = [p for p in feed if p.get("status") == "posted"]
    print(f"feed_posts(status=posted): {len(posted)}건", flush=True)

    # 3) 매칭
    feed_by_sc = {}
    feed_no_url = []
    for f in posted:
        sc = _shortcode(f.get("threads_url", ""))
        if sc:
            feed_by_sc[sc] = f
        else:
            feed_no_url.append(f)

    matched = set(feed_by_sc) & set(api_by_sc)
    feed_only = set(feed_by_sc) - set(api_by_sc)
    api_only  = set(api_by_sc) - set(feed_by_sc)

    print(f"\n[매칭] feed↔API 매칭: {len(matched)}건", flush=True)
    print(f"[누락] feed에 있고 API에 없음: {len(feed_only)}건", flush=True)
    print(f"[추가] API에만 있고 feed에 없음: {len(api_only)}건", flush=True)
    print(f"[URL없음] feed에 threads_url 비어있음: {len(feed_no_url)}건", flush=True)

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

    # 4) 댓글 검증
    print("\n" + "=" * 70, flush=True)
    print("댓글(reply) 검증", flush=True)
    print("=" * 70, flush=True)

    if os.path.exists(REPLIED_PATH):
        replied = json.load(open(REPLIED_PATH, encoding="utf-8"))
        if isinstance(replied, list):
            replied_set = set(replied)
        else:
            replied_set = set(replied.keys())
        print(f"replied_comments: {len(replied_set)}개 기록", flush=True)
    else:
        replied_set = set()
        print("replied_comments.json 없음", flush=True)

    # 댓글 단 대상 = product_code 있고 threads_url 있고 removed 아님
    targets = [
        f for f in posted
        if f.get("product_code") and f.get("product_code") != "preview"
        and f.get("threads_url")
    ]
    print(f"댓글 대상(코드+URL 모두 있음): {len(targets)}건", flush=True)

    # API id ↔ shortcode 매핑 후 replied 검사
    no_comment = []
    for f in targets:
        sc = _shortcode(f.get("threads_url", ""))
        if not sc:
            continue
        api_id = api_by_sc.get(sc, {}).get("id", "")
        if api_id and api_id not in replied_set:
            no_comment.append((f, sc, api_id))

    print(f"\n댓글 누락(대상인데 replied 기록 없음): {len(no_comment)}건", flush=True)
    for f, sc, api_id in no_comment:
        print(f"  [{f.get('product_code','?'):>4}] {sc}  api_id={api_id}  {f.get('product_name','')[:30]}", flush=True)

    # 5) 각 API 글의 실제 reply 개수 조회
    print("\n" + "=" * 70, flush=True)
    print("Threads API 각 글의 실제 reply 수 (살아있는 글만)", flush=True)
    print("=" * 70, flush=True)
    for sc in sorted(matched, key=lambda s: feed_by_sc[s].get('timestamp',''), reverse=True)[:20]:
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


if __name__ == "__main__":
    main()
