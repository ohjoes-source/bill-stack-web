# Bill-stack 통합 가이드

이 문서는 **기존 Next.js 사이트에 Bill-stack을 추가 서비스로 붙이는 방법**을 설명합니다.
Bill-stack은 BizOffice 지출결의서 자동 작성 FastAPI 서비스입니다.

---

## 서비스 흐름

```
BizOffice 포털 메뉴 클릭
  → GET /auth?sso=HEX&id=userId&type=employee   ← BizOffice 서버가 이 URL로 리다이렉트
  → RSA 복호화 → userId 획득
  → JWT 발급 → /?token=JWT[&setup=1] 로 리다이렉트
  → 사용자: 영수증 업로드 → OCR → 내역 확인 → Playwright 자동 입력 → 기안하기
```

---

## 1. BizOfficePlus RSA SSO 연결 (핵심 작업)

### 작동 원리

BizOffice 포털이 메뉴 클릭 시 등록된 서비스 URL로 리다이렉트합니다:

```
GET https://your-service.com/auth?sso=암호화된HexString&id=userId&type=employee
```

**암호화 체인 (BizOffice → 이 서비스)**
```
userId → ASCII bytes → Base64 문자열 → RSA PKCS#1 v1.5 암호화 → HexString
```

**복호화 체인 (이 서비스)**
```
HexString → bytes → RSA_PKCS1v15_decrypt(private_key) → Base64 문자열 → decode → userId
```

**폴백**: `sso=` 복호화 실패 시 `id=` 평문 파라미터를 사용합니다.

### 환경변수 설정

```env
AUTH_PROVIDER=rsa_sso

# 방법 A — PEM 직접 (개행을 \n으로)
RSA_PRIVATE_KEY_PEM=-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----

# 방법 B — Windows XML 형식 (<RSAKeyValue>...</RSAKeyValue>)
RSA_PRIVATE_KEY_XML=<RSAKeyValue><Modulus>...</Modulus>...</RSAKeyValue>
```

> **보안 주의**: 개인키는 절대 git에 커밋하지 마세요. 서버 환경변수에만 저장합니다.

### 구현 파일: `auth_providers/rsa_sso.py`

이미 구현되어 있습니다. 수정 없이 사용 가능합니다.

- `decrypt_sso_token(hex_string)` — `sso=` 파라미터 복호화
- `_xml_to_pem(xml_str)` — Windows XML 개인키 → PEM 변환

### 엔드포인트: `GET /auth`

`server.py`에 이미 구현되어 있습니다.

```
GET /auth?sso=HEX&id=userId&type=employee
  → userId 획득 (RSA 복호화 또는 id= 폴백)
  → JWT 발급
  → 이름 설정 있으면 → /?token=JWT
  → 이름 설정 없으면 → /?token=JWT&setup=1  (이름 입력 화면)
```

---

## 2. 기존 Next.js 사이트에 연결하는 두 가지 방법

### 방법 A — 독립 실행 + nginx 프록시 (권장)

Bill-stack을 별도 포트로 실행하고 nginx에서 프록시합니다.

```bash
# .env 설정 후
AUTH_PROVIDER=rsa_sso
RSA_PRIVATE_KEY_XML=<RSAKeyValue>...</RSAKeyValue>
SECRET_KEY=랜덤32자이상

# 실행
uvicorn server:app --host 127.0.0.1 --port 8001
```

```nginx
# nginx 설정
location /billstack/ {
    proxy_pass http://127.0.0.1:8001/;
    proxy_set_header Host $host;
}
```

BizOffice 포털에 등록할 URL: `https://your-site.com/billstack/auth`

### 방법 B — FastAPI에 마운트

기존 사이트도 FastAPI라면 앱 팩토리로 직접 마운트합니다:

```python
# 기존 main.py
import sys
sys.path.insert(0, "/path/to/bill-stack-web")
from server import create_app as create_billstack

main_app.mount("/billstack", create_billstack())
```

BizOffice 포털에 등록할 URL: `https://your-site.com/billstack/auth`

### 방법 C — Next.js에서 JWT 공유

기존 사이트가 이미 RSA SSO를 처리하고 JWT를 발급한다면,
Bill-stack이 그 JWT를 그대로 수락하도록 SECRET_KEY를 공유할 수 있습니다:

```env
AUTH_PROVIDER=external_jwt
EXTERNAL_JWT_SECRET=기존_사이트의_JWT_시크릿
EXTERNAL_JWT_ID_FIELD=sub      # JWT payload의 사용자 ID 필드명
EXTERNAL_JWT_AUTHOR_FIELD=name # JWT payload의 이름 필드명
```

이 경우 프론트엔드에서 기존 사이트 JWT를 `external_token` 필드로 POST `/api/login`에 넣어야 합니다.

---

## 3. 환경변수 전체 목록

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AUTH_PROVIDER` | `bizoffice` | `rsa_sso` / `bizoffice` / `external_jwt` |
| `RSA_PRIVATE_KEY_PEM` | — | RSA 개인키 PEM (개행 `\n`) |
| `RSA_PRIVATE_KEY_XML` | — | RSA 개인키 Windows XML 형식 |
| `OCR_PROVIDER` | `easyocr` | OCR 툴 |
| `SECRET_KEY` | *(변경 필수)* | JWT 서명 키 |
| `TOKEN_EXPIRE_HOURS` | `24` | JWT 만료 시간 |
| `APP_PREFIX` | `""` | 마운트 prefix (예: `/billstack`) |
| `EXTERNAL_JWT_SECRET` | — | external_jwt 방식 공유 시크릿 |
| `EXTERNAL_JWT_ID_FIELD` | `sub` | JWT payload 사용자 ID 필드 |
| `EXTERNAL_JWT_AUTHOR_FIELD` | `name` | JWT payload 이름 필드 |

---

## 4. 파일 구조

```
bill-stack-web/
├── server.py                   FastAPI 앱 (create_app() 팩토리)
│                                 GET /auth  — BizOffice SSO 콜백
│                                 POST /api/login — 직접 로그인 (bizoffice 모드)
│                                 GET /api/me — 현재 사용자 정보
│                                 PATCH /api/me — 이름 수정
│                                 POST /api/ocr — OCR 시작
│                                 POST /api/replay — 자동입력 시작
├── web_replayer.py             BizOffice 자동입력 스킬
├── auth_providers/
│   ├── __init__.py             AUTH_PROVIDER 라우터
│   ├── base.py                 AuthProvider 인터페이스
│   ├── rsa_sso.py              ← BizOfficePlus RSA SSO (구현 완료)
│   ├── bizoffice_playwright.py  직접 로그인 (개발/테스트용)
│   └── external_jwt.py         기존 JWT 공유 방식
├── ocr_providers/
│   └── easyocr_provider.py
└── static/index.html           프론트엔드 SPA
```

---

## 5. 자동입력 스킬 계약 (변경 금지)

```json
{
  "현장명": "강남 현장",
  "내역": [
    { "적요": "식대", "거래처": "홍길동식당", "금액": 45000 },
    { "적요": "교통비", "거래처": "카카오택시", "금액": 12000 }
  ]
}
```

- `현장명`: 필수, 비어있으면 기안 실패
- `내역`: 1~5개, 각 항목의 세 필드 모두 필수
- `금액`: 양의 정수 (원)

---

## 6. RSA 개인키 등록 절차 (BizOffice 관리자)

1. 공개키/개인키 쌍 생성 (BizOffice 담당자가 제공하거나 서비스 측에서 생성)
2. 공개키를 BizOffice 서버에 등록 (서비스 URL 함께 등록)
3. 개인키를 Bill-stack 서버 환경변수에 저장 (`RSA_PRIVATE_KEY_XML` 또는 `RSA_PRIVATE_KEY_PEM`)
4. BizOffice 포털 메뉴에서 서비스 URL을 `https://your-service.com/auth`로 설정
