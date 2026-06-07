"""
상품 이미지 가공 → imgBB 업로드
원본 이미지 1장을 4가지 스타일로 가공:
  1) 원본 정방형 크롭
  2) 따뜻한 톤 (웜 필터)
  3) 밝고 선명한 버전
  4) 클로즈업 크롭 (중앙 75%)
실패 시 [] 반환 → 호출부에서 원본 이미지 유지
"""
import base64
import io
import logging
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")
logger = logging.getLogger("image_gen")


def _download_image(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 3000:
            return r.content
    except Exception as e:
        logger.warning(f"이미지 다운로드 실패: {e}")
    return None


def _make_variants(img_bytes: bytes) -> list[bytes]:
    """PIL로 이미지 4종 가공"""
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        logger.warning("Pillow 없음 — 원본만 반환")
        return [img_bytes]

    try:
        src = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = src.size
        size = min(w, h)

        def to_bytes(img: Image.Image) -> bytes:
            buf = io.BytesIO()
            img = img.resize((1080, 1080), Image.LANCZOS)
            img.save(buf, format="JPEG", quality=88)
            return buf.getvalue()

        # 1) 정방형 중앙 크롭
        left = (w - size) // 2
        top  = (h - size) // 2
        v1 = src.crop((left, top, left + size, top + size))

        # 2) 따뜻한 톤 (빨강·노랑 살짝 강조)
        v2 = v1.copy()
        r, g, b = v2.split()
        r = ImageEnhance.Brightness(r).enhance(1.08)
        g = ImageEnhance.Brightness(g).enhance(1.02)
        b = ImageEnhance.Brightness(b).enhance(0.90)
        v2 = Image.merge("RGB", (r, g, b))
        v2 = ImageEnhance.Contrast(v2).enhance(1.05)

        # 3) 밝고 선명
        v3 = ImageEnhance.Brightness(v1).enhance(1.15)
        v3 = ImageEnhance.Sharpness(v3).enhance(1.4)
        v3 = ImageEnhance.Color(v3).enhance(1.1)

        # 4) 클로즈업 (중앙 70% 크롭)
        margin = int(size * 0.15)
        v4 = v1.crop((margin, margin, size - margin, size - margin))

        return [to_bytes(v) for v in [v1, v2, v3, v4]]

    except Exception as e:
        logger.warning(f"이미지 가공 실패: {e}")
        return [img_bytes]


def _upload_imgbb(img_bytes: bytes) -> str | None:
    try:
        b64 = base64.b64encode(img_bytes).decode()
        r = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["data"]["url"]
        logger.warning(f"imgBB 오류: {r.status_code}")
    except Exception as e:
        logger.warning(f"imgBB 업로드 실패: {e}")
    return None


def generate_and_upload_images(product: dict, post_text: str = "") -> list[str]:
    """
    상품 이미지 다운로드 → 4종 스타일 가공 → imgBB 업로드 → URL 목록 반환.
    IMGBB_API_KEY 없거나 전체 실패 시 [] 반환.
    """
    if not IMGBB_API_KEY:
        logger.info("IMGBB_API_KEY 없음 → 이미지 가공 건너뜀")
        return []

    image_url = product.get("image_url", "")
    if not image_url:
        logger.warning("상품 이미지 URL 없음")
        return []

    logger.info(f"상품 이미지 다운로드: {image_url[:60]}...")
    img_bytes = _download_image(image_url)
    if not img_bytes:
        return []

    variants = _make_variants(img_bytes)
    logger.info(f"이미지 {len(variants)}종 가공 완료 → imgBB 업로드 중...")

    result = []
    for i, v in enumerate(variants):
        url = _upload_imgbb(v)
        if url:
            result.append(url)
            logger.info(f"  업로드 완료 ({i+1}/{len(variants)}): {url[:55]}...")
        else:
            logger.warning(f"  업로드 실패 ({i+1})")

    logger.info(f"이미지 처리 결과: {len(result)}장 성공 / {len(variants)}장 시도")
    return result
