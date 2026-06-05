"""
비쿠팡 포스팅 삭제 전용 스크립트
환경변수: POST_ID (삭제할 Threads 게시글 ID)
데이터 정리는 이미 완료된 상태에서 게시글만 삭제하고 페이지 재생성
"""
import logging
import os
import sys

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("remove_post")


def run():
    post_id = os.getenv("POST_ID", "").strip()
    if not post_id:
        logger.error("POST_ID 환경변수 필요")
        sys.exit(1)

    token = os.getenv("THREADS_ACCESS_TOKEN", "")
    if not token:
        logger.error("THREADS_ACCESS_TOKEN 없음")
        sys.exit(1)

    logger.info(f"게시글 삭제: {post_id}")
    r = requests.delete(
        f"https://graph.threads.net/v1.0/{post_id}",
        params={"access_token": token},
        timeout=10, verify=False,
    )
    if r.status_code == 200:
        logger.info(f"  삭제 완료: {post_id}")
    else:
        logger.error(f"  삭제 실패: {r.status_code} {r.text[:200]}")
        sys.exit(1)

    try:
        import generate_page, generate_feed_page
        generate_page.main()
        generate_feed_page.main()
        logger.info("  페이지 재생성 완료")
    except Exception as e:
        logger.error(f"  페이지 생성 오류: {e}")

    logger.info("완료")


if __name__ == "__main__":
    run()
