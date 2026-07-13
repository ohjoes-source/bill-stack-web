"""
인증 프로바이더 선택 — 환경변수 AUTH_PROVIDER 로 교체.

  bizoffice    (기본값) — Playwright headless 로 BizOffice 직접 로그인
  rsa_sso               — BizOfficePlus RSA SSO (GET /auth 콜백 방식)
  external_jwt          — 기존 사이트 JWT 공유 (EXTERNAL_JWT_SECRET 설정 필요)
"""
import os
from pathlib import Path
from .base import AuthProvider, AuthResult

_instance: AuthProvider | None = None

_PROVIDERS = {
    "bizoffice":    "auth_providers.bizoffice_playwright.BizOfficePlaywrightAuth",
    "rsa_sso":      "auth_providers.rsa_sso.RsaSsoAuth",
    "external_jwt": "auth_providers.external_jwt.ExternalJwtAuth",
    "seon_portal":  "auth_providers.seon_portal.SeonPortalAuth",
}


def get_provider(auth_dir: Path) -> AuthProvider:
    global _instance
    if _instance is None:
        name = os.getenv("AUTH_PROVIDER", "bizoffice")
        class_path = _PROVIDERS.get(name)
        if not class_path:
            raise ValueError(f"알 수 없는 AUTH_PROVIDER: {name}. 지원: {list(_PROVIDERS)}")
        module_path, class_name = class_path.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        # BizOfficePlaywrightAuth 는 auth_dir 인자 필요, 나머지는 불필요
        try:
            _instance = cls(auth_dir)
        except TypeError:
            _instance = cls()
    return _instance
