"""
KST 시간 게이트 — GitHub Actions 크론 지연(실측 7~12시간) 방어선.

크론이 언제 도착하든 도착 시점의 KST 기준으로:
- 허용창 안이면 즉시 통과
- 창 시작 전이면 시작 시각까지 대기 (max_wait_h 이내일 때만)
- 그 외(새벽 등)는 이번 실행 생략 → 다음 크론에 위임

schedule 이벤트에만 적용. workflow_dispatch(수동 실행)·로컬은 사람 의도이므로 무조건 통과.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
logger = logging.getLogger("post_gate")


def _decide(window_start: float, window_end: float, max_wait_h: float,
            label: str, now: datetime | None):
    """(통과여부, 대기초) 반환"""
    if os.getenv("GITHUB_EVENT_NAME", "") != "schedule":
        return True, 0.0
    now = now or datetime.now(KST)
    h = now.hour + now.minute / 60
    if window_start <= h < window_end:
        return True, 0.0
    if h < window_start:
        wait_h = window_start - h
        if 0 < wait_h <= max_wait_h:
            logger.info(f"[{label}] KST {now:%H:%M} 도착 — {int(window_start):02d}:00까지 {wait_h*60:.0f}분 대기 후 게시")
            return True, wait_h * 3600
        logger.info(f"[{label}] KST {now:%H:%M} 도착 — 창 시작까지 {wait_h:.1f}h(상한 {max_wait_h}h 초과) → 생략")
        return False, 0.0
    logger.info(f"[{label}] KST {now:%H:%M} 도착 — 허용창 {int(window_start)}~{int(window_end)}시 밖 → 생략")
    return False, 0.0


async def kst_gate(window_start: float, window_end: float, max_wait_h: float = 0.0,
                   label: str = "", now: datetime | None = None) -> bool:
    ok, wait = _decide(window_start, window_end, max_wait_h, label, now)
    if ok and wait:
        await asyncio.sleep(wait)
    return ok


def kst_gate_sync(window_start: float, window_end: float, max_wait_h: float = 0.0,
                  label: str = "", now: datetime | None = None) -> bool:
    ok, wait = _decide(window_start, window_end, max_wait_h, label, now)
    if ok and wait:
        time.sleep(wait)
    return ok
