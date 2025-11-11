# token_verifier.py
import json
import jwt
import requests
from jwt.algorithms import RSAAlgorithm
from datetime import timedelta
from src.config.settings import settings  

# 기존과 동일: 앱 시작 시 JWKS 1회 로드 
jwks = requests.get(settings.cognito_jwks_url).json()

_ISS = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"

def public_key_for(token: str):
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if not key:
        return None
    key_str = json.dumps(key)
    return RSAAlgorithm.from_jwk(key_str)

def verify_id_token(token: str):
    """
    기존 ID 토큰 검증 (audience 검사 포함) — 변경 없음
    """
    try:
        public_key = public_key_for(token)
        if public_key is None:
            return None
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=_ISS,
        )
        # (선택) token_use 확인
        if payload.get("token_use") and payload.get("token_use") != "id":
            return None
        return payload
    except Exception:
        return None

def verify_cognito_access_token(token: str):
    """
    Access 토큰 검증:
    - RS256 서명 / iss / exp
    - audience 미검증(options.verify_aud=False)
    - token_use == "access"
    - client_id == 앱 클라 ID
    """
    try:
        public_key = public_key_for(token)
        if public_key is None:
            return None
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            issuer=_ISS,
        )
        if payload.get("token_use") != "access":
            return None
        if payload.get("client_id") != settings.cognito_app_client_id:
            return None
        return payload
    except Exception:
        return None
