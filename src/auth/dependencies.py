from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi_cognito import CognitoToken

from src.auth.cognito_config import cognito_auth
from src.db.database import get_db
from src.models.user.users import User

async def get_current_user_cognito_id(
    token: CognitoToken = Depends(cognito_auth.auth_required)  # 메서드 호출
) -> str:
    """
    Cognito 토큰에서 사용자 ID 추출
    """
    cognito_id = token.get("sub")
    if not cognito_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 ID(sub)가 없습니다",
        )
    return cognito_id

async def get_current_user(
    cognito_id: str = Depends(get_current_user_cognito_id),
    db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter(User.cognito_id == cognito_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다. 회원가입이 필요합니다."
        )
    return user