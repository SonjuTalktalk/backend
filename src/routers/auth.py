from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date
from src.db.database import get_db
from src.models.user.users import User
from src.auth.token_verifier import verify_cognito_token  # ✅ 네가 만든 토큰 검증 함수 import

router = APIRouter(prefix="/auth", tags=["인증"])

class LoginRequest(BaseModel):
    token: str  # Cognito ID Token 또는 Access Token


@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    로그인 엔드포인트
    - 앱이 Cognito 로그인 후 받은 토큰을 전달
    - 백엔드는 토큰을 검증한 뒤 DB 사용자 조회
    """

    # ✅ 1) Cognito 토큰 검증
    payload = verify_cognito_token(request.token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다."
        )

    # ✅ 2) Cognito sub(고유 ID) 가져오기
    cognito_sub = payload.get("sub")
    if not cognito_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="토큰에 sub(사용자 ID)가 없습니다."
        )

    # ✅ 3) DB에서 사용자 조회
    user = db.query(User).filter(User.cognito_id == cognito_sub).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="가입되지 않은 사용자입니다."
        )

    # ✅ 4) 로그인 성공 — 사용자 정보 반환
    return {
        "message": "로그인 성공",
        "user": {
            "cognito_id": user.cognito_id,
            "name": user.name,
            "phone_number": user.phone_number,
            "gender": user.gender,
            "birthdate": str(user.birthdate),
            "point": user.point,
        }
    }
    
