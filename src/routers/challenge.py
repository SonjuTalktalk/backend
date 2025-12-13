# src/routers/challenge.py
from __future__ import annotations

from datetime import datetime, date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from src.models.challenge import Challenges, DailyChallengePick, DailyChallengeUserState

router = APIRouter(prefix="/challenges", tags=["챌린지"])

# 프리미엄 새로고침 제한(너희 정책에 맞게 조정)
PREMIUM_REFRESH_LIMIT = 3


def today_kst() -> date:
    # 서버 타임존이 KST라고 가정 (main.py 스케줄러도 Asia/Seoul 사용)
    return datetime.now().date()


# --------------------- 내부 유틸 ---------------------
def ensure_state(db: Session, uid: str, day: date) -> DailyChallengeUserState:
    row = (
        db.query(DailyChallengeUserState)
        .filter(
            DailyChallengeUserState.owner_cognito_id == uid,
            DailyChallengeUserState.date_for == day,
        )
        .first()
    )
    if row is None:
        row = DailyChallengeUserState(owner_cognito_id=uid, date_for=day, refresh_used=0)
        db.add(row)
        db.flush()
    return row


def pick_4_random(db: Session) -> List[Challenges]:
    rows = db.query(Challenges).order_by(func.rand()).limit(4).all()
    if len(rows) < 4:
        raise HTTPException(500, "challenges 테이블에 최소 4개 이상 있어야 합니다.")
    return rows


def get_or_create_today_picks(db: Session, uid: str, day: date) -> List[DailyChallengePick]:
    picks = (
        db.query(DailyChallengePick)
        .options(joinedload(DailyChallengePick.challenge))
        .filter(
            DailyChallengePick.owner_cognito_id == uid,
            DailyChallengePick.date_for == day,
        )
        .all()
    )
    if picks:
        # slot_index가 없으니, UI 안정성을 위해 정렬(원하면 빼도 됨)
        picks.sort(key=lambda p: p.challenge_id)
        return picks

    challenges = pick_4_random(db)
    db.add_all(
        [
            DailyChallengePick(
                owner_cognito_id=uid,
                date_for=day,
                challenge_id=c.id,
                is_complete=False,
            )
            for c in challenges
        ]
    )
    db.commit()

    picks = (
        db.query(DailyChallengePick)
        .options(joinedload(DailyChallengePick.challenge))
        .filter(
            DailyChallengePick.owner_cognito_id == uid,
            DailyChallengePick.date_for == day,
        )
        .all()
    )
    picks.sort(key=lambda p: p.challenge_id)
    return picks


# --------------------- 스키마 ---------------------
class DailyChallengeItem(BaseModel):
    id: int
    title: str
    subtitle: str
    give_point: int
    is_complete: bool


class DailyChallengeResponse(BaseModel):
    date_for: date
    refresh_remaining: int
    challenges: List[DailyChallengeItem]


class RefreshDailyResponse(DailyChallengeResponse):
    pass


class CompleteDailyReq(BaseModel):
    challenge_id: int


class CompleteDailyRes(BaseModel):
    challenge_id: int
    is_complete: bool
    earned_point: int
    total_point: int


# --------------------- API ---------------------
@router.get("/daily", response_model=DailyChallengeResponse)
def get_daily(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    day = today_kst()

    picks = get_or_create_today_picks(db, uid, day)

    refresh_remaining = 0
    if current_user.is_premium:
        state = ensure_state(db, uid, day)
        refresh_remaining = max(0, PREMIUM_REFRESH_LIMIT - int(state.refresh_used))
        db.commit()  # state가 새로 생겼을 수도 있으니

    return DailyChallengeResponse(
        date_for=day,
        refresh_remaining=refresh_remaining,
        challenges=[
            DailyChallengeItem(
                id=p.challenge.id,
                title=p.challenge.title,
                subtitle=p.challenge.subtitle,
                give_point=int(p.challenge.give_point),
                is_complete=bool(p.is_complete),  # ✅ 프론트 체크 표시용
            )
            for p in picks
        ],
    )


@router.post("/daily/refresh", response_model=RefreshDailyResponse)
def refresh_daily(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    refresh 하면 완료된 챌린지도 그냥 날아가고 새로운 걸로 바뀌게
    -> 오늘 picks 통째로 삭제 후 새로 4개 생성
    """
    if not current_user.is_premium:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="프리미엄 전용 기능입니다.")

    uid = current_user.cognito_id
    day = today_kst()

    state = ensure_state(db, uid, day)
    if int(state.refresh_used) >= PREMIUM_REFRESH_LIMIT:
        raise HTTPException(status_code=400, detail="오늘 새로고침 횟수를 모두 사용했습니다.")

    # 완료 여부 상관없이 오늘 picks 전부 삭제
    db.query(DailyChallengePick).filter(
        DailyChallengePick.owner_cognito_id == uid,
        DailyChallengePick.date_for == day,
    ).delete(synchronize_session=False)

    challenges = pick_4_random(db)
    db.add_all(
        [
            DailyChallengePick(
                owner_cognito_id=uid,
                date_for=day,
                challenge_id=c.id,
                is_complete=False,
            )
            for c in challenges
        ]
    )

    state.refresh_used = int(state.refresh_used) + 1
    db.commit()

    picks = (
        db.query(DailyChallengePick)
        .options(joinedload(DailyChallengePick.challenge))
        .filter(
            DailyChallengePick.owner_cognito_id == uid,
            DailyChallengePick.date_for == day,
        )
        .all()
    )
    picks.sort(key=lambda p: p.challenge_id)

    refresh_remaining = max(0, PREMIUM_REFRESH_LIMIT - int(state.refresh_used))

    return RefreshDailyResponse(
        date_for=day,
        refresh_remaining=refresh_remaining,
        challenges=[
            DailyChallengeItem(
                id=p.challenge.id,
                title=p.challenge.title,
                subtitle=p.challenge.subtitle,
                give_point=int(p.challenge.give_point),
                is_complete=bool(p.is_complete),
            )
            for p in picks
        ],
    )


@router.post("/daily/complete", response_model=CompleteDailyRes)
def complete_daily(
    body: CompleteDailyReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    오늘의 picks 중 challenge_id 완료 처리 + 포인트 지급
    - 이미 완료면 idempotent(earned_point=0)
    """
    uid = current_user.cognito_id
    day = today_kst()

    # 동시 요청 시 포인트 중복 지급 방지용 row lock
    row = (
        db.query(DailyChallengePick)
        .options(joinedload(DailyChallengePick.challenge))
        .filter(
            DailyChallengePick.owner_cognito_id == uid,
            DailyChallengePick.date_for == day,
            DailyChallengePick.challenge_id == body.challenge_id,
        )
        .with_for_update()
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="오늘의 챌린지에 없는 항목입니다.")

    if row.is_complete:
        db.refresh(current_user)
        return CompleteDailyRes(
            challenge_id=body.challenge_id,
            is_complete=True,
            earned_point=0,
            total_point=int(current_user.point),
        )

    row.is_complete = True

    earned = int(row.challenge.give_point)
    current_user.point = int(current_user.point) + earned

    db.commit()
    db.refresh(current_user)

    return CompleteDailyRes(
        challenge_id=body.challenge_id,
        is_complete=True,
        earned_point=earned,
        total_point=int(current_user.point),
    )
