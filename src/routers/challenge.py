from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.models.challenge import (
    Challenges,
    DailyChallengePick,
    DailyChallengeUserState,
)
from src.models.users import User
from src.auth.dependencies import get_current_user

router = APIRouter(prefix="/challenges", tags=["챌린지"])

# 프리미엄 유저가 하루에 새로고침 가능한 최대 횟수
REFRESH_LIMIT = 3


# ----------------------------------------
# 유틸 함수들
# ----------------------------------------


def today_kst() -> date:
    """KST 기준 오늘 날짜 반환"""
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def get_user_state_today(
    db: Session,
    user: User,
    today: Optional[date] = None,
) -> Optional[DailyChallengeUserState]:
    """유저의 오늘자 daily 상태 조회 (없으면 None)"""
    if today is None:
        today = today_kst()

    return db.scalar(
        select(DailyChallengeUserState).where(
            DailyChallengeUserState.owner_cognito_id == user.cognito_id,
            DailyChallengeUserState.date_for == today,
        )
    )


def get_user_today_challenges(
    db: Session,
    user: User,
    today: Optional[date] = None,
) -> List[Challenges]:
    """
    유저별 오늘자 챌린지 4개 조회
    - DailyChallengePick 기반
    """
    if today is None:
        today = today_kst()

    return db.scalars(
        select(Challenges)
        .join(DailyChallengePick, DailyChallengePick.challenge_id == Challenges.id)
        .where(
            DailyChallengePick.owner_cognito_id == user.cognito_id,
            DailyChallengePick.date_for == today,
        )
        # slot_index 제거 → 정렬 기준 없애거나, challenge_id 기준으로 정렬
        #.order_by(DailyChallengePick.challenge_id)
    ).all()


def pick_and_store_user_today(
    db: Session,
    user: User,
    today: Optional[date] = None,
    *,
    replace: bool = False,
) -> List[Challenges]:
    """
    유저별 오늘자 챌린지 4개 랜덤 추출 + 저장

    - replace=False:
        - 이미 오늘자 데이터가 있으면, DB에 있는 것 그대로 사용
    - replace=True:
        - 오늘자 데이터를 전부 삭제하고 새로 4개 뽑아서 저장
    """
    if today is None:
        today = today_kst()

    # 이미 있는 거 재활용
    if not replace:
        existing = get_user_today_challenges(db, user, today)
        if existing:
            return existing

    # 오늘자 기존 데이터 삭제
    db.execute(
        delete(DailyChallengePick).where(
            DailyChallengePick.owner_cognito_id == user.cognito_id,
            DailyChallengePick.date_for == today,
        )
    )

    # 챌린지 4개 랜덤 추출
    picked: List[Challenges] = db.scalars(
        select(Challenges).order_by(func.rand()).limit(4)
    ).all()

    if not picked:
        return []

    # 🔥 slot_index 없이 그냥 challenge_id만 저장
    for c in picked:
        db.add(
            DailyChallengePick(
                owner_cognito_id=user.cognito_id,
                date_for=today,
                challenge_id=c.id,
            )
        )

    db.commit()
    return picked


# Pydantic 변환 헬퍼
def to_dto_list(challenges: List[Challenges]) -> List["ChallengeDTO"]:
    return [ChallengeDTO.model_validate(c) for c in challenges]


# ----------------------------------------
# DTO
# ----------------------------------------


class ChallengeDTO(BaseModel):
    id: int
    title: str
    subtitle: str
    give_point: int

    class Config:
        from_attributes = True


class DailyChallengeResponse(BaseModel):
    challenges: List[ChallengeDTO]
    refresh_remaining: int  # 3 → 2 → 1 → 0

    class Config:
        from_attributes = True


class RefreshRemainingResponse(BaseModel):
    remaining: int  # 남은 새로고침 횟수
    max: int        # 하루 최대 새로고침 횟수

    class Config:
        from_attributes = True


# ----------------------------------------
# API 엔드포인트
# ----------------------------------------


@router.get("/daily", response_model=DailyChallengeResponse)
def read_today_daily_challenges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    

    - 모든 유저가 "개인용" 4개를 가진다.
    - 처음 호출 시: 랜덤으로 4개 뽑아서 저장
    - 이후 호출 시: 이미 저장된 4개를 그대로 반환
    - 프리미엄 여부에 따라 refresh_remaining 값만 달라짐
    """
    today = today_kst()

    # 1) 유저 개인 daily 챌린지 가져오기 (없으면 새로 생성)
    picked = pick_and_store_user_today(db, current_user, today, replace=False)
    if not picked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="등록된 챌린지가 없습니다.",
        )

    # 2) 새로고침 남은 횟수 계산
    if not getattr(current_user, "is_premium", False):
        # 일반 유저는 새로고침 기능 없음
        remaining = 0
    else:
        state = get_user_state_today(db, current_user, today)
        if not state:
            remaining = REFRESH_LIMIT
        else:
            remaining = max(0, REFRESH_LIMIT - state.refresh_used)

    return DailyChallengeResponse(
        challenges=to_dto_list(picked),
        refresh_remaining=remaining,
    )


@router.get("/daily/refresh-remaining", response_model=RefreshRemainingResponse)
def get_refresh_remaining(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
 

    - 프리미엄 유저만 의미 있음
    - 일반 유저는 remaining=0, max=0 또는 remaining=0, max=REFRESH_LIMIT 중 택1
    """
    if not getattr(current_user, "is_premium", False):
        # 정책에 따라 max=0 으로 줄 수도 있고, max=REFRESH_LIMIT 로 줘도 됨
        return RefreshRemainingResponse(
            remaining=0,
            max=REFRESH_LIMIT,
        )

    today = today_kst()
    state = get_user_state_today(db, current_user, today)

    if not state:
        remaining = REFRESH_LIMIT
    else:
        remaining = max(0, REFRESH_LIMIT - state.refresh_used)

    return RefreshRemainingResponse(
        remaining=remaining,
        max=REFRESH_LIMIT,
    )


@router.post("/daily/refresh", response_model=DailyChallengeResponse)
def refresh_daily_challenges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    

    - 하루 최대 REFRESH_LIMIT 번
    - 호출 시 마다:
        1) 유저의 오늘자 새로고침 사용 횟수 확인
        2) 제한 넘으면 에러
        3) 넘지 않으면 유저 개인 daily를 새로 4개 뽑아서 저장
        4) refresh_used += 1
    """
    if not getattr(current_user, "is_premium", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="프리미엄 전용 기능입니다.",
        )

    today = today_kst()

    # 오늘자 state 조회 또는 생성
    state = get_user_state_today(db, current_user, today)
    if not state:
        state = DailyChallengeUserState(
            owner_cognito_id=current_user.cognito_id,
            date_for=today,
            refresh_used=0,
        )
        db.add(state)
        db.commit()
        db.refresh(state)

    if state.refresh_used >= REFRESH_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="오늘은 더 이상 새로고침할 수 없습니다.",
        )

    # 유저 개인 daily를 새로 뽑기 (replace=True)
    picked = pick_and_store_user_today(db, current_user, today, replace=True)
    if not picked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="등록된 챌린지가 없습니다.",
        )

    # 새로고침 사용 횟수 증가
    state.refresh_used += 1
    db.add(state)
    db.commit()
    db.refresh(state)

    remaining = max(0, REFRESH_LIMIT - state.refresh_used)

    return DailyChallengeResponse(
        challenges=to_dto_list(picked),
        refresh_remaining=remaining,
    )
