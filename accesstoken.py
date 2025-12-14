import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 👇 이미 사용 중인(DB에도 있는) 계정 정보 입력
EXISTING_PHONE = "+821030023970"  
EXISTING_PASSWORD = "Chris0412^^" 
# ==========================================

CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID")
REGION = os.getenv("COGNITO_REGION")

def get_token_simple():
    client = boto3.client('cognito-idp', region_name=REGION)
    print(f"--- 🚀 기존 계정 로그인 시도: {EXISTING_PHONE} ---")

    try:
        # 비밀번호 변경 없이 바로 로그인 시도
        resp = client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': EXISTING_PHONE, 
                'PASSWORD': EXISTING_PASSWORD
            }
        )
        
        access_token = resp['AuthenticationResult']['AccessToken']
        
        print("\n" + "="*50)
        print("✅ 토큰 발급 성공!")
        print("="*50)
        print(f"👇 [ Access Token ]:\n")
        print(access_token)
        print("="*50)

    except client.exceptions.NotAuthorizedException:
        print("\n❌ 실패: 아이디나 비밀번호가 틀렸습니다.")
    except client.exceptions.UserNotFoundException:
        print("\n❌ 실패: Cognito에 없는 사용자입니다.")
    except Exception as e:
        print(f"\n❌ 오류: {e}")

if __name__ == "__main__":
    get_token_simple()