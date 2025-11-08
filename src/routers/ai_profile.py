from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.user.users import User
from src.models.user.ai import AiProfile, Personality

router = APIRouter(prefix="/ai", tags=["AI 프로필"])

# 프로필 생성 요청 스키마
class CreateAiProfileRequest(BaseModel):
    nickname: str = Field(..., max_length=50)
    personality: Personality


# ai 프로필 생성
@router.post("", status_code=status.HTTP_201_CREATED)
def create_ai_profile(
    body: CreateAiProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    
    exists = db.query(AiProfile).filter(AiProfile.owner_cognito_id == current_user.cognito_id).first()
    if exists:
        raise HTTPException(status_code=409, detail="이미 AI 프로필이 존재합니다.")

    new_profile = AiProfile(
        owner_cognito_id=current_user.cognito_id,
        nickname=body.nickname,
        personality=body.personality,
    
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return {"message": "AI 프로필이 생성되었습니다.", "nickname": new_profile.nickname}



# 프로필 전체 조회 스키마
class AiProfileResponse(BaseModel):
    nickname: str
    personality: Personality

    class Config:
        from_attributes = True 


# ai프로필 전체 조회
@router.get("/me", response_model=AiProfileResponse)
def get_my_ai_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """로그인한 유저의 AI 프로필 전체 조회"""
    profile = db.query(AiProfile).filter(AiProfile.owner_cognito_id == current_user.cognito_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="AI 프로필이 없습니다.")
    return profile
 


# 닉네임 수정 요청 스키마
class NicknameUpdateRequest(BaseModel):
    new_nickname: str = Field(..., max_length=50)


# 닉네임 수정
@router.put("/nickname")
def update_my_nickname(
    body: NicknameUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
   
    profile = db.query(AiProfile).filter(AiProfile.owner_cognito_id == current_user.cognito_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="AI 프로필이 없습니다.")

    profile.nickname = body.new_nickname
    db.commit()
    db.refresh(profile)
    return {"message": "닉네임이 변경되었습니다.", "nickname": profile.nickname}


# 성격/말투/감정 수정 요청 스키마
class PrefsUpdateRequest(BaseModel):
    personality: Personality 


# 성격/말투/감정 수정
@router.put("/preferences", response_model=AiProfileResponse)
def update_preferences(
    body: PrefsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(AiProfile).filter(AiProfile.owner_cognito_id == current_user.cognito_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="AI 프로필이 없습니다.")

    if body.personality is not None:
        profile.personality = body.personality

    db.commit()
    db.refresh(profile)
    return profile