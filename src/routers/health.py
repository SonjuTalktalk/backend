# src/routers/health.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import date
from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from sqlalchemy.orm import Session
from sqlalchemy import and_
from src.models.health_diary import HealthDiary

router = APIRouter(prefix="/health", tags=["건강"])

class CreateHealthDiary(BaseModel):
    diary_date: date
    diary_text: str

@router.post("/diaries")
def create_ai_profile(
    body: CreateHealthDiary,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    
    diary = db.query(HealthDiary).filter(
        and_(
            HealthDiary.cognito_id == current_user.cognito_id,
            HealthDiary.diary_date == body.diary_date
        )
    ).first()

    if diary:
        diary.diary_text = body.diary_text
        db.commit()
        db.refresh(diary)
        return {
            "message": "건강 일기가 수정되었습니다.",
            "date": diary.diary_date
        }
    else:
        new_diary = HealthDiary(
            cognito_id=current_user.cognito_id,
            diary_date=body.diary_date,
            diary_text=body.diary_text,
        )
        db.add(new_diary)
        db.commit()
        db.refresh(new_diary)
        return {
            "message": "건강 일기가 등록되었습니다.", 
            "date": new_diary.diary_date
        }
   