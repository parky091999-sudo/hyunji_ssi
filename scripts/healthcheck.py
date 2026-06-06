"""
헬스체크 — 오늘 자동 포스팅 여부 확인 → 없으면 auto_post.py 재실행
매일 17:00 KST (08:00 UTC) 실행
"""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

KST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("healthcheck")


def check_today_posted() -> bool:
    feed_path = os.path.join(ROOT, "data", "feed_posts.json")
    if not os.path.exists(feed_path):
        return False
    today = datetime.now(KST).strftime("%Y-%m-%d")
    with open(feed_path, encoding="utf-8") as f:
        feed = json.load(f)
    return any(
        p.get("timestamp", "")[:10] == today
        and p.get("post_type") == "auto"
        and p.get("status") == "posted"
        for p in feed
    )


if __name__ == "__main__":
    today = datetime.now(KST).strftime("%Y-%m-%d")
    logger.info(f"헬스체크 시작: {today}")

    if check_today_posted():
        logger.info("오늘 자동 포스팅 이미 완료 — 스킵")
        sys.exit(0)

    logger.info("오늘 자동 포스팅 없음 → 재실행 시작")
    os.environ["SKIP_DELAY"] = "true"
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "auto_post.py")]
    )
    sys.exit(result.returncode)
