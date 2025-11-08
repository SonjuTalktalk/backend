from src.config.settings import settings
from jwt.algorithms import RSAAlgorithm
import jwt
import time
import requests

# 앱 시작할 때 JWKS 한 번만 로드
jwks = requests.get(settings.cognito_jwks_url).json()

def verify_cognito_token(token: str):
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers["kid"]

        # JWKS에서 kid 일치하는 키 찾기
        key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if key is None:
            print("키 매칭 실패")
            return None

        public_key = RSAAlgorithm.from_jwk(key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
        )
        return payload

    except Exception as e:
        print("Token verification error:", e)
        return None