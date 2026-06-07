"""
AI 이미지 생성
1순위: Together AI FLUX.1-schnell-Free (무료, CI 안정적) → imgBB 업로드
2순위: pollinations.ai → imgBB 업로드 (브라우저 환경에서만 신뢰)
실패 시 [] 반환 → 호출부에서 원본 이미지 유지
"""
import base64
import logging
import os
import sys
import time
from urllib.parse import quote

import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
from config import GOOGLE_API_KEY

IMGBB_API_KEY    = os.getenv("IMGBB_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
HF_TOKEN         = os.getenv("HF_TOKEN", "")

logger = logging.getLogger("image_gen")

CATEGORY_PROMPTS = {
    "뷰티": [
        "Korean LED facial mask skincare device, soft pink pastel studio lighting, cosmetic product photography, clean white background, 4k",
        "woman using face beauty device at home, Korean beauty aesthetic, warm natural light, lifestyle photography",
        "skincare beauty gadget flat lay, rose gold tones, minimal elegant composition, editorial style",
        "anti-aging LED mask beauty product, modern bathroom setting, glowing skin concept, professional photo",
    ],
    "주방": [
        "modern kitchen appliance product photography, bright clean white background, professional studio lighting, 4k",
        "cooking lifestyle scene, Korean home kitchen aesthetic, warm natural light, food styling",
        "kitchen gadget flat lay, marble surface, minimalist composition, editorial food photography",
        "home cooking product in use, cozy kitchen setting, soft warm tones, lifestyle photo",
    ],
    "생활": [
        "home lifestyle product photography, cozy interior, warm natural lighting, clean background, 4k",
        "smart home device in modern living room, Scandinavian interior aesthetic, soft focus",
        "household product flat lay, white linen background, minimal editorial composition",
        "home product lifestyle shot, cozy domestic scene, warm golden hour light",
    ],
    "디지털/가전": [
        "tech gadget product photography, minimalist white studio background, sharp focus, 4k",
        "electronic device lifestyle shot, modern desk setup, clean aesthetic, professional lighting",
        "smart device flat lay, dark matte surface, dramatic studio lighting, editorial",
        "technology product in use, modern home office, natural daylight, lifestyle photography",
    ],
    "인테리어": [
        "cozy interior decor product, Scandinavian home aesthetic, warm mood lighting, lifestyle photography",
        "home decoration flat lay, minimal white background, editorial composition, 4k",
        "interior design product in room setting, warm ambient light, lifestyle shot",
        "decorative home item, elegant modern interior, soft natural daylight",
    ],
    "기타": [
        "lifestyle product photography, clean white background, professional studio lighting, 4k",
        "product flat lay composition, minimal editorial style, warm neutral tones",
        "product in use lifestyle photo, natural light, Korean aesthetic, modern setting",
        "commercial product photography, sharp focus, elegant background, professional",
    ],
}


def _make_prompts(product: dict, post_text: str) -> list[str]:
    category = product.get("category_hint", product.get("category", "기타"))

    if GOOGLE_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")
            res = model.generate_content(
                f"""Write 4 English image prompts for AI image generation for this Korean shopping product.
Product: {product.get('name', '')}
Category: {category}

Rules:
- English ONLY (no Korean characters)
- Each prompt on one line, no numbering
- Professional commercial product photography style
- Include the product context (in use, flat lay, lifestyle, etc.)
- Include: Korean lifestyle aesthetic, studio quality, 4k
- Output exactly 4 prompts separated by newlines""",
                generation_config=genai.types.GenerationConfig(temperature=0.7),
            )
            lines = [l.strip() for l in res.text.strip().split("\n") if l.strip()][:4]
            if len(lines) >= 3:
                return lines
        except Exception as e:
            logger.warning(f"Gemini 프롬프트 생성 실패: {e}")

    return CATEGORY_PROMPTS.get(category, CATEGORY_PROMPTS["기타"])


def _hf_generate(prompt: str) -> bytes | None:
    """Hugging Face Inference API — FLUX.1-schnell (무료, 카드 불필요)"""
    try:
        r = requests.post(
            "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
            headers={"Authorization": f"Bearer {HF_TOKEN}"},
            json={"inputs": prompt},
            timeout=90,
        )
        if r.status_code == 200:
            ct = r.headers.get("content-type", "")
            if ct.startswith("image") or r.content[:3] in (b'\xff\xd8\xff', b'\x89PN'):
                return r.content
        elif r.status_code == 503:
            # 모델 로딩 중 — 최대 30초 대기 후 재시도
            wait = r.json().get("estimated_time", 20)
            logger.info(f"    HF 모델 로딩 중, {min(wait,30):.0f}초 대기...")
            time.sleep(min(wait, 30))
            r2 = requests.post(
                "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={"inputs": prompt},
                timeout=90,
            )
            if r2.status_code == 200 and r2.content[:3] in (b'\xff\xd8\xff', b'\x89PN'):
                return r2.content
        logger.warning(f"  HF 오류: {r.status_code} {r.text[:100]}")
    except Exception as e:
        logger.warning(f"  HF 예외: {e}")
    return None


def _together_generate(prompt: str) -> bytes | None:
    """Together AI FLUX.1-schnell-Free (결제 활성화 시 사용)"""
    try:
        r = requests.post(
            "https://api.together.xyz/v1/images/generations",
            headers={"Authorization": f"Bearer {TOGETHER_API_KEY}", "Content-Type": "application/json"},
            json={"model": "black-forest-labs/FLUX.1-schnell-Free", "prompt": prompt,
                  "width": 1024, "height": 1024, "steps": 4, "n": 1, "response_format": "b64_json"},
            timeout=60,
        )
        if r.status_code == 200:
            return base64.b64decode(r.json()["data"][0]["b64_json"])
        logger.warning(f"  Together AI 오류: {r.status_code} {r.text[:120]}")
    except Exception as e:
        logger.warning(f"  Together AI 예외: {e}")
    return None


def _pollinations_generate(prompt: str, idx: int = 0) -> bytes | None:
    """pollinations.ai 폴백 (로컬/브라우저 환경용, CI에서 불안정)"""
    encoded = quote(prompt)
    seed    = (abs(hash(prompt)) + idx * 7919) % 99999
    url     = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1024&nologo=true&seed={seed}&model=flux-realism"
    )
    try:
        r = requests.get(url, timeout=90)
        if r.status_code == 200 and len(r.content) > 5000:
            ct = r.headers.get("content-type", "")
            if ct.startswith("image") or r.content[:3] in (b'\xff\xd8\xff', b'\x89PN', b'GIF'):
                return r.content
    except Exception as e:
        logger.warning(f"  pollinations 실패: {e}")
    return None


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
        logger.warning(f"  imgBB 오류: {r.status_code}")
    except Exception as e:
        logger.warning(f"  imgBB 업로드 실패: {e}")
    return None


def generate_and_upload_images(product: dict, post_text: str = "") -> list[str]:
    """
    AI 이미지 4장 생성 → imgBB 업로드 → 영구 URL 목록 반환.
    imgBB 키 없거나 전체 실패 시 [] 반환.
    """
    if not IMGBB_API_KEY:
        logger.info("IMGBB_API_KEY 없음 → AI 이미지 건너뜀")
        return []

    prompts = _make_prompts(product, post_text)
    result  = []

    for i, prompt in enumerate(prompts[:4]):
        logger.info(f"  이미지 {i+1}/4 생성 중...")

        # 1순위: Hugging Face (무료, 카드 불필요)
        img_bytes = None
        if HF_TOKEN:
            img_bytes = _hf_generate(prompt)
            if img_bytes:
                logger.info(f"    HF 생성 성공 ({i+1})")

        # 2순위: Together AI (결제 활성화 시)
        if not img_bytes and TOGETHER_API_KEY:
            img_bytes = _together_generate(prompt)
            if img_bytes:
                logger.info(f"    Together AI 생성 성공 ({i+1})")

        # 3순위: pollinations.ai (로컬 환경 폴백)
        if not img_bytes:
            logger.info(f"    pollinations.ai 폴백 ({i+1})...")
            img_bytes = _pollinations_generate(prompt, idx=i)

        if not img_bytes:
            logger.warning(f"  이미지 {i+1} 생성 실패 — 건너뜀")
            continue

        url = _upload_imgbb(img_bytes)
        if url:
            result.append(url)
            logger.info(f"  imgBB 업로드 완료 ({i+1}): {url[:55]}...")
        else:
            logger.warning(f"  이미지 {i+1} imgBB 업로드 실패 — 건너뜀")

    logger.info(f"AI 이미지 생성 결과: {len(result)}장 성공 / {len(prompts[:4])}장 시도")
    return result
