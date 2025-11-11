# src/routers/chat_lists.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session

from src.models.users import User
from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.chat_history import ChatHistory

router = APIRouter(prefix="/chats", tags=["채팅-목록"])

class ChatListItem(BaseModel):
    chat_list_num: int
    last_date: str
    last_time: str
    last_message: str | None = None

@router.get("/lists", response_model=List[ChatListItem])
def get_chat_lists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id

    # 각 방의 최신 메시지/갯수 추출 (PostgreSQL 기준; 다른 DB면 문법만 살짝 조정)
    sub = (
        db.query(
            ChatHistory.chat_list_num,
            ChatHistory.chat_date,
            ChatHistory.chat_time,
        )
        .filter(ChatHistory.owner_cognito_id == uid)
        .subquery()
    )

    rows = (
        db.query(
            ChatHistory.chat_list_num,
            ChatHistory.message.label("last_message"),
            ChatHistory.chat_date.label("last_date"),
            ChatHistory.chat_time.label("last_time"),
        )
        .filter(ChatHistory.owner_cognito_id == uid)
        .order_by(
            ChatHistory.chat_list_num.asc(),
            ChatHistory.chat_date.desc(),
            ChatHistory.chat_time.desc(),
            ChatHistory.chat_num.desc(),
        )
        .distinct(ChatHistory.chat_list_num)  # 최신 한 줄만
        .all()
    )

    items = []
    for r in rows:
        items.append(ChatListItem(
            chat_list_num=r.chat_list_num,
            last_message=r.last_message,
            last_date=str(r.last_date),
            last_time=str(r.last_time)
        ))
    return items


@router.delete("")  # DELETE /chats?list_no=1&list_no=2&list_no=3
def bulk_delete_chat_lists(
    list_no: List[int] = Query(..., description="삭제할 채팅방 번호들. 반복 파라미터로 전달"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    targets = list(set(list_no))  # 중복 제거
    if not targets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제할 방번호가 없습니다.")

    q = (
        db.query(ChatHistory)
          .filter(
              ChatHistory.owner_cognito_id == uid,
              ChatHistory.chat_list_num.in_(targets)
          )
    )
    deleted = q.delete(synchronize_session=False)
    db.commit()

    if deleted == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="삭제할 메시지가 없습니다.")
    return {"deleted_count": deleted, "chat_list_nums": targets}