"""
Google Gemini Vision OCR 프로바이더

환경변수:
  GEMINI_API_KEY   Google Gemini API 키 (필수)
"""
import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .base import OcrProvider

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

PROMPT = """한국 영수증 이미지를 분석해서 아래 2가지만 추출하세요.

[추출 규칙]
1. 거래처: 가게 상호명 또는 사업자명
   - 영수증 상단에 크게 적힌 가게 이름 우선
   - 사업자등록번호 위나 아래에 있는 상호명
   - 영문 브랜드명이 있으면 한글 상호명 우선
   - 간이영수증이면 도장/서명 옆 상호명

2. 금액: 최종 실제 결제 금액 (숫자만)
   - "합계", "결제금액", "청구금액", "받을금액", "총액" 중 최종 금액
   - 카드 영수증이면 "승인금액" 또는 "결제금액"
   - 부가세 포함된 최종 금액
   - 쉼표 제거 후 숫자만 (예: 12,500 → 12500)
   - 금액을 못 찾으면 0

3. 적요: 거래처명을 간결하게 그대로 사용

반드시 아래 JSON 형식만 반환하세요. 설명 없이:
{"적요": "거래처명", "거래처": "정확한 상호명", "금액": 12345}"""


def _pdf_to_image_bytes(path: str) -> Optional[bytes]:
    try:
        import fitz
        doc = fitz.open(path)
        page = doc[0]
        pix = page.get_pixmap(dpi=150)
        return pix.tobytes("png")
    except ImportError:
        return None


class GeminiOcrProvider(OcrProvider):

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다")

    def process_file(self, filepath: str) -> dict:
        ext = Path(filepath).suffix.lower()
        try:
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".pdf": "application/pdf",
            }
            mime_type = mime_map.get(ext, "image/jpeg")
            with open(filepath, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "contents": [{
                    "parts": [
                        {"text": PROMPT},
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                    ]
                }],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 1024,
                },
            }

            req = urllib.request.Request(
                GEMINI_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-goog-api-key": self.api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            text = body["candidates"][0]["content"]["parts"][0]["text"].strip()

            # ``` 코드블록 제거
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            # JSON 범위 추출 (배열 또는 객체)
            arr_start = text.find("[")
            obj_start = text.find("{")
            if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
                end = text.rfind("]")
                text = text[arr_start:end + 1]
            elif obj_start != -1:
                end = text.rfind("}")
                text = text[obj_start:end + 1]

            data = json.loads(text)
            # 배열이면 첫 번째 항목 사용
            if isinstance(data, list):
                data = data[0] if data else {}
            return {
                "적요": str(data.get("적요", "")),
                "거래처": str(data.get("거래처", "")),
                "금액": int(data.get("금액", 0)),
            }

        except json.JSONDecodeError as e:
            return {"error": f"응답 파싱 오류: {e}", "적요": "", "거래처": "", "금액": 0}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return {"error": "API 사용량 초과 (429) — 1분 후 다시 시도하세요", "적요": "", "거래처": "", "금액": 0}
            body = e.read().decode("utf-8", errors="replace")
            return {"error": f"API 오류 {e.code}: {body[:200]}", "적요": "", "거래처": "", "금액": 0}
        except Exception as e:
            return {"error": str(e), "적요": "", "거래처": "", "금액": 0}
