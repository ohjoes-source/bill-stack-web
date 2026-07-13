from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AuthResult:
    success:  bool
    username: str        # BizOffice 로그인 ID (JWT sub로 사용)
    author:   str        # 한글 이름 (기안 시 영수자 필드에 입력됨)
    error:    str = ""


class AuthProvider(ABC):
    """
    인증 프로바이더 인터페이스.

    새 인증 방식 추가 시:
      1. 이 클래스를 상속
      2. authenticate() 구현
      3. auth_providers/__init__.py 의 _PROVIDERS 에 키 등록
      4. 환경변수 AUTH_PROVIDER=새키 설정
    """

    @abstractmethod
    def authenticate(self, credentials: dict) -> AuthResult:
        """
        credentials: 로그인 폼에서 넘어온 raw 딕셔너리.
        - BizOffice Playwright 방식:  {"biz_id", "biz_password", "author"}
        - OASIS SSO 방식:             {"oasis_token"} 또는 {"code"} (OAuth callback)
        - 외부 JWT 방식:              {"external_token"}

        반드시 AuthResult를 반환한다 (예외 금지 — 오류는 AuthResult.error 에 담을 것).
        """
        ...
