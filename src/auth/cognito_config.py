# src/auth/cognito_config.py  ✅ 정답 버전
import os
from dotenv import load_dotenv
from fastapi_cognito import CognitoAuth, CognitoSettings

load_dotenv()

cognito_settings = CognitoSettings(
    check_expiration=True,
    jwt_header_name="Authorization",
    jwt_header_prefix="Bearer",  # Swagger가 Bearer 자동 부착
    userpools={
        "default": {
            "region": os.getenv("COGNITO_REGION"),
            "userpool_id": os.getenv("COGNITO_USER_POOL_ID"),
            "app_client_id": os.getenv("COGNITO_APP_CLIENT_ID"),
        }
    },
)

cognito_auth = CognitoAuth(settings=cognito_settings)

