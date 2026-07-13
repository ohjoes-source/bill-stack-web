"""
BizOfficePlus RSA SSO 인증 프로바이더

BizOffice가 메뉴 클릭 시 다음 URL로 리다이렉트합니다:
  https://your-service.com/auth?sso=암호화된HexString&id=userId&type=employee

암호화 체인 (BizOffice 서버 → 이 서비스):
  userId → ASCII bytes → Base64 문자열 → RSA PKCS#1 v1.5 암호화 → HexString

복호화 체인 (이 서비스):
  HexString → bytes → RSA 복호화 → Base64 문자열 → decode → userId

환경변수:
  RSA_PRIVATE_KEY_PEM  — PEM 형식 개인키 (개행은 \\n 으로)
  RSA_PRIVATE_KEY_XML  — Windows XML 형식 개인키 (<RSAKeyValue>...</RSAKeyValue>)
  (PEM 우선, 없으면 XML 자동 변환)
"""
import base64
import os
import xml.etree.ElementTree as ET
from .base import AuthProvider, AuthResult


def _xml_to_pem(xml_str: str) -> str:
    """Windows <RSAKeyValue> XML 형식 → PEM 변환"""
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateNumbers, RSAPublicNumbers
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

    def b64int(tag: str) -> int:
        val = ET.fromstring(xml_str).find(tag)
        if val is None:
            raise ValueError(f"XML에 <{tag}> 태그가 없습니다")
        return int.from_bytes(base64.b64decode(val.text.strip()), "big")

    pub = RSAPublicNumbers(b64int("Exponent"), b64int("Modulus"))
    priv = RSAPrivateNumbers(
        p=b64int("P"), q=b64int("Q"), d=b64int("D"),
        dmp1=b64int("DP"), dmq1=b64int("DQ"), iqmp=b64int("InverseQ"),
        public_numbers=pub,
    )
    key = priv.private_key()
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


def _load_private_key():
    pem = os.getenv("RSA_PRIVATE_KEY_PEM", "").replace("\\n", "\n")
    if not pem:
        xml = os.getenv("RSA_PRIVATE_KEY_XML", "")
        if not xml:
            raise RuntimeError("RSA_PRIVATE_KEY_PEM 또는 RSA_PRIVATE_KEY_XML 환경변수가 필요합니다")
        pem = _xml_to_pem(xml)

    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    return load_pem_private_key(pem.encode(), password=None)


def decrypt_sso_token(hex_string: str) -> str:
    """BizOffice sso= 파라미터 복호화 → userId 반환"""
    from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
    key = _load_private_key()
    encrypted = bytes.fromhex(hex_string)
    decrypted = key.decrypt(encrypted, PKCS1v15())
    # 복호화 결과는 Base64(userId)
    return base64.b64decode(decrypted.decode("ascii").strip()).decode("utf-8")


class RsaSsoAuth(AuthProvider):
    """
    이 프로바이더는 직접 authenticate()로 사용하지 않습니다.
    server.py 의 GET /auth 엔드포인트에서 decrypt_sso_token()을 직접 호출합니다.

    기존 Next.js 사이트에서 토큰을 전달받는 경우:
      credentials["user_id"]  = 복호화된 userId
      credentials["author"]   = 한글 이름 (사이트에서 알고 있는 경우)
    """
    def authenticate(self, credentials: dict) -> AuthResult:
        user_id = credentials.get("user_id", "").strip()
        author  = credentials.get("author", "").strip()
        if not user_id:
            return AuthResult(False, "", "", "user_id가 없습니다")
        return AuthResult(True, user_id, author or user_id)
