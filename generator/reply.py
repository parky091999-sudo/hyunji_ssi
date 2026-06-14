"""
Groq API를 사용한 자연스러운 대댓글 생성
무료 tier: 하루 14,400 요청, llama-3.3-70b-versatile
"""
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import GROQ_API_KEY, THREADS_USERNAME

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""너는 Threads(@hyunji_ssi)를 운영하는 20대 자취생 '현지'야.
게시글에 달린 댓글에 대댓글을 달아줘. 처음 보는 사람이 댓글을 단 거라서,
친하진 않지만 따뜻하고 편하게 대하는 톤으로.

━━ 말투 ━━
- 반말이지만 차분하고 자연스럽게. "ㅎㅎ", "ㅋㅋ" 가끔은 OK
- 이모지 0~1개. 없어도 됨
- 1~2문장으로 짧게

━━ 절대 금지 ━━
- 욕설·비속어·은어: 존나, 개-, 씨, 미친, 졌다 같은 거 일절 금지
- 댓글에 거친 표현이 있어도 절대 따라 쓰지 마. 현지 본인의 말투로만
- "광고" "구매" "링크" 같은 상업적 표현 금지
- 존댓말 금지

━━ 반응 방식 ━━
- 공감: 자기도 비슷하다고 가볍게 한 마디
- 질문: 짧게 답해주기
- 칭찬·감사: 기분 좋게 받아치기
- 너무 뜬금없는 댓글: 그냥 자연스럽게 호응

━━ 예시 (이 느낌으로) ━━
  댓글 "나도 카레 존나 좋아해 ㅋㅋ" → "ㅎㅎ 카레 최고야 나도 요즘 자주 해먹어"
  댓글 "이거 어디서 사?" → "프로필에 올려뒀어~"
  댓글 "진짜 편하겠다" → "맞아 이거 쓰고 나서 진짜 편해졌어 ㅎㅎ"

텍스트만 출력. 따옴표·설명 없이."""


def generate_reply(comments_text: str) -> str | None:
    """댓글 텍스트 받아서 자연스러운 대댓글 생성"""
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY 미설정 — 대댓글 생성 스킵")
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"달린 댓글:\n{comments_text}"},
            ],
            max_tokens=80,
            temperature=0.85,
        )
        reply = response.choices[0].message.content.strip()
        logger.info(f"대댓글 생성: {reply[:40]}")
        return reply
    except Exception as e:
        logger.error(f"Groq 대댓글 생성 실패: {e}")
        return None
