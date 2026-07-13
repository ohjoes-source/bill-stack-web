"""
지출결의서 자동입력 스킬 (웹 버전)

스킬 계약 — 이 스킬이 요구하는 최소 데이터:
  {
    "현장명": str,          # 필수
    "내역": [               # 필수, 1~5개
      {
        "적요":   str,      # 필수
        "거래처": str,      # 필수
        "금액":   int,      # 필수, 양의 정수
      }
    ]
  }

이 계약 외의 필드는 무시됩니다.
상태는 status_cb(event, message) 콜백으로 전달됩니다:
  event: "info" | "ready" | "done" | "error" | "cancelled"
"""
import threading
from datetime import date
from pathlib import Path
from typing import Callable, TypedDict

BIZ_URL = "https://gwp.ktbizoffice.com/EKPHome/Login?compid=seoneng"

# ── 스킬 데이터 계약 ──────────────────────────────────────────────

class RowData(TypedDict):
    적요:   str
    거래처: str
    금액:   int


class SkillData(TypedDict):
    현장명: str
    내역:   list[RowData]


def validate(data: dict) -> tuple[SkillData | None, list[str]]:
    """입력 데이터 검증 후 (cleaned, errors) 반환. errors 비어있으면 유효."""
    errors = []

    site = str(data.get("현장명", "")).strip()
    if not site:
        errors.append("현장명이 비어있습니다")

    raw_rows = data.get("내역", [])
    if not raw_rows:
        errors.append("내역 항목이 없습니다")
    if len(raw_rows) > 5:
        errors.append("내역은 최대 5개까지 입력 가능합니다")

    rows: list[RowData] = []
    for i, row in enumerate(raw_rows[:5], 1):
        try:
            금액 = int(str(row.get("금액", 0)).replace(",", "").replace(" ", ""))
        except (ValueError, TypeError):
            금액 = 0
            errors.append(f"내역 {i}: 금액이 숫자가 아닙니다")

        rows.append(RowData(
            적요=str(row.get("적요", "")).strip(),
            거래처=str(row.get("거래처", "")).strip(),
            금액=max(0, 금액),
        ))

    if errors:
        return None, errors
    return SkillData(현장명=site, 내역=rows), []


# ── 세션 저장소 ───────────────────────────────────────────────────

_sessions: dict = {}
_sessions_lock = threading.Lock()


def get_session(task_id: str) -> dict | None:
    with _sessions_lock:
        return _sessions.get(task_id)


def cleanup_session(task_id: str):
    with _sessions_lock:
        sess = _sessions.pop(task_id, None)
    if sess:
        try:
            sess.get("context") and sess["context"].close()
            sess.get("browser") and sess["browser"].close()
        except Exception:
            pass


# ── 스킬 실행 ────────────────────────────────────────────────────

def run_skill(
    task_id: str,
    skill_data: SkillData,
    file_paths: list[str],
    cfg: dict,
    status_cb: Callable[[str, str], None],
):
    """
    별도 스레드에서 호출. cfg = {id, password, author, url, username}.
    status_cb(event, message) 로 진행 상태를 전달.
    """
    from playwright.sync_api import sync_playwright

    auth_file = Path(__file__).parent / "data" / "users" / cfg["username"] / "auth.json"

    def s(event: str, msg: str):
        status_cb(event, msg)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            if auth_file.exists():
                s("info", "저장된 세션으로 연결 중...")
                context = browser.new_context(storage_state=str(auth_file))
                page = context.new_page()
                page.goto("https://gwp.ktbizoffice.com/ezPortal/Main/IndexPortal")
                page.wait_for_selector("body", timeout=10000)
                if "login" in page.url.lower():
                    s("info", "세션 만료 — 재로그인 중...")
                    context.close()
                    context = _login(browser, cfg, auth_file)
                    page = context.pages[0]
            else:
                s("info", "로그인 중...")
                context = _login(browser, cfg, auth_file)
                page = context.pages[0]

            s("info", "로그인 완료")

            with _sessions_lock:
                _sessions[task_id] = {
                    "browser": browser, "context": context,
                    "page": page, "page1": None,
                    "status": "logged_in",
                }

            # 결재 → 기안하기
            s("info", "기안하기 열기...")
            page.locator("#top_menu_sub_list").get_by_text("결재").click()
            page.wait_for_timeout(1500)
            ap = page.locator("iframe[name=\"__MultiViewPage_4_Page___frame\"]")
            ap.content_frame.get_by_text("기안하기").click()
            ap.content_frame.locator("#Main_iFrameLayer").wait_for(state="attached", timeout=15000)
            page.wait_for_timeout(2000)

            # 수입지출결의서 선택
            s("info", "수입지출결의서 선택 중...")
            inner = ap.content_frame.locator("#Main_iFrameLayer").content_frame
            inner.locator("text=수입지출결의서").wait_for(state="visible", timeout=15000)
            inner.get_by_text("수입지출결의서").click()
            page.wait_for_timeout(500)
            inner.get_by_role("cell", name="수입지출결의서").click()
            page.wait_for_timeout(300)
            with page.expect_popup() as info:
                inner.get_by_text("확인").click()
            page1 = info.value
            page1.locator("iframe[name=\"message\"]").wait_for(state="attached", timeout=15000)
            page1.wait_for_timeout(1500)
            s("info", "양식 열림")

            # 파일 첨부
            supported = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
            files = [f for f in file_paths if Path(f).suffix.lower() in supported and Path(f).exists()]
            if files:
                s("info", f"파일 첨부 중... ({len(files)}개)")
                page1.get_by_role("listitem", name="첨부", exact=True).click()
                attach = (page1.locator("#Main_iFrameLayer").content_frame
                              .locator("iframe[name=\"dadiframe\"]").content_frame)
                attach.locator("input[type='file']").wait_for(state="attached", timeout=10000)
                attach.locator("input[type='file']").set_input_files(files)
                page1.wait_for_timeout(300)
                attach.locator("#checkboxall").check()
                page1.locator("#Main_iFrameLayer").content_frame.get_by_text("확인").click()
                page1.wait_for_timeout(800)

            # ── 폼 입력 (스킬 계약 데이터만 사용) ─────────────────────
            s("info", "폼 입력 중...")
            mf = page1.locator("iframe[name=\"message\"]").content_frame
            site = skill_data["현장명"]
            rows = skill_data["내역"]
            total = sum(r["금액"] for r in rows)
            today = date.today()

            mf.locator("tr:nth-child(2) > td:nth-child(2) > div").first.click()
            mf.locator("tr:nth-child(2) > td:nth-child(2) > div").first.fill(f" {site}  ")
            page1.wait_for_timeout(300)

            mf.locator("#frame_doctitle").click()
            mf.locator("#frame_doctitle").fill(f"{site} 지출결의")
            page1.wait_for_timeout(300)

            for i, row in enumerate(rows):
                tr = i + 3
                mf.locator(f"td > div > table > tbody > tr:nth-child({tr}) > td > div").first.click()
                mf.locator(f"td > div > table > tbody > tr:nth-child({tr}) > td > div").first.fill(f" {row['적요']}")
                page1.wait_for_timeout(200)
                mf.locator(f"tr:nth-child({tr}) > td:nth-child(2) > div").first.click()
                mf.locator(f"tr:nth-child({tr}) > td:nth-child(2) > div").first.fill(f" {row['거래처']}")
                page1.wait_for_timeout(200)
                mf.locator(f"tr:nth-child({tr}) > td:nth-child(3) > div").first.click()
                mf.locator(f"tr:nth-child({tr}) > td:nth-child(3) > div").first.fill(f"{row['금액']:,}  ")
                page1.wait_for_timeout(200)

            mf.locator("tr:nth-child(8) > td:nth-child(3) > div").first.click()
            mf.locator("tr:nth-child(8) > td:nth-child(3) > div").first.fill(f"{total:,}  ")
            page1.wait_for_timeout(300)

            mf.locator("div").filter(has_text="일금").nth(4).fill(
                f"일금  {_to_korean(total)} (\\ {total:,} )")
            page1.wait_for_timeout(300)

            cash_cb = mf.locator("input[type='checkbox']").first
            if not cash_cb.is_checked():
                cash_cb.check()
            page1.wait_for_timeout(200)

            mf.locator("td:nth-child(2) > div").first.click()
            mf.locator("td:nth-child(2) > div").first.fill(f" {today.strftime('%y.%m.%d')}")
            page1.wait_for_timeout(200)

            mf.locator("div > table > tbody > tr:nth-child(2) > td:nth-child(2) > div").first.click()
            mf.locator("div > table > tbody > tr:nth-child(2) > td:nth-child(2) > div").first.fill(
                f" {today.year} 년 {today.month:02d} 월 {today.day:02d} 일")
            page1.wait_for_timeout(200)

            mf.locator("tr:nth-child(2) > td:nth-child(4) > div").first.click()
            mf.locator("tr:nth-child(2) > td:nth-child(4) > div").first.fill(f"{cfg['author']}  ")
            page1.wait_for_timeout(200)

            context.storage_state(path=str(auth_file))

            with _sessions_lock:
                if task_id in _sessions:
                    _sessions[task_id]["page1"] = page1
                    _sessions[task_id]["status"] = "ready_for_submit"

            s("ready", "폼 입력 완료 ✅ — 기안하기 버튼을 눌러 제출하세요")

            # 기안 확인 대기 (최대 10분)
            done_event = threading.Event()
            with _sessions_lock:
                if task_id in _sessions:
                    _sessions[task_id]["done_event"] = done_event
            done_event.wait(timeout=600)

            with _sessions_lock:
                should_submit = _sessions.get(task_id, {}).get("submit_requested", False)

            if should_submit:
                s("info", "기안 중...")
                page1.get_by_role("button", name="기안").click()
                page1.wait_for_timeout(2000)
                s("done", "기안 완료! 🎉")
            else:
                s("cancelled", "시간 초과 또는 취소")

    except Exception as e:
        s("error", str(e))
    finally:
        cleanup_session(task_id)


def confirm_submit(task_id: str) -> bool:
    with _sessions_lock:
        sess = _sessions.get(task_id)
        if not sess or sess.get("status") != "ready_for_submit":
            return False
        sess["submit_requested"] = True
        done_event = sess.get("done_event")
    if done_event:
        done_event.set()
    return True


# ── 내부 유틸 ────────────────────────────────────────────────────

def _login(browser, cfg: dict, auth_file: Path):
    context = browser.new_context()
    page = context.new_page()
    page.goto(cfg.get("url", BIZ_URL))
    page.get_by_role("textbox", name="아이디").fill(cfg["id"])
    page.get_by_role("textbox", name="아이디").press("Tab")
    page.get_by_role("textbox", name="비밀번호").fill(cfg["password"])
    page.get_by_role("textbox", name="비밀번호").press("Enter")
    page.wait_for_selector("#top_menu_sub_list", timeout=10000)
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(auth_file))
    return context


def _to_korean(n: int) -> str:
    if n == 0:
        return "영원정"
    units = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
    pos   = ['', '십', '백', '천']
    big   = ['', '만', '억', '조']

    def chunk(c):
        s = ''
        for i in range(3, -1, -1):
            d = (c // 10**i) % 10
            if d:
                s += units[d] + pos[i]
        return s

    r, bi = '', 0
    while n > 0:
        c = n % 10000
        if c:
            r = chunk(c) + big[bi] + r
        bi += 1; n //= 10000
    return r + '원정'
