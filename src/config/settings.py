# src/config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    cognito_region: str
    cognito_user_pool_id: str
    cognito_app_client_id: str
    cognito_jwks_url: str

    db_user: str
    db_pass: str
    db_host: str
    db_port: int
    db_name: str
    
    class Config:
        env_file = ".env"


settings = Settings()