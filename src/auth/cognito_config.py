
import os
from dotenv import load_dotenv
from fastapi_cognito import CognitoAuth, CognitoSettings

load_dotenv()

cognito_settings = CognitoSettings(
    check_expiration=True,
    jwt_header_name="Authorization",
    jwt_header_prefix="Bearer",  
    userpools={
        "default": {
            "region": os.getenv("COGNITO_REGION"),
            "userpool_id": os.getenv("COGNITO_USER_POOL_ID"),
            "app_client_id": os.getenv("COGNITO_APP_CLIENT_ID"),
        }
    },
)

cognito_auth = CognitoAuth(settings=cognito_settings)

