# Bill-Stack Web — 관리 가이드

## 서비스 정보

| 항목 | 내용 |
|------|------|
| 서비스 URL | https://determined-possibility-production.up.railway.app |
| 인증 경로 | `/auth?token=<JWT>` (SEON 포털) · `/auth?sso=<RSA>` (BizOffice) |
| Railway 프로젝트 | `determined-possibility` (axlab18-dot's Projects) |
| OCR 엔진 | Claude API vision (claude-haiku-4-5) |

---

## 환경변수 (Railway 대시보드에서 설정)

| 변수 | 값 | 설명 |
|------|----|------|
| `SECRET_KEY` | `bill-stack-secret-2026` | JWT 서명 키 |
| `TOKEN_EXPIRE_HOURS` | `24` | JWT 만료 시간 |
| `OCR_PROVIDER` | `claude` | OCR 엔진 |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | Claude API 키 |

> Railway 대시보드 → 서비스 → Variables 탭에서 확인·수정

---

## 다른 PC에서 배포하는 방법

### 1. 사전 준비

```bash
# Node.js 설치 확인 (railway CLI 필요)
node -v

# Railway CLI 설치
npm install -g @railway/cli

# Railway 로그인 (GitHub 계정)
railway login
```

### 2. 폴더 열기 및 프로젝트 연결

```bash
cd "004 bill-stack-web"

# Railway 프로젝트 연결
railway link
# → 프로젝트 목록에서 "determined-possibility" 선택
# → 환경: production
# → 서비스: determined-possibility
```

### 3. 코드 수정 후 배포

```bash
# 배포
railway up --service determined-possibility

# 배포 상태 확인
railway status
```

---

## 폴더 구조

```
004 bill-stack-web/
├── server.py              # FastAPI 메인 서버
├── requirements.txt       # 프로덕션 의존성 (경량)
├── requirements-full.txt  # 전체 의존성 (로컬 개발용)
├── railway.toml           # Railway 빌드·배포 설정
├── .env                   # 로컬 개발용 환경변수 (배포 X)
├── static/
│   └── index.html         # 프론트엔드 전체 (SPA)
├── auth_providers/
│   ├── seon_provider.py   # SEON 포털 SSO (토큰 검증)
│   └── bizoffice_provider.py  # BizOffice SSO (RSA 복호화)
└── ocr_providers/
    ├── __init__.py
    └── claude_provider.py # Claude API vision OCR
```

---

## 주요 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/auth` | SSO 로그인 (token= 또는 sso= 파라미터) |
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

SEON 포털 DB에서 아래 SQL 실행 필요:

```sql
UPDATE tools
SET href = 'https://determined-possibility-production.up.railway.app/auth'
WHERE id = 'expense-ocr';
```

담당자: 오지호

---

## 로컬 개발 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn server:app --reload --port 8000

# 접속
http://localhost:8000
```

---

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| `사용자 설정 없음` 오류 | 구버전 코드 캐시 | 북마클릿 재설치 |
| 팝업 차단 | 브라우저 팝업 차단 | 주소창 팝업 허용 클릭 |
| OCR 오류 | ANTHROPIC_API_KEY 만료 | Railway 환경변수 재설정 |
| PIN 만료 | 30분 초과 | 앱에서 기안하기 다시 클릭 |
| Railway 배포 실패 | requirements.txt 문제 | `requirements-full.txt` 내용 확인 금지, `requirements.txt` 유지 |
