import re
from pathlib import Path
from .base import OcrProvider

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["ko", "en"], gpu=False)
    return _reader


def _pdf_to_images(path: Path) -> list[bytes]:
    import fitz
    doc = fitz.open(str(path))
    images = [page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png") for page in doc]
    doc.close()
    return images


def _ocr_bytes(img_bytes: bytes) -> list[str]:
    import numpy as np
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    results = _get_reader().readtext(img)
    return [text for (_, text, conf) in results if conf > 0.3]


def _ocr_file(path: Path) -> list[str]:
    results = _get_reader().readtext(str(path))
    return [text for (_, text, conf) in results if conf > 0.3]


def _extract_amount(texts: list[str]) -> int:
    candidates = []
    for t in texts:
        for n in re.findall(r"[\d,]{3,}", t):
            try:
                v = int(n.replace(",", ""))
                if 1_000 <= v <= 10_000_000:
                    candidates.append(v)
            except Exception:
                pass
    return max(candidates) if candidates else 0


def _extract_vendor(texts: list[str]) -> str:
    keywords = ["주식회사", "㈜", "(주)", "마트", "편의점", "카페", "식당",
                "음식점", "주유소", "GS", "CU", "세븐", "이마트", "롯데"]
    for t in texts:
        if any(k in t for k in keywords):
            return t.strip()
    return texts[0].strip() if texts else ""


class EasyOcrProvider(OcrProvider):
    def process_file(self, filepath: str) -> dict:
        path = Path(filepath)
        try:
            if path.suffix.lower() == ".pdf":
                texts = []
                for img in _pdf_to_images(path):
                    texts.extend(_ocr_bytes(img))
            else:
                texts = _ocr_file(path)
            return {"적요": path.stem, "거래처": _extract_vendor(texts), "금액": _extract_amount(texts)}
        except Exception as e:
            return {"error": str(e), "적요": path.stem, "거래처": "", "금액": 0}
