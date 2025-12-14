# src/config/kakaopay_settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class KakaoPaySettings(BaseSettings):
    # ✅ 핵심: extra="ignore" (다른 env 키들은 무시)
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    kakaopay_cid: str
    kakaopay_auth_scheme: str
    kakaopay_secret_key: str

    kakaopay_base_url: str
    kakaopay_approval_url: str
    kakaopay_cancel_url: str
    kakaopay_fail_url: str

    # optional
    kakaopay_app_return_scheme: str | None = None

kakaopay_settings = KakaoPaySettings()
