# src/auth/dependencies.py
from typing import TYPE_CHECKING
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi_cognito import CognitoToken

from src.auth.cognito_config import cognito_auth
from src.db.database import get_db

# (선택) 타입체킹 전용 임포트 – 런타임 순환 방지
if TYPE_CHECKING:
    from src.models.user.users import User

# (선택) Swagger 설명용 보안 스키마가 필요 없으면 삭제해도 됩니다.
from fastapi.security import HTTPBearer
security = HTTPBearer(
    scheme_name="HTTPBearer",
    description="Cognito JWT 토큰을 입력하세요"
)

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
