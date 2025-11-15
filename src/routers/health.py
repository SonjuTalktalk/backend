# src/routers/health.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import date
from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from sqlalchemy.orm import Session
from sqlalchemy import and_
from src.models.health_memo import HealthMemo

router = APIRouter(prefix="/health", tags=["건강"])

class CreateHealthMemo(BaseModel):
    memo_date: date
    memo_text: str

@router.post("/memos")
def create_health_memo(
    body: CreateHealthMemo,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    
    memo = db.query(HealthMemo).filter(
        and_(
            HealthMemo.cognito_id == current_user.cognito_id,
            HealthMemo.memo_date == body.memo_date
        )
    ).first()

    if memo:
        memo.memo_text = body.memo_text
        db.commit()
        db.refresh(memo)
        return {
            "message": "건강 일기가 수정되었습니다.",
            "date": memo.memo_date
        }
    else:
        new_memo = HealthMemo(
            cognito_id=current_user.cognito_id,
            memo_date=body.memo_date,
            memo_text=body.memo_text,
        )
        db.add(new_memo)
        db.commit()
        db.refresh(new_memo)
        return {
            "message": "건강 일기가 등록되었습니다.", 
            "date": new_memo.memo_date
        }
   