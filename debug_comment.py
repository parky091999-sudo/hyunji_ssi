"""
댓글 입력 과정 디버그 - 각 단계 스크린샷 저장
실행: python debug_comment.py
"""
import asyncio
import json
import os
from playwright.async_api import async_playwright

COOKIE_PATH = os.path.join(os.path.dirname(__file__), "data", "threads_cookies.json")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
THREADS_URL = "https://www.threads.com"

# 방금 올라간 포스트 URL (최신 것으로 교체)
POST_URL = "https://www.threads.com/@kkul.pick.kr/post/DYyYdSeElt1"

TEST_COMMENT = "\n".join([
    "🛒 구매 링크는 여기!",
    "👇 46% 할인 (11,720원)",
    "https://www.coupang.com/vp/products/8153054092?vendorItemId=90243050105",
    "",
    "💡 파트너스 활동을 통해 일정액의 수수료를 제공받습니다.",
])


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )

        with open(COOKIE_PATH) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)

        page = await context.new_page()

        # 1. 포스트 페이지 이동
        print(f"\n[1] 포스트 페이지 이동: {POST_URL}")
        await page.goto(POST_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=os.path.join(DATA_DIR, "comment_01_post_page.png"))
        print("  스크린샷: comment_01_post_page.png")

        # 2. 댓글 입력창 탐색
        print("\n[2] 댓글 입력창 탐색...")
        selectors = [
            "[placeholder*='답글']",
            "[placeholder*='Reply']",
            "[aria-label*='답글']",
            "[aria-label*='reply']",
            "div[role='textbox']",
            "[contenteditable='true']",
        ]
        for sel in selectors:
            els = await page.query_selector_all(sel)
            if els:
                print(f"  [FOUND] {sel} → {len(els)}개")
                for i, el in enumerate(els[:3]):
                    try:
                        aria = await el.get_attribute("aria-label") or ""
                        ph = await el.get_attribute("placeholder") or ""
                        txt = (await el.inner_text())[:30]
                        print(f"    [{i}] aria='{aria[:40]}' placeholder='{ph[:40]}' text='{txt}'")
                    except Exception:
                        pass
            else:
                print(f"  [MISS]  {sel}")

        # 3. 첫 번째 textbox 클릭
        print("\n[3] div[role='textbox'] 클릭...")
        el = await page.query_selector("div[role='textbox']")
        if el:
            await el.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=os.path.join(DATA_DIR, "comment_02_clicked.png"))
            print("  클릭 후 스크린샷: comment_02_clicked.png")
        else:
            print("  [ERROR] textbox 없음")
            await browser.close()
            return

        # 4. 한 줄씩 입력 (Shift+Enter로 줄바꿈)
        print("\n[4] 댓글 입력 (Shift+Enter 방식)...")
        lines = TEST_COMMENT.split("\n")
        print(f"  총 {len(lines)}줄 입력 예정")
        for i, line in enumerate(lines):
            if line:
                await page.keyboard.type(line, delay=30)
                print(f"  [{i}] 입력: '{line[:50]}'")
            else:
                print(f"  [{i}] 빈줄")
            if i < len(lines) - 1:
                await page.keyboard.press("Shift+Enter")
                await page.wait_for_timeout(200)

        await page.wait_for_timeout(1000)
        await page.screenshot(path=os.path.join(DATA_DIR, "comment_03_typed.png"))
        print("  입력 후 스크린샷: comment_03_typed.png")

        # 5. 현재 textbox 내용 확인
        print("\n[5] 입력된 내용 확인...")
        el = await page.query_selector("div[role='textbox']")
        if el:
            content = await el.inner_text()
            print(f"  textbox 내용:\n---\n{content}\n---")

        # 6. 게시 버튼 탐색
        print("\n[6] 댓글 게시 버튼 탐색...")
        post_btn = page.get_by_role("button", name="게시", exact=True)
        count = await post_btn.count()
        print(f"  '게시' 버튼 {count}개 발견")

        print("\n  ★ 5초 후 게시 버튼 클릭합니다. 화면 확인하세요.")
        await page.wait_for_timeout(5000)

        if count > 0:
            await post_btn.last.click()
            print("  게시 버튼 클릭!")
            await page.wait_for_timeout(3000)
            await page.screenshot(path=os.path.join(DATA_DIR, "comment_04_posted.png"))
            print("  게시 후 스크린샷: comment_04_posted.png")

        print("\n[완료] 5초 후 종료")
        await page.wait_for_timeout(5000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug())
