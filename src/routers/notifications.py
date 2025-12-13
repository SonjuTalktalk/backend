import datetime as dt
from zoneinfo import ZoneInfo
from typing import List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import asc

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.users import User
from src.models.notification import Notification


KST = ZoneInfo("Asia/Seoul")

router = APIRouter(prefix="/notifications", tags=["알림"])


class NotificationCreateReq(BaseModel):
    title: str
    text: str


class NotificationItem(BaseModel):
    notification_id: int
    title: str
    text: str
    date: str
    time: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_notification(
    body: NotificationCreateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    
    """
    [프론트용 요약]

    ✅ POST /notifications
    - 설명: 로그인 유저의 알림 1개 생성
    - 인증: Authorization: Bearer <access_token> 필수
    - Request JSON:
        {
          "title": "string",
          "text": "string"
        }
    - Response (201):
        {
          "notification_id": 123
        }

    🔸 저장 규칙
    - 서버가 KST 기준 현재 시각을 잡아서
      noti_date(날짜), noti_time(시간)을 자동 저장함
    - owner_cognito_id는 토큰에서 꺼낸 current_user.cognito_id로 자동 저장됨
    """


    now = dt.datetime.now(KST).replace(microsecond=0)

    row = Notification(
        owner_cognito_id=current_user.cognito_id,
        title=body.title,
        text=body.text,
        noti_date=now.date(),
        noti_time=now.time(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {"notification_id": row.notification_id}


@router.get("", response_model=List[NotificationItem])
async def get_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    [프론트용 요약]

    ✅ GET /notifications
    - 설명: 로그인 유저의 알림 목록 전체 조회
    - 인증: Authorization: Bearer <access_token> 필수
    - Response (200): 배열
        [
          {
            "notification_id": 1,
            "title": "...",
            "text": "...",
            "date": "2025-12-13",
            "time": "10:30:00"
          }
        ]

    🔸 내장 정렬 규칙
    - "날짜 빠른 게 위로" = 오래된 알림부터 위로 보이게
      noti_date ASC, noti_time ASC, notification_id ASC
    """
    
    rows = (
        db.query(Notification)
        .filter(Notification.owner_cognito_id == current_user.cognito_id)
        .order_by(
            asc(Notification.noti_date),
            asc(Notification.noti_time),
            asc(Notification.notification_id),
        )
        .all()
    )

    return [
        NotificationItem(
            notification_id=r.notification_id,
            title=r.title,
            text=r.text,
            date=r.noti_date.isoformat(),
            time=r.noti_time.strftime("%H:%M:%S"),
        )
        for r in rows
    ]


@router.delete("", status_code=status.HTTP_200_OK)
async def clear_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    
    """
    [프론트용 요약]

    DELETE /notifications
    - 설명: 로그인 유저의 알림을 전부 삭제(초기화 버튼 용)
    - 인증: Authorization: Bearer <access_token> 필수
    - Response (200):
        {
          "deleted": 5
        }
      (deleted = 삭제된 행 개수)
    """
    
    deleted = (
        db.query(Notification)
        .filter(Notification.owner_cognito_id == current_user.cognito_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}
