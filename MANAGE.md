# Bill-Stack Web — 관리 가이드

## 서비스 정보

| 항목 | 내용 |
|------|------|
| 서비스 URL | https://bill-stack-web.onrender.com |
| 인증 경로 | `/auth?token=<JWT>` (SEON 포털) |
| Render 서비스 ID | `srv-d9a9fpurnols739uacag` |
| GitHub 레포 | `ohjoes-source/bill-stack-web` (main 브랜치) |
| OCR 엔진 | Google Gemini 2.0 Flash |

> **Free 플랜 주의**: 비활성 상태 50초+ 지연 발생 (스핀다운)

---

## 환경변수 (Render 대시보드 → Environment)

| 변수 | 값 | 설명 |
|------|----|------|
| `SECRET_KEY` | `bill-stack-secret-2026` | JWT 서명 키 |
| `TOKEN_EXPIRE_HOURS` | `24` | JWT 만료 시간 |
| `OCR_PROVIDER` | `gemini` | OCR 엔진 |
| `GEMINI_API_KEY` | `AIzaSyDJfhx7s-oKJMm-lHYWNP1vZlw8Z-ERMTk` | Gemini API 키 |
| `AUTH_PROVIDER` | `seon_portal` | 인증 방식 |

---

## 배포 방법 (GitHub 연동 자동배포)

```bash
# 코드 수정 후 GitHub에 push하면 자동 배포됨
git add .
git commit -m "변경 내용"
git push origin main
```

Render 대시보드에서 배포 상태 확인: https://dashboard.render.com/web/srv-d9a9fpurnols739uacag

---

## 폴더 구조

```
004 bill-stack-web/
├── server.py              # FastAPI 메인 서버
├── requirements.txt       # 프로덕션 의존성 (경량)
├── requirements-full.txt  # 전체 의존성 (로컬 개발용)
├── .env                   # 로컬 개발용 환경변수 (배포 X)
├── static/
│   └── index.html         # 프론트엔드 전체 (SPA)
├── auth_providers/
│   └── seon_portal.py     # SEON 포털 SSO (토큰 검증)
└── ocr_providers/
    ├── __init__.py
    ├── gemini_provider.py # Google Gemini Vision OCR
    └── claude_provider.py # Claude API vision OCR (대체용)
```

---

## 주요 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/auth` | SSO 로그인 (token= 파라미터) |
| `POST` | `/api/ocr` | 영수증 OCR 분석 |
| `POST` | `/api/draft` | PIN 생성 및 기안 데이터 저장 |
| `GET` | `/api/draft/{pin}` | PIN으로 기안 데이터 조회 (북마클릿용) |

---

## 북마클릿 동작 원리

1. 사용자가 앱에서 영수증 OCR → 내역 확인 → **기안하기** 클릭
2. 서버에 데이터 저장 → **4자리 PIN** 발급 (30분 유효)
3. 사용자가 어느 탭에서든 **북마클릿 클릭**
4. 지출결의서 팝업이 자동으로 열림
5. PIN 입력 → 서버에서 데이터 조회 → **폼 자동 입력**

---

## SEON 포털 연동

SEON 포털 DB(Supabase) tools 테이블에서:

```sql
UPDATE tools
SET href = 'https://bill-stack-web.onrender.com/auth'
WHERE id = 'expense-ocr';
```

---

## 로컬 개발 실행

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
# 접속: http://localhost:8000
```

---

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 첫 요청 50초 지연 | Free 플랜 스핀다운 | 기다리거나 Paid 업그레이드 |
| `사용자 설정 없음` 오류 | 구버전 코드 캐시 | 북마클릿 재설치 |
| 팝업 차단 | 브라우저 팝업 차단 | 주소창 팝업 허용 클릭 |
| OCR 오류 | GEMINI_API_KEY 문제 | Render Environment 탭 확인 |
| PIN 만료 | 30분 초과 | 앱에서 기안하기 다시 클릭 |
