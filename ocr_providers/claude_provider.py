"""
Claude Vision OCR 프로바이더

Anthropic API를 사용해 영수증 이미지/PDF를 분석합니다.
EasyOCR/Torch 의존성 없이 동작하며, 한국어 인식 품질이 훨씬 뛰어납니다.

환경변수:
  ANTHROPIC_API_KEY   Anthropic API 키 (필수)
"""
import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple

from .base import OcrProvider

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """당신은 영수증 분석 전문가입니다. 한국 영수증 이미지를 보고 아래 2가지만 추출하세요.

[추출 규칙]
1. 거래처: 가게 상호명 또는 사업자명
   - 영수증 상단에 크게 적힌 가게 이름 우선
   - 사업자등록번호 위나 아래에 있는 상호명
   - 영문 브랜드명이 있으면 한글 상호명 우선 (예: 스타벅스커피코리아(주))
   - 간이영수증이면 도장/서명 옆 상호명

2. 금액: 최종 실제 결제 금액 (숫자만)
   - "합계", "결제금액", "청구금액", "받을금액", "총액" 중 가장 큰 최종 금액
   - 카드 영수증이면 "승인금액" 또는 "결제금액"
   - 부가세 포함된 최종 금액
   - 쉼표 제거 후 숫자만 (예: 12,500 → 12500)
   - 금액을 못 찾으면 0

3. 적요: 거래처명을 간결하게 그대로 사용

반드시 아래 JSON 형식만 반환하세요. 설명 없이:
{"적요": "거래처명", "거래처": "정확한 상호명", "금액": 12345}"""


def _encode_image(path: str) -> Tuple[str, str]:
    """파일을 base64로 인코딩. (data, media_type) 반환."""
    ext = Path(path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_map.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8"), media_type


def _pdf_to_image_bytes(path: str) -> Optional[bytes]:
    """PDF 첫 페이지를 PNG 바이트로 변환. pymupdf 없으면 None."""
    try:
        import fitz
        doc = fitz.open(path)
        page = doc[0]
        pix = page.get_pixmap(dpi=150)
        return pix.tobytes("png")
    except ImportError:
        return None


class ClaudeOcrProvider(OcrProvider):

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다")

    def process_file(self, filepath: str) -> dict:
        ext = Path(filepath).suffix.lower()
        try:
            if ext == ".pdf":
                img_bytes = _pdf_to_image_bytes(filepath)
                if img_bytes:
                    image_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
                    media_type = "image/png"
                else:
                    return {"error": "PDF 처리 불가 (pymupdf 미설치)", "적요": filepath, "거래처": "", "금액": 0}
            else:
                image_b64, media_type = _encode_image(filepath)

            payload = {
                "model": MODEL,
                "max_tokens": 256,
                "system": SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": [{
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                    }, {
                        "type": "text",
                        "text": "이 영수증에서 정보를 추출해주세요.",
                    }],
                }],
            }

            req = urllib.request.Request(
                ANTHROPIC_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            text = body["content"][0]["text"].strip()
            # JSON 파싱 — 코드블록 감싸진 경우 처리
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            # 중괄호 범위만 잘라서 파싱 (앞뒤 불필요한 텍스트 제거)
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                text = text[start:end+1]
            data = json.loads(text)
            return {
                "적요": str(data.get("적요", "")),
                "거래처": str(data.get("거래처", "")),
                "금액": int(data.get("금액", 0)),
            }

        except json.JSONDecodeError as e:
            return {"error": f"응답 파싱 오류: {e}", "적요": Path(filepath).name, "거래처": "", "금액": 0}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return {"error": f"API 오류 {e.code}: {body[:200]}", "적요": Path(filepath).name, "거래처": "", "금액": 0}
        except Exception as e:
            return {"error": str(e), "적요": Path(filepath).name, "거래처": "", "금액": 0}
