# AWS Cognito 설정 및 JWT 검증 인스턴스
import os
from dotenv import load_dotenv
from fastapi_cognito import CognitoAuth, CognitoSettings

load_dotenv()

cognito_settings = CognitoSettings(
    check_expiration=True,                          # JWT의 exp(만료 시간) 검사를 할지 여부 (True 권장)
    jwt_header_name="Authorization",                # JWT가 담긴 헤더 이름
    jwt_header_prefix="Bearer",                     # JWT 앞에 붙는 접두어
    userpools={
        "default": {
            "region": os.getenv("COGNITO_REGION"),
            "userpool_id": os.getenv("COGNITO_USER_POOL_ID"),
            "app_client_id": os.getenv("COGNITO_APP_CLIENT_ID"),
   
        }
    },
)

cognito_auth = CognitoAuth(settings=cognito_settings)  # fastapi-cognito 라이브러리가 실제 인증 객체를 생성, 다른 파일에서 verify(token) 메서드로 JWT 검증에 사용
