
# src/routers/challenge.py
from __future__ import annotations
from datetime import datetime, date
from typing import List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.models.challenge import Challenges, DailyChallengePick

router = APIRouter(prefix="/challenges", tags=["챌린지"])

#데일리 테이블 스키마
class ChallengeDTO(BaseModel):
    id: int
    title: str
    subtitle: str
    give_point: int

    class Config:
        from_attributes = True

# 오늘 날짜 반환
KST = ZoneInfo("Asia/Seoul")
def today_kst() -> date:
    return datetime.now(KST).date()

# 날짜로 오늘자 챌린지 조회 
def get_today(db: Session):
    today = today_kst()
    return db.scalars(
        select(Challenges)
        .join(DailyChallengePick, DailyChallengePick.challenge_id == Challenges.id)
        .where(DailyChallengePick.date_for == today)
    ).all()

# 오늘자 챌린지 뽑기
def pick_and_store_today(db: Session, *, replace: bool = False):

    today = today_kst()

    if not replace:
        existing = get_today(db)
        if existing:
            return existing

    # 기존 오늘자 데이터 삭제
    db.execute(delete(DailyChallengePick).where(DailyChallengePick.date_for == today))

    # 챌린지 4개 무작위 추출
    picked = db.scalars(
        select(Challenges).order_by(func.rand()).limit(4)
    ).all()

    if not picked:
        return []

    for c in picked:
        db.add(DailyChallengePick(date_for=today, challenge_id=c.id))
    db.commit()
    return picked


#오늘자 조회 챌린지 조회
@router.get("/daily", response_model=List[ChallengeDTO])
def read_today_daily_challenges(db: Session = Depends(get_db)):
    rows = get_today(db)
    if rows:
        return rows

    rows = pick_and_store_today(db)
    if not rows:
        raise HTTPException(status_code=404, detail="등록된 챌린지가 없습니다.")
    return rows

