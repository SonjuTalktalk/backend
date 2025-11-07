# 프로필 관련 API 엔드포인트 (사용자 정보 조회)
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from src.models.user.users import User
from src.auth.dependencies import get_current_user
from src.db.database import get_db

router = APIRouter(prefix="/profile", tags=["프로필"])

# 사용자 프로필 응답 스키마
class UserProfileResponse(BaseModel):
    phone_number: str
    name: str
    gender: str
    birthdate: date
    point: int

    class Config:
        from_attributes = True  


# 이름 수정 스키마
class NameUpdateRequest(BaseModel):
    new_name: str

# 이름 수정 
@router.put("/me/name", status_code=status.HTTP_200_OK)
async def update_my_name(
    body: NameUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.name = body.new_name
    db.commit()
    db.refresh(current_user)
    return {"message": "이름이 성공적으로 변경되었습니다.", "name": current_user.name}

# 전체 프로필 보기
@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


# 계정 삭제 
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.delete(current_user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)