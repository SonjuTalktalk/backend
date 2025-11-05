
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
from src.models.user.challenge import Challenges, DailyChallengePick

router = APIRouter(prefix="/challenges", tags=["챌린지"])

# 반환용 스키마 정의
class ChallengeDTO(BaseModel):
    id: int
    title: str
    subtitle: str
    give_point: int

    class Config:
        from_attributes = True

# 오늘 날짜 KST 기준 함수
KST = ZoneInfo("Asia/Seoul")
def today_kst() -> date:
    return datetime.now(KST).date()

# 날짜로 오늘자 챌린지 조회 함수
def get_today(db: Session):
    today = today_kst()
    return db.scalars(
        select(Challenges)
        .join(DailyChallengePick, DailyChallengePick.challenge_id == Challenges.id)
        .where(DailyChallengePick.date_for == today)
    ).all()

# ── 오늘자 저장/생성 ───────────────────────────────────────────
def pick_and_store_today(db: Session, *, replace: bool = False):
    """
    오늘자 챌린지 4개를 보장해서 반환.
    replace=True 이면 오늘 데이터가 있어도 '삭제→재뽑기' 수행(개발/테스트용).
    기본은 자정 스케줄러가 1회 생성하고, 요청시에는 기존 데이터만 읽음.
    """
    today = today_kst()

    if not replace:
        existing = get_today(db)
        if existing:
            return existing

    # 오늘자 레코드 정리(강제 재뽑기 or 최초 생성 전 안전 보정)
    db.execute(delete(DailyChallengePick).where(DailyChallengePick.date_for == today))

    # MySQL 고정: RAND() 기반 랜덤 4개  
    picked = db.scalars(
        select(Challenges).order_by(func.rand()).limit(4)
    ).all()

    if not picked:
        return []

    for c in picked:
        db.add(DailyChallengePick(date_for=today, challenge_id=c.id))
    db.commit()
    return picked

# ── API: 오늘자 조회(없으면 생성) ─────────────────────────────
@router.get("/daily", response_model=List[ChallengeDTO])
def read_today_daily_challenges(db: Session = Depends(get_db)):
    rows = get_today(db)
    if rows:
        return rows

    rows = pick_and_store_today(db)
    if not rows:
        raise HTTPException(status_code=404, detail="등록된 챌린지가 없습니다.")
    return rows

# ── API(개발용): 강제 재뽑기 ───────────────────────────────────
@router.post("/daily/force-repick", response_model=List[ChallengeDTO])
def force_repick(db: Session = Depends(get_db)):
    rows = pick_and_store_today(db, replace=True)
    if not rows:
        raise HTTPException(status_code=404, detail="등록된 챌린지가 없습니다.")
    return rows
