"""
외부 JWT 프로바이더 — 기존 사이트가 이미 JWT를 발급하는 경우.
기존 사이트와 SECRET_KEY를 공유하면 토큰을 재발급 없이 그대로 사용할 수 있음.

환경변수:
  EXTERNAL_JWT_SECRET  — 기존 사이트의 JWT 시크릿 키
  EXTERNAL_JWT_ID_FIELD    — JWT payload 에서 사용자 ID 필드명 (기본: "sub")
  EXTERNAL_JWT_AUTHOR_FIELD — JWT payload 에서 이름 필드명 (기본: "name")
"""
import os
from jose import jwt, JWTError
from .base import AuthProvider, AuthResult

EXTERNAL_SECRET      = os.getenv("EXTERNAL_JWT_SECRET", "")
ID_FIELD     = os.getenv("EXTERNAL_JWT_ID_FIELD", "sub")
AUTHOR_FIELD = os.getenv("EXTERNAL_JWT_AUTHOR_FIELD", "name")


class ExternalJwtAuth(AuthProvider):
    def authenticate(self, credentials: dict) -> AuthResult:
        token = credentials.get("external_token", "")
        if not token:
            return AuthResult(False, "", "", "external_token이 없습니다")
        if not EXTERNAL_SECRET:
            return AuthResult(False, "", "", "EXTERNAL_JWT_SECRET 환경변수가 설정되지 않았습니다")
        try:
            payload = jwt.decode(token, EXTERNAL_SECRET, algorithms=["HS256"])
            username = payload.get(ID_FIELD, "")
            author   = payload.get(AUTHOR_FIELD, "")
            if not username:
                return AuthResult(False, "", "", f"JWT payload 에 '{ID_FIELD}' 필드가 없습니다")
            return AuthResult(True, username, author)
        except JWTError as e:
            return AuthResult(False, "", "", f"JWT 검증 실패: {e}")
