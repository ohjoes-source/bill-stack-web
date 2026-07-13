from abc import ABC, abstractmethod


class OcrProvider(ABC):
    """영수증 OCR 프로바이더 인터페이스 — 새 툴 추가 시 이 클래스를 상속."""

    @abstractmethod
    def process_file(self, filepath: str) -> dict:
        """
        파일 하나를 분석하여 반환:
        {"적요": str, "거래처": str, "금액": int}
        오류 시 {"error": str, "적요": str, "거래처": "", "금액": 0}
        """
        ...
