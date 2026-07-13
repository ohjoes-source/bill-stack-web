"""
기본 인증 프로바이더 — Playwright headless 로 BizOffice에 직접 로그인.
별도 SSO 없이 사용하는 독립 실행 시나리오용.
"""
import threading
from pathlib import Path
from .base import AuthProvider, AuthResult

BIZ_URL = "https://gwp.ktbizoffice.com/EKPHome/Login?compid=seoneng"


class BizOfficePlaywrightAuth(AuthProvider):
    def __init__(self, auth_dir: Path):
        self._auth_dir = auth_dir  # 세션 파일 저장 경로

    def authenticate(self, credentials: dict) -> AuthResult:
        biz_id   = credentials.get("biz_id", "").strip()
        password = credentials.get("biz_password", "")
        author   = credentials.get("author", "").strip()

        if not biz_id or not password or not author:
            return AuthResult(False, "", "", "모든 항목을 입력해주세요")

        result: dict = {}
        done = threading.Event()

        def _run():
            try:
                from playwright.sync_api import sync_playwright
                auth_file = self._auth_dir / biz_id / "auth.json"
                auth_file.parent.mkdir(parents=True, exist_ok=True)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    ctx = browser.new_context()
                    page = ctx.new_page()
                    page.goto(BIZ_URL)
                    page.get_by_role("textbox", name="아이디").fill(biz_id)
                    page.get_by_role("textbox", name="아이디").press("Tab")
                    page.get_by_role("textbox", name="비밀번호").fill(password)
                    page.get_by_role("textbox", name="비밀번호").press("Enter")
                    page.wait_for_selector("#top_menu_sub_list", timeout=10000)
                    ctx.storage_state(path=str(auth_file))
                    ctx.close()
                    browser.close()
                result["ok"] = True
            except Exception as e:
                result["ok"] = False
                result["error"] = str(e)
            finally:
                done.set()

        threading.Thread(target=_run, daemon=True).start()
        done.wait(timeout=15)

        if result.get("ok"):
            return AuthResult(True, biz_id, author)
        return AuthResult(False, "", "", result.get("error", "로그인 시간 초과"))
