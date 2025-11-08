from src.config.settings import settings
import requests
import time
from jose import jwk

jwks_cache = {
    "keys": None,
    "expires_at": 0
}

def get_jwks():
    now = time.time()

    if jwks_cache["keys"] and now < jwks_cache["expires_at"]:
        return jwks_cache["keys"]

    res = requests.get(settings.cognito_jwks_url)
    res_json = res.json()

    keys = {k["kid"]: jwk.construct(k) for k in res_json["keys"]}

    jwks_cache["keys"] = keys
    jwks_cache["expires_at"] = now + 60 * 60 # 1시간 캐싱
    return keys