"""
일상/일반 포스트 — 3일에 한 번 자동 포스팅
상품 링크 없이 계정 소개·일상 공감·생활 팁·질문글 등을 올려 팔로워 유입 유도
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from config import DATA_DIR, LOG_DIR, THREADS_ACCESS_TOKEN

TRACKER_PATH = os.path.join(DATA_DIR, "last_casual_post.json")
FEED_POSTS_PATH = os.path.join(DATA_DIR, "feed_posts.json")
INTERVAL_DAYS = 3

KST = timezone(timedelta(hours=9))

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "casual_post.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("casual_post")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _should_post() -> bool:
    tracker = _load_json(TRACKER_PATH, {})
    last_posted = tracker.get("last_posted_at")
    if not last_posted:
        return True
    last_dt = datetime.fromisoformat(last_posted)
    elapsed = datetime.now(KST) - last_dt.replace(tzinfo=KST) if last_dt.tzinfo is None else datetime.now(KST) - last_dt
    return elapsed.days >= INTERVAL_DAYS


def run():
    logger.info("=" * 50)
    logger.info(f"일상글 포스팅 체크: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    logger.info("=" * 50)

    if not _should_post():
        tracker = _load_json(TRACKER_PATH, {})
        logger.info(f"아직 {INTERVAL_DAYS}일 미경과 (마지막: {tracker.get('last_posted_at', '없음')}) — 건너뜀")
        return

    if not THREADS_ACCESS_TOKEN:
        logger.warning("THREADS_ACCESS_TOKEN 미설정 — 건너뜀")
        return

    logger.info(f"{INTERVAL_DAYS}일 경과 — 일상글 생성 시작")
    from generator.content import generate_general_post
    post_text = generate_general_post()

    if not post_text:
        logger.warning("일상글 생성 실패 — 종료")
        return

    logger.info(f"생성된 글:\n{post_text}")

    from poster.threads import post_thread_api
    from poster.comment_replier import add_recent_post

    try:
        result = post_thread_api(post_text=post_text, image_url=None, detail_images=None)
    except Exception as e:
        logger.error(f"포스팅 실패: {e}")
        result = None

    now_str = datetime.now(KST).isoformat()
    status = "posted" if result else "failed"

    if result:
        post_url = result.get("post_url")
        post_id = result.get("post_id")
        _save_json(TRACKER_PATH, {"last_posted_at": now_str})
        if post_url and post_id:
            add_recent_post(post_url, post_id, "story")
        logger.info(f"일상글 포스팅 완료: {post_url or '(URL 없음)'}")
    else:
        logger.warning("일상글 포스팅 실패")

    # feed_posts 기록
    feed = _load_json(FEED_POSTS_PATH, [])
    feed.insert(0, {
        "timestamp":    now_str,
        "product_code": "",
        "product_name": "[일상글]",
        "post_text":    post_text,
        "threads_url":  result.get("post_url") if result else None,
        "status":       status,
        "post_type":    "casual",
    })
    _save_json(FEED_POSTS_PATH, feed[:200])


if __name__ == "__main__":
    run()
