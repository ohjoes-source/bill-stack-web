"""
OASIS SSO 인증 프로바이더 — 기존 사이트의 OASIS 연동 모듈에 맞게 구현 필요.

─────────────────────────────────────────────────────────────────
[다른 Claude에게]

이 파일을 수정해서 OASIS 인증을 연결해주세요.

OASIS 연동 방식에 따라 두 가지 중 하나를 선택합니다:

[방식 A] 기존 사이트가 OASIS 로그인 후 토큰/세션을 발급하는 경우
  - credentials["oasis_token"] 으로 기존 사이트의 토큰을 받음
  - 기존 사이트 API를 호출해서 사용자 정보(ID, 이름) 검증
  - 검증 성공 시 AuthResult(True, user_id, user_name) 반환

[방식 B] OASIS OAuth 콜백 처리 (code → token 교환)
  - credentials["code"] 를 OASIS 토큰 엔드포인트에 전달
  - 토큰으로 사용자 정보 조회
  - AuthResult 반환

필수 반환값:
  AuthResult.username → BizOffice 로그인 ID와 동일해야 함
                         (기안 시 auth.json 세션 파일명으로 사용됨)
  AuthResult.author   → 기안서 영수자 필드에 들어갈 한글 이름

─────────────────────────────────────────────────────────────────
"""
import os
from .base import AuthProvider, AuthResult

OASIS_API_BASE = os.getenv("OASIS_API_BASE", "")   # 예: https://your-site.com/api
OASIS_CLIENT_ID = os.getenv("OASIS_CLIENT_ID", "")
OASIS_CLIENT_SECRET = os.getenv("OASIS_CLIENT_SECRET", "")


class OasisAuth(AuthProvider):
    def authenticate(self, credentials: dict) -> AuthResult:
        # TODO: 기존 사이트의 OASIS 연동 방식에 맞게 구현

        # ── 방식 A 예시: 기존 사이트 토큰으로 사용자 검증 ──────────
        # token = credentials.get("oasis_token")
        # if not token:
        #     return AuthResult(False, "", "", "토큰이 없습니다")
        # resp = requests.get(f"{OASIS_API_BASE}/me",
        #                     headers={"Authorization": f"Bearer {token}"})
        # if resp.status_code != 200:
        #     return AuthResult(False, "", "", "토큰 검증 실패")
        # user = resp.json()
        # return AuthResult(True, user["biz_id"], user["name"])

        # ── 방식 B 예시: OAuth code 교환 ──────────────────────────
        # code = credentials.get("code")
        # resp = requests.post(f"{OASIS_API_BASE}/oauth/token", json={
        #     "client_id": OASIS_CLIENT_ID,
        #     "client_secret": OASIS_CLIENT_SECRET,
        #     "code": code,
        # })
        # token_data = resp.json()
        # user = get_user_from_token(token_data["access_token"])
        # return AuthResult(True, user["biz_id"], user["name"])

        return AuthResult(False, "", "", "OASIS 인증 미구현 — oasis.py 를 수정해주세요")
