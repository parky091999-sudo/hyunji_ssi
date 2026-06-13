"""
Dry-run 미리보기 — Threads 피드 스타일
실제 쓰레드에 포스팅하지 않고, 생성될 콘텐츠를 브라우저에서 확인
"""
import os
import sys
import webbrowser
import tempfile
from datetime import datetime

sys.path.append(os.path.dirname(__file__))

PREVIEW_MAX = 5  # 미리보기 전용 상품 수 (실제 운영과 무관)
PREVIEW_SOURCE = "youtube"  # "youtube" | "naver" — 상품 수집 소스


def _sample_engager_comments() -> list[dict]:
    from config import GROQ_API_KEY
    if not GROQ_API_KEY:
        return []

    sample_posts = [
        {"keyword": "주방꿀템",      "text": "이거 진짜 신기함… 계란 껍질 스트레스 없이 한 번에 벗겨짐 🥚 아침에 삶은계란 먹는 사람들은 무조건 편함 궁금하면 댓글에 링크 남겨둘게! #쿠팡추천템 #살림템 #주방꿀템"},
        {"keyword": "생활꿀템",      "text": "쌀 씻다가 쌀알 흘려보신 분? 물만 틀면 자동으로 빙글빙글 돌아가서 쌀알 하나도 안 빠져요 ㅋㅋ 전기세 0원. 가격 커피 한 잔 값."},
        {"keyword": "신기한생활용품", "text": "인생 다이소템 뭐야? 다들 딱 1개만 추천해줘! 나는 이거 절대 천원 퀄리티 아님 수분감 미쳤고 완전 내 인생템!!"},
    ]

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        system = (
            "너는 Threads SNS를 즐겨 쓰는 평범한 한국인이야. "
            "생활용품·주방·살림 관련 게시글을 보고 진짜 사람처럼 자연스럽게 반응하는 댓글을 달아.\n"
            "- 반말, 친근하게\n"
            "- 게시글 내용의 구체적인 제품/상황 언급\n"
            "- 최소 12자, 최대 40자\n"
            "- 감탄사만으로 끝내지 말 것\n"
            "- 댓글만 출력. 따옴표 없이."
        )
        results = []
        for sp in sample_posts:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"다음 게시글에 댓글 1개 작성:\n\n{sp['text']}"},
                ],
                max_tokens=80, temperature=0.85,
            )
            comment = resp.choices[0].message.content.strip().strip('"\'""''')
            results.append({
                "keyword": sp["keyword"],
                "post_preview": sp["text"][:55] + "...",
                "comment": comment,
            })
        return results
    except Exception as e:
        return [{"keyword": "오류", "post_preview": "", "comment": f"Groq 연결 실패: {e}"}]


def _post_card(image_url: str, text: str, label: str = "") -> str:
    img_html = (
        f'<div class="post-img"><img src="{image_url}" alt=""></div>'
        if image_url else ""
    )
    label_html = f'<div class="post-label-badge">{label}</div>' if label else ""
    text_html = text.replace("\n", "<br>")
    return f"""
    <div class="post-card">
      {label_html}
      <div class="post-header">
        <div class="avatar-wrap">
          <div class="avatar">꿀<br>픽</div>
          <div class="thread-line"></div>
        </div>
        <div class="post-body-wrap">
          <div class="post-meta">
            <span class="username">kkul.pick.kr</span>
            <span class="dot">·</span>
            <span class="timestamp">방금</span>
            <span class="more">···</span>
          </div>
          <div class="post-text">{text_html}</div>
          {img_html}
          <div class="post-actions">
            <span>♡</span>
            <span>💬</span>
            <span>↺</span>
            <span>✈</span>
          </div>
        </div>
      </div>
    </div>"""


def _inpock_guide(contents: list[dict]) -> str:
    """인포크링크 등록 가이드 — 각 상품의 코드·이름·URL 목록"""
    rows = ""
    for c in contents:
        product = c["product"]
        code = c.get("product_code", "?")
        name = product.get("name", "")[:50]
        url = product.get("product_url", "")
        rows += f"""
        <tr>
          <td>[{code}]</td>
          <td>{name}</td>
          <td><a href="{url}" target="_blank" style="color:#f8c93a;font-size:11px">쿠팡 링크</a></td>
        </tr>"""
    return f"""
    <div class="inpock-guide">
      <div class="section-label" style="padding:20px 16px 10px">인포크 등록 목록</div>
      <div style="padding:0 16px 20px;font-size:12px;color:#888">
        아래 상품들을 <b style="color:#f8c93a">link.inpock.co.kr</b> 에 코드 순서대로 등록하세요
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead>
          <tr style="color:#555;border-bottom:1px solid #222">
            <th style="text-align:left;padding:6px 16px">코드</th>
            <th style="text-align:left;padding:6px 8px">상품명</th>
            <th style="text-align:left;padding:6px 8px">링크</th>
          </tr>
        </thead>
        <tbody style="color:#ccc">{rows}</tbody>
      </table>
    </div>"""


def generate_html(contents: list[dict], engager_samples: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    feed_html = ""
    for i, c in enumerate(contents, 1):
        product = c["product"]
        name = product.get("name", "")
        image_url = product.get("image_url", "")
        style = c.get("style", "")
        code = c.get("product_code", "")

        yt = product.get("youtube_source")
        yt_info = f' · YT {yt["views"]:,}회' if yt else ""
        code_info = f' · [{code}]' if code else ""
        feed_html += f'<div class="product-group"><div class="product-divider">상품 {i}{code_info} · {name[:35]} · [{style}]{yt_info}</div>'
        feed_html += _post_card(image_url, c["post_text_1"])
        feed_html += "</div>"

    engager_html = ""
    for s in engager_samples:
        post_text = f'"{s["post_preview"]}"'
        engager_html += f"""
        <div class="post-card engager-post">
          <div class="engager-keyword">검색 키워드: #{s['keyword']}</div>
          <div class="post-header">
            <div class="avatar-wrap">
              <div class="avatar other">타<br>계</div>
            </div>
            <div class="post-body-wrap">
              <div class="post-meta">
                <span class="username">타계정</span>
                <span class="dot">·</span>
                <span class="timestamp">1시간</span>
              </div>
              <div class="post-text engager-preview-text">{post_text}</div>
            </div>
          </div>
          <div class="reply-row">
            <div class="reply-avatar-wrap">
              <div class="avatar small">현지</div>
            </div>
            <div class="reply-bubble">
              <span class="username">hyunji_ssi</span>
              <div class="reply-text">{s['comment']}</div>
            </div>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>현지의 zip 미리보기 · {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    background: #000;
    color: #fff;
    max-width: 640px;
    margin: 0 auto;
    min-height: 100vh;
  }}

  /* 탭 네비게이션 */
  .topbar {{
    position: sticky; top: 0; z-index: 10;
    background: rgba(0,0,0,0.9);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid #222;
  }}
  .topbar-row {{
    padding: 14px 16px 0;
    display: flex; justify-content: space-between; align-items: center;
  }}
  .topbar-logo {{ font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
  .topbar-meta {{ font-size: 11px; color: #666; }}
  .tab-nav {{
    display: flex;
    border-top: 1px solid #1a1a1a;
    margin-top: 10px;
  }}
  .tab-btn {{
    flex: 1;
    padding: 10px;
    background: none;
    border: none;
    color: #555;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all .15s;
  }}
  .tab-btn.active {{
    color: #fff;
    border-bottom-color: #f5a623;
  }}

  /* 탭 패널 */
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  /* 링크인바이오 iframe */
  .linkbio-frame {{
    width: 100%;
    height: calc(100vh - 100px);
    border: none;
    display: block;
  }}

  /* 섹션 타이틀 */
  .section-label {{
    font-size: 11px; color: #555; font-weight: 600;
    padding: 20px 16px 6px;
    text-transform: uppercase; letter-spacing: 0.08em;
  }}

  /* 상품 그룹 */
  .product-group {{ border-bottom: 8px solid #111; }}
  .product-divider {{
    font-size: 11px; color: #444;
    padding: 10px 16px 4px;
    background: #0a0a0a;
  }}

  /* 게시글 카드 */
  .post-card {{
    padding: 14px 16px 8px;
    border-bottom: 1px solid #1a1a1a;
    position: relative;
  }}
  .post-label-badge {{
    font-size: 10px; color: #888;
    margin-bottom: 8px;
    padding-left: 52px;
  }}
  .post-header {{
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }}
  .avatar-wrap {{
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
  }}
  .avatar {{
    width: 40px; height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, #f8c93a, #f5a623);
    display: flex; align-items: center; justify-content: center;
    font-size: 9px; font-weight: 800; color: #fff;
    text-align: center; line-height: 1.2;
    flex-shrink: 0;
  }}
  .avatar.other {{
    background: linear-gradient(135deg, #555, #333);
    font-size: 8px;
  }}
  .avatar.small {{
    width: 30px; height: 30px;
    font-size: 7px;
    background: linear-gradient(135deg, #f8c93a, #f5a623);
  }}
  .thread-line {{
    width: 2px;
    background: #2a2a2a;
    flex: 1;
    min-height: 20px;
    margin-top: 6px;
  }}
  .post-body-wrap {{ flex: 1; min-width: 0; }}
  .post-meta {{
    display: flex; align-items: center; gap: 4px;
    margin-bottom: 6px;
  }}
  .username {{ font-size: 14px; font-weight: 700; color: #fff; }}
  .dot {{ color: #555; font-size: 12px; }}
  .timestamp {{ font-size: 13px; color: #666; }}
  .more {{ margin-left: auto; color: #555; font-size: 18px; letter-spacing: 2px; cursor: pointer; }}
  .post-text {{
    font-size: 15px; line-height: 1.55;
    color: #f0f0f0;
    white-space: pre-wrap;
    word-break: break-word;
    margin-bottom: 10px;
  }}
  .post-img {{
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 10px;
    max-height: 320px;
  }}
  .post-img img {{
    width: 100%; height: 320px;
    object-fit: cover; display: block;
  }}
  .post-actions {{
    display: flex; gap: 16px;
    font-size: 20px; color: #666;
    padding: 4px 0 8px;
  }}
  .post-actions span {{ cursor: pointer; }}
  .post-actions span:hover {{ color: #fff; }}

  .engager-post {{ background: #0a0a0a; }}
  .engager-keyword {{ font-size: 11px; color: #555; padding-bottom: 8px; }}
  .engager-preview-text {{ color: #666 !important; font-style: italic; font-size: 14px !important; }}
  .reply-row {{
    display: flex; gap: 10px;
    align-items: flex-start;
    padding: 10px 0 4px 52px;
  }}
  .reply-avatar-wrap {{ flex-shrink: 0; }}
  .reply-bubble {{ flex: 1; }}
  .reply-bubble .username {{ font-size: 13px; }}
  .reply-text {{ font-size: 14px; color: #e0e0e0; margin-top: 2px; line-height: 1.4; }}

  .footer {{ text-align: center; padding: 40px 16px; font-size: 11px; color: #333; }}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-row">
    <div class="topbar-logo">현지의 zip 미리보기</div>
    <div class="topbar-meta">실제 미게시 · {now}</div>
  </div>
  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('feed', this)">Threads 피드</button>
    <button class="tab-btn" onclick="switchTab('linkbio', this)">링크인바이오</button>
  </div>
</div>

<!-- 탭 1: Threads 피드 -->
<div id="tab-feed" class="tab-panel active">
  <div class="section-label">포스팅 예정 · {len(contents)}개 상품</div>
  {feed_html}
  {_inpock_guide(contents)}
  <div class="section-label">Engager 댓글 샘플</div>
  {engager_html if engager_html else '<div style="color:#444;font-size:13px;padding:16px">GROQ_API_KEY 없음</div>'}
  <div class="footer">Dry-run · Threads에 실제 업로드되지 않았습니다</div>
</div>

<!-- 탭 2: 링크인바이오 -->
<div id="tab-linkbio" class="tab-panel">
  <iframe class="linkbio-frame" src="docs/index.html"></iframe>
</div>

<script>
  function switchTab(id, btn) {{
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + id).classList.add('active');
    btn.classList.add('active');
  }}
</script>
</body>
</html>"""


def run_preview():
    from generator.content import generate_posts_batch

    print(f"상품 수집 중... [{PREVIEW_SOURCE}]")
    if PREVIEW_SOURCE == "youtube":
        from config import YOUTUBE_API_KEY
        if not YOUTUBE_API_KEY:
            print("  ⚠ YOUTUBE_API_KEY 없음 → 네이버로 대체")
            from scraper.naver_shopping import scrape_deals
            products = scrape_deals(max_items=PREVIEW_MAX)
        else:
            from scraper.youtube_trending import scrape_trending_products
            products = scrape_trending_products(max_items=PREVIEW_MAX)
            if len(products) < PREVIEW_MAX:
                # YouTube로 부족하면 네이버로 보충
                from scraper.naver_shopping import scrape_deals
                extra = scrape_deals(max_items=PREVIEW_MAX - len(products))
                products.extend(extra)
    else:
        from scraper.naver_shopping import scrape_deals
        products = scrape_deals(max_items=PREVIEW_MAX)

    if not products:
        print("수집된 상품 없음")
        return
    print(f"  → {len(products)}개 수집")

    print("AI 콘텐츠 생성 중...")
    contents = generate_posts_batch(products)
    print(f"  → {len(contents)}개 생성")

    print("Engager 댓글 샘플 생성 중...")
    engager_samples = _sample_engager_comments()
    print(f"  → {len(engager_samples)}개 샘플")

    print("링크인바이오 페이지 생성 중...")
    import generate_page
    generate_page.main()
    print(f"  → docs/index.html 생성 완료")

    html = generate_html(contents, engager_samples)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", encoding="utf-8",
        delete=False,
        dir=os.path.dirname(__file__),
        prefix="preview_",
    )
    tmp.write(html)
    tmp.close()

    print(f"\n파일: {tmp.name}")
    webbrowser.open(f"file:///{tmp.name.replace(os.sep, '/')}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    run_preview()
