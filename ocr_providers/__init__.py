"""
OCR 프로바이더 선택 — 환경변수 OCR_PROVIDER 로 교체.

현재 지원:
  claude    (기본값) — Anthropic API 비전, 한국어 최적
  easyocr             — 로컬, GPU 없이 동작
  tesseract           — Tesseract-OCR 설치 필요
  google              — GOOGLE_VISION_KEY 환경변수 필요

새 프로바이더 추가:
  1. base.OcrProvider 상속하여 process_file() 구현
  2. 아래 _PROVIDERS 딕셔너리에 키 추가
"""
import os
from typing import Optional
from .base import OcrProvider

_instance: Optional[OcrProvider] = None

_PROVIDERS = {
    "claude":    "ocr_providers.claude_provider.ClaudeOcrProvider",
    "gemini":    "ocr_providers.gemini_provider.GeminiOcrProvider",
    "easyocr":   "ocr_providers.easyocr_provider.EasyOcrProvider",
    "tesseract": "ocr_providers.tesseract_provider.TesseractProvider",
    "google":    "ocr_providers.google_provider.GoogleVisionProvider",
}


def get_provider() -> OcrProvider:
    global _instance
    if _instance is None:
        name = os.getenv("OCR_PROVIDER", "claude")
        class_path = _PROVIDERS.get(name)
        if not class_path:
            raise ValueError(f"알 수 없는 OCR_PROVIDER: {name}. 지원: {list(_PROVIDERS)}")
        module_path, class_name = class_path.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(module_path)
        _instance = getattr(mod, class_name)()
    return _instance
