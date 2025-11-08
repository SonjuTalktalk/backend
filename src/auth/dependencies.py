# src/auth/dependencies.py
from typing import TYPE_CHECKING
from fastapi import Depends, HTTPException, status
from fastapi import Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from fastapi_cognito import CognitoToken

from src.auth.cognito_config import cognito_auth
from src.db.database import get_db
from src.models.user.users import User
from src.auth.token_verifier import verify_cognito_token
security = HTTPBearer()                 # FastAPI의 내장 HTTPBearer 보안 스키마를 사용해서 클라이언트 요청의 헤더에 포함된 토큰을 자동으로 추출


'''
async def get_current_user_cognito_id(
    # access 토큰을 쓰고 있다면 access_auth_required로 바꿔도 됩니다.
    token: CognitoToken = Depends(cognito_auth.auth_required)
) -> str:
    cognito_id = token.get("sub")
    if not cognito_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 ID(sub)가 없습니다"
        )
    return cognito_id

async def get_current_user(
    cognito_id: str = Depends(get_current_user_cognito_id),
    db: Session = Depends(get_db)
):
    # ✅ 순환 방지: 런타임 시점에 임포트
    from src.models.user.users import User

    user = db.query(User).filter(User.cognito_id == cognito_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다. 회원가입이 필요합니다."
        )
    return user
'''

def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth:
        raise HTTPException(401, "인증 헤더 없음")
    
    token = auth.replace("Bearer ", "")
    jwks = get_jwks()

    try:
        payload = verify_cognito_token(token, jwks)
    except Exception:
        raise HTTPException(401, "유효하지 않거나 만료된 토큰")
    
    return payload