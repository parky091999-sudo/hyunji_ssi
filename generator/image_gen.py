"""
상품 이미지를 Gemini(gemini-3.1-flash-image)로 보조 컷 2장 생성 → imgBB 업로드
  - 메인은 원본 image_url(쿠팡/네이버 상세) 사용 — 호출부에서 첫 자리 유지
  - 보조 컷 1: 3/4 비스듬 각도 + 옅은 그라데이션 배경 (제품 디테일)
  - 보조 컷 2: 사용 환경 컷 (제품을 실제 공간에 자연스럽게 배치)
실패 시 부분 성공한 URL만 반환 → 호출부에서 가용 이미지로 게시

설계 메모:
  - 원본 메인 사진이 직관적이고 깔끔하다는 운영자 피드백(2026-06-12, [017]) 반영.
  - [019][020] 흰 배경 단조로움 피드백(2026-06-13) → 사용 환경 컷 추가.
    제품 외형은 보존하되 자연스러운 공간 컨텍스트로 배경 다양성 확보.
"""
import base64
import io
import logging
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
IMGBB_API_KEY  = os.getenv("IMGBB_API_KEY", "")
logger = logging.getLogger("image_gen")

_PROMPTS = [
    (
        "이 이미지의 핵심 제품을 약 30~45도 비스듬한 각도(3/4 뷰)에서 본 전문 제품 사진으로 만들어줘. "
        "입체감과 깊이가 드러나는 구도 — 원본 정면 컷과는 시점이 명확히 달라야 함. "
        "다음은 반드시 완전히 제거해야 해 — 한 글자도 남기지 마: "
        "한국어/중국어/일본어/영어 글자, 치수 표기, 사이즈 라벨, 설명 문구, 가격표, 화살표, "
        "비교표, 인포그래픽, 워터마크, 로고에 포함된 글자, 제품 위/주변에 적힌 모든 텍스트. "
        "제품의 형태·색상·재질은 원본과 동일하게 유지하고, 배경은 부드러운 연회색에서 흰색으로 "
        "이어지는 그라데이션, 바닥에 자연스러운 옅은 그림자. 결과는 입체감 있는 제품 컷 한 장."
    ),
    (
        "이 이미지의 핵심 제품을 실제 사용되는 자연스러운 공간 컷으로 배치해줘. "
        "제품 카테고리에 어울리는 한국 가정·사무실 환경 — 예: 주방 제품은 깔끔한 주방 카운터, "
        "욕실 제품은 화이트 톤 욕실, 거실 가전은 따뜻한 우드/패브릭 톤 거실, 휴대 제품은 책상 위 "
        "또는 여행 가방 옆. 자연광 또는 부드러운 실내조명, 따뜻하고 사실적인 분위기. "
        "제품 자체의 형태·색상·재질·로고는 원본과 100% 동일하게 유지 — 형태 왜곡·색상 변경·신규 부품 추가 절대 금지. "
        "제품은 화면 중앙~중앙 약간 측면에 자연스럽게 배치하고, 주변 소품은 1~2개로 최소화. "
        "다음은 반드시 제거: 한국어/중국어/일본어/영어 글자, 치수·가격·설명 문구, 워터마크, "
        "비교표, 인포그래픽, 제품 위/주변 모든 텍스트. 결과는 제품이 분명히 주인공인 라이프스타일 컷."
    ),
]


def _download_image(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 3000:
            return r.content
    except Exception as e:
        logger.warning(f"이미지 다운로드 실패: {e}")
    return None


def _to_clean_jpeg(img_bytes: bytes) -> bytes:
    """Gemini 출력 바이트를 표준 JPEG으로 강제 재인코딩.

    Threads API가 imgBB의 비표준 컨테이너(WebP/PNG with alpha 등) fetch에
    실패하는 문제(2207052/2207083) 회피용. PIL로 RGB 변환 후 quality=92 JPEG.
    """
    from PIL import Image
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def _upload_imgbb(img_bytes: bytes) -> str | None:
    try:
        b64 = base64.b64encode(img_bytes).decode()
        r = requests.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": IMGBB_API_KEY,
                "image": b64,
                # 명시적 .jpg 확장자 — Threads가 Content-Type/URL 모두 jpg로 인식
                "name": f"hyunji_{int(time.time())}",
            },
            timeout=30,
        )
        if r.status_code == 200:
            d = r.json()["data"]
            # url = 원본 직접 URL (확장자 보존). display_url은 변환 거치는 경우 있어 회피.
            return d.get("url") or d.get("display_url")
        logger.warning(f"imgBB 오류: {r.status_code}")
    except Exception as e:
        logger.warning(f"imgBB 업로드 실패: {e}")
    return None


def generate_and_upload_images(product: dict, post_text: str = "") -> list[str]:
    """
    상품 이미지 다운로드 → Gemini로 _PROMPTS 개수만큼 변형 → imgBB 업로드 → URL 목록.
    키 없거나 전체 실패 시 [] 반환. 부분 성공 시 성공한 URL만 반환.
    """
    if not GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY 없음 → 이미지 생성 건너뜀")
        return []
    if not IMGBB_API_KEY:
        logger.info("IMGBB_API_KEY 없음 → 이미지 생성 건너뜀")
        return []

    try:
        from google import genai
        from google.genai import types
        from PIL import Image
    except ImportError as e:
        logger.warning(f"패키지 없음: {e}")
        return []

    image_url = product.get("image_url", "")
    if not image_url:
        logger.warning("상품 이미지 URL 없음")
        return []

    logger.info(f"상품 이미지 다운로드: {image_url[:60]}...")
    img_bytes = _download_image(image_url)
    if not img_bytes:
        return []

    try:
        pil_image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as e:
        logger.warning(f"이미지 열기 실패: {e}")
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)
    results = []

    for i, prompt in enumerate(_PROMPTS):
        try:
            logger.info(f"  이미지 {i+1}/{len(_PROMPTS)} 생성 중...")
            response = client.models.generate_content(
                model="gemini-3.1-flash-image",
                contents=[prompt, pil_image],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                ),
            )
            for part in response.parts:
                if getattr(part, "thought", False):
                    continue
                if part.inline_data is not None:
                    raw = part.inline_data.data
                    img_bytes = base64.b64decode(raw) if isinstance(raw, str) else raw
                    # Gemini 출력은 컨테이너 형식이 들쭉날쭉(WebP/PNG with alpha 등) — Threads가
                    # imgBB의 비표준 형식 fetch에 실패해 carousel 0/N으로 폴백되는 버그 회피.
                    try:
                        img_bytes = _to_clean_jpeg(img_bytes)
                    except Exception as e:
                        logger.warning(f"  JPEG 재인코딩 실패, 원본 업로드 시도: {e}")
                    url = _upload_imgbb(img_bytes)
                    if url:
                        results.append(url)
                        logger.info(f"  업로드 완료 ({i+1}): {url[:55]}...")
                    break
        except Exception as e:
            logger.warning(f"  이미지 {i+1} 생성 실패: {e}")

    logger.info(f"이미지 생성 결과: {len(results)}장 성공 / {len(_PROMPTS)}장 시도")
    return results
