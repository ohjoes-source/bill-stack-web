"""
SEON 포털 토큰 검증 프로바이더

진입 흐름:
  SEON 포털 카드 클릭
    → 포털이 단기 토큰 발급
    → GET /auth?token=<TOKEN> 로 리다이렉트
    → 이 프로바이더가 포털 API로 토큰 검증
    → userId, name 획득 → JWT 발급

환경변수:
  SEON_PORTAL_VERIFY_URL   검증 API URL (기본값 내장, 변경 필요 시만 설정)
"""
import json
import os
import urllib.request
import urllib.error
from .base import AuthProvider, AuthResult

SEON_VERIFY_URL = os.getenv(
    "SEON_PORTAL_VERIFY_URL",
    "https://seon-portal.vercel.app/api/verify-token?service=bill-stack",
)


def verify_seon_token(token: str) -> dict:
    """포털 검증 API 호출 → {userId, name, department, rank, role} 반환."""
    payload = json.dumps({"token": token}).encode("utf-8")
    req = urllib.request.Request(
        SEON_VERIFY_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ValueError("포털 토큰이 만료되었거나 유효하지 않습니다")
        raise RuntimeError(f"포털 API 오류 (HTTP {e.code})")


class SeonPortalAuth(AuthProvider):
    """POST /api/login 경로에서는 사용하지 않음. /auth 엔드포인트에서 직접 호출."""
    def authenticate(self, credentials: dict) -> AuthResult:
        token = credentials.get("token", "").strip()
        if not token:
            return AuthResult(False, "", "", "token이 없습니다")
        try:
            data = verify_seon_token(token)
        except ValueError as e:
            return AuthResult(False, "", "", str(e))
        except Exception as e:
            return AuthResult(False, "", "", f"포털 검증 실패: {e}")
        user_id = data.get("userId", "")
        name = data.get("name", "")
        if not user_id:
            return AuthResult(False, "", "", "포털 응답에 userId 없음")
        return AuthResult(True, user_id, name or user_id)
