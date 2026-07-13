"""
Bill-stack Web Server

독립 실행:
  uvicorn server:app --host 0.0.0.0 --port 8000

기존 FastAPI 앱에 마운트:
  from bill_stack_web.server import create_app
  billstack = create_app()
  main_app.mount("/billstack", billstack)

주요 환경변수:
  AUTH_PROVIDER        bizoffice | oasis | external_jwt  (기본: bizoffice)
  OCR_PROVIDER         easyocr | tesseract | google       (기본: easyocr)
  SECRET_KEY           JWT 서명 키
  TOKEN_EXPIRE_HOURS   JWT 만료 시간 (기본: 24)
  APP_PREFIX           마운트 prefix (기본: "")  예: /billstack
"""
import asyncio
import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

SECRET_KEY         = os.getenv("SECRET_KEY", "bill-stack-secret-change-this")
ALGORITHM          = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))
APP_PREFIX         = os.getenv("APP_PREFIX", "").rstrip("/")
AUTH_PROVIDER      = os.getenv("AUTH_PROVIDER", "bizoffice")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

oauth2 = OAuth2PasswordBearer(tokenUrl=f"{APP_PREFIX}/api/login")


# ── JWT ──────────────────────────────────────────────────────────

def _create_token(username: str, author: str = "") -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "name": author, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


class UserInfo:
    def __init__(self, username: str, author: str):
        self.username = username
        self.author = author


def _get_current_user(token: str = Depends(oauth2)) -> UserInfo:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        u = payload.get("sub")
        if not u:
            raise HTTPException(status_code=401, detail="Invalid token")
        return UserInfo(username=u, author=payload.get("name", ""))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _user_dir(username: str) -> Path:
    d = DATA_DIR / "users" / username
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_user_config(username: str, author: str):
    (_user_dir(username) / "config.json").write_text(
        json.dumps({"author": author, "username": username}, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_user_config(username: str) -> dict | None:
    f = _user_dir(username) / "config.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


# ── 태스크 저장소 ────────────────────────────────────────────────

_tasks: dict = {}
_lock = threading.Lock()

# ── 기안 임시 저장소 (PIN 기반, 30분 만료) ──────────────────────
import random
_drafts: dict = {}  # {pin: {data, expires_at}}

def _new_draft_pin(data: dict) -> str:
    pin = str(random.randint(1000, 9999))
    expires = datetime.utcnow() + timedelta(minutes=30)
    with _lock:
        # 만료된 항목 정리
        now = datetime.utcnow()
        expired = [k for k, v in _drafts.items() if v["expires_at"] < now]
        for k in expired:
            del _drafts[k]
        _drafts[pin] = {"data": data, "expires_at": expires}
    return pin


def _new_task(username: str) -> str:
    tid = str(uuid.uuid4())
    with _lock:
        _tasks[tid] = {"username": username, "events": [], "done": False,
                       "created_at": datetime.utcnow().isoformat()}
    return tid


def _push(tid: str, event: str, message: str):
    with _lock:
        if tid in _tasks:
            _tasks[tid]["events"].append({"event": event, "message": message})
            if event in ("done", "error", "cancelled"):
                _tasks[tid]["done"] = True


# ── 앱 팩토리 ────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """기존 사이트에 마운트할 때는 이 함수로 앱 인스턴스를 생성."""
    _app = FastAPI(title="Bill-stack", docs_url=None, redoc_url=None)
    _app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                        allow_methods=["*"], allow_headers=["*"])
    _register_routes(_app)
    return _app


def _register_routes(app: FastAPI):

    # ── 정적 파일 & 메인 페이지 ──────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse((BASE_DIR / "static" / "index.html").read_text(encoding="utf-8"))

    # ── 로그인 ───────────────────────────────────────────────────
    class LoginBody(BaseModel):
        # 필드는 AUTH_PROVIDER에 따라 달라짐. 공통 필드:
        biz_id:       str = ""   # bizoffice 방식
        biz_password: str = ""   # bizoffice 방식
        author:       str = ""   # 공통 (이름)
        oasis_token:  str = ""   # oasis 방식
        external_token: str = "" # external_jwt 방식

    @app.post("/api/login")
    async def login(body: LoginBody):
        from auth_providers import get_provider
        provider = get_provider(DATA_DIR / "users")
        result = provider.authenticate(body.model_dump())
        if not result.success:
            raise HTTPException(status_code=401, detail=result.error)
        _save_user_config(result.username, result.author)
        return {
            "access_token": _create_token(result.username, result.author),
            "token_type": "bearer",
            "username": result.username,
            "author": result.author,
        }

    # ── SSO 콜백 — SEON 포털 토큰 또는 BizOffice RSA ───────────────
    # SEON 포털:    GET /auth?token=<단기토큰>
    # BizOffice:   GET /auth?sso=<HEX>&id=<userId>&name=<이름>&type=employee
    # 직접 접근:   403 차단
    @app.get("/auth")
    async def sso_callback(
        token: str = None,   # SEON 포털 경로
        sso:   str = None,   # BizOffice RSA 경로
        id:    str = None,   # BizOffice 폴백 (평문 userId)
        name:  str = None,   # BizOffice name 파라미터 (선택)
        type:  str = None,   # 무시 (기록 용도)
    ):
        from fastapi.responses import RedirectResponse, HTMLResponse

        user_id: str | None = None
        author:  str | None = None

        # ── 경로 ①: SEON 포털 토큰 ──────────────────────────────
        if token:
            try:
                from auth_providers.seon_portal import verify_seon_token
                data = verify_seon_token(token)
                user_id = data.get("userId")
                author  = data.get("name") or user_id
            except Exception as e:
                return HTMLResponse(_blocked_html(f"포털 토큰 검증 실패: {e}"), status_code=401)

        # ── 경로 ②: BizOffice RSA SSO ────────────────────────────
        elif sso or id:
            if sso:
                try:
                    from auth_providers.rsa_sso import decrypt_sso_token
                    user_id = decrypt_sso_token(sso)
                except Exception:
                    user_id = id or None
            else:
                user_id = id
            author = name or None

        # ── 경로 ③: 직접 접근 차단 ──────────────────────────────
        else:
            return HTMLResponse(_blocked_html(), status_code=403)

        if not user_id:
            return HTMLResponse(_blocked_html("사용자 ID를 확인할 수 없습니다"), status_code=400)

        # ── JWT 발급 (이름을 토큰에 포함) ───────────────────────────
        if not author:
            # BizOffice에서 name 파라미터 없이 첫 진입 → 이름 입력 화면
            jwt_token = _create_token(user_id, "")
            return RedirectResponse(url=f"{APP_PREFIX}/?token={jwt_token}&setup=1", status_code=302)

        jwt_token = _create_token(user_id, author)
        return RedirectResponse(url=f"{APP_PREFIX}/?token={jwt_token}", status_code=302)

    @app.get("/api/me")
    async def me(user: UserInfo = Depends(_get_current_user)):
        return {"username": user.username, "author": user.author}

    class ProfileBody(BaseModel):
        author: str

    @app.patch("/api/me")
    async def update_me(body: ProfileBody, user: UserInfo = Depends(_get_current_user)):
        author = body.author.strip()
        if not author:
            raise HTTPException(status_code=422, detail="이름을 입력해주세요")
        # 이름 업데이트는 클라이언트가 새 토큰을 재발급받아야 함 — 현재 세션에만 반영
        _save_user_config(user.username, author)
        return {"username": user.username, "author": author, "reload_token": _create_token(user.username, author)}

    # ── OCR ──────────────────────────────────────────────────────
    @app.post("/api/ocr")
    async def start_ocr(files: list[UploadFile] = File(...),
                        user: UserInfo = Depends(_get_current_user)):
        tid = _new_task(user.username)
        upload_dir = TEMP_DIR / tid
        upload_dir.mkdir()
        saved = []
        for f in files:
            dest = upload_dir / f.filename
            dest.write_bytes(await f.read())
            saved.append(str(dest))
        username = user.username

        def _run():
            try:
                from ocr_providers import get_provider
                from concurrent.futures import ThreadPoolExecutor, as_completed
                provider = get_provider()
                results = [None] * len(saved)
                _push(tid, "progress", f"총 {len(saved)}개 파일 동시 분석 중...")

                def _process(idx_fp):
                    idx, fp = idx_fp
                    return idx, provider.process_file(fp)

                with ThreadPoolExecutor(max_workers=min(len(saved), 5)) as ex:
                    futures = {ex.submit(_process, (i, fp)): i for i, fp in enumerate(saved)}
                    done_count = 0
                    for fut in as_completed(futures):
                        idx, result = fut.result()
                        results[idx] = result
                        done_count += 1
                        _push(tid, "progress", f"완료 ({done_count}/{len(saved)}): {Path(saved[idx]).name}")

                with _lock:
                    _tasks[tid]["result"] = results
                    _tasks[tid]["file_paths"] = saved
                _push(tid, "done", json.dumps(results, ensure_ascii=False))
            except Exception as e:
                _push(tid, "error", f"OCR 처리 오류: {e}")

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": tid}

    @app.get("/api/ocr/{tid}/stream")
    async def ocr_stream(tid: str, user: UserInfo = Depends(_get_current_user)):
        return _sse(tid)

    # ── 기안 PIN 발급 / 조회 ─────────────────────────────────────
    class DraftBody(BaseModel):
        result_data: dict

    @app.post("/api/draft")
    async def create_draft(body: DraftBody, user: UserInfo = Depends(_get_current_user)):
        data = {**body.result_data, "_author": user.author, "_username": user.username}
        pin = _new_draft_pin(data)
        return {"pin": pin}

    @app.get("/api/draft/{pin}")
    async def get_draft(pin: str):
        with _lock:
            draft = _drafts.get(pin)
        if not draft:
            return {"error": "코드가 없거나 만료됐습니다 (30분 유효)"}
        if datetime.utcnow() > draft["expires_at"]:
            with _lock:
                _drafts.pop(pin, None)
            return {"error": "코드가 만료됐습니다"}
        return draft["data"]

    # ── Replay 스킬 ──────────────────────────────────────────────
    class ReplayBody(BaseModel):
        ocr_task_id: str
        result_data: dict

    @app.post("/api/replay")
    async def start_replay(body: ReplayBody, user: UserInfo = Depends(_get_current_user)):
        from web_replayer import validate, run_skill

        skill_data, errors = validate(body.result_data)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})

        with _lock:
            file_paths = _tasks.get(body.ocr_task_id, {}).get("file_paths", [])

        tid = _new_task(user.username)
        run_cfg = {"author": user.author, "id": user.username, "password": ""}

        def _run():
            run_skill(task_id=tid, skill_data=skill_data, file_paths=file_paths,
                      cfg=run_cfg, status_cb=lambda ev, msg: _push(tid, ev, msg))

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": tid}

    @app.get("/api/replay/{tid}/stream")
    async def replay_stream(tid: str, user: UserInfo = Depends(_get_current_user)):
        return _sse(tid)

    @app.post("/api/replay/{tid}/submit")
    async def submit_replay(tid: str, user: UserInfo = Depends(_get_current_user)):
        from web_replayer import confirm_submit
        if not confirm_submit(tid):
            raise HTTPException(status_code=400, detail="제출 준비 안 됨")
        return {"ok": True}

    @app.post("/api/replay/{tid}/cancel")
    async def cancel_replay(tid: str, user: UserInfo = Depends(_get_current_user)):
        from web_replayer import cleanup_session
        cleanup_session(tid)
        _push(tid, "cancelled", "취소")
        return {"ok": True}

    # ── 정리 태스크 ───────────────────────────────────────────────
    async def _cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            cutoff = datetime.utcnow() - timedelta(hours=2)
            with _lock:
                expired = [k for k, v in _tasks.items()
                           if datetime.fromisoformat(v["created_at"]) < cutoff]
            for tid in expired:
                shutil.rmtree(TEMP_DIR / tid, ignore_errors=True)
                with _lock:
                    _tasks.pop(tid, None)

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(_cleanup_loop())


# ── 차단 HTML 헬퍼 ──────────────────────────────────────────────

def _blocked_html(reason: str = "") -> str:
    msg = reason or "BizOffice 포털 또는 SEON 포털에서 접근해주세요"
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>접근 불가 — Bill-stack</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Apple SD Gothic Neo','맑은 고딕',sans-serif;
     background:#F7F9FF;display:flex;align-items:center;
     justify-content:center;min-height:100vh;color:#1E2D45}}
.card{{background:#fff;border-radius:16px;padding:48px 40px;
      text-align:center;max-width:400px;
      box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.icon{{font-size:48px;margin-bottom:16px}}
h1{{font-size:18px;font-weight:800;margin-bottom:8px;color:#1B4FD8}}
p{{font-size:13px;color:#5A6A85;line-height:1.7}}
</style></head>
<body><div class="card">
  <div class="icon">🔒</div>
  <h1>접근 권한이 없습니다</h1>
  <p>{msg}</p>
</div></body></html>"""


# ── SSE 헬퍼 ────────────────────────────────────────────────────

def _sse(tid: str) -> StreamingResponse:
    async def generate():
        sent = 0
        while True:
            with _lock:
                task = _tasks.get(tid)
            if not task:
                yield 'data: {"event":"error","message":"task not found"}\n\n'
                return
            while sent < len(task["events"]):
                yield f"data: {json.dumps(task['events'][sent], ensure_ascii=False)}\n\n"
                sent += 1
            if task["done"]:
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── 독립 실행 ────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
