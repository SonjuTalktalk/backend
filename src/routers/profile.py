# 프로필 관련 API 엔드포인트 (사용자 정보 조회)
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from src.models.users import User
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
    is_premium : bool   
    
    class Config:
        from_attributes = True  


# 이름 수정 스키마
class NameUpdateRequest(BaseModel):
    new_name: str


class PremiumUpdateRequest(BaseModel):
    is_premium: bool

class PointEarnRequest(BaseModel):
    point: int
      
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


@router.put("/me/premium", status_code=status.HTTP_200_OK)
async def update_my_premium(
    body: PremiumUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.is_premium = body.is_premium
    db.commit()
    db.refresh(current_user)
    return {
        "message": "프리미엄 상태가 변경되었습니다.",
        "is_premium": current_user.is_premium,
    }
    
@router.post("/me/point/earn", status_code=status.HTTP_200_OK)
async def earn_point(
    body: PointEarnRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.point <= 0:
        raise HTTPException(400, "amount는 양수여야 합니다.")
    
    # 여기서 따로 <= 0 체크 안 해도 됨 (conint가 막아줌)
    current_user.point += body.point
    db.commit()
    db.refresh(current_user)
    return {
        "message": "포인트가 적립되었습니다.",
        "point": current_user.point,
    }
    

@router.post("/me/point/reset(test_ver)", status_code=status.HTTP_200_OK)
async def reset_my_point(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    current_user.point = 0
    db.commit()
    db.refresh(current_user)
    return {
        "message": "포인트가 0으로 초기화되었습니다.",
        "point": current_user.point,
    }