"""
댓글 감지 및 자동 대댓글 — 6시간마다 실행
auto_post.py와 별개로 더 자주 댓글을 체크해 빠른 대응
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from config import LOG_DIR, THREADS_ACCESS_TOKEN

KST = timezone(timedelta(hours=9))

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "check_comments.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("check_comments")


async def run():
    logger.info("=" * 50)
    logger.info(f"댓글 체크 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    logger.info("=" * 50)

    if not THREADS_ACCESS_TOKEN:
        logger.warning("THREADS_ACCESS_TOKEN 미설정 — 건너뜀")
        return

    from poster.comment_replier import check_and_reply_comments
    try:
        await check_and_reply_comments()
    except Exception as e:
        logger.error(f"댓글 처리 오류: {e}")

    logger.info("댓글 체크 완료")


if __name__ == "__main__":
    asyncio.run(run())
