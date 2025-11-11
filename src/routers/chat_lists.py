# src/routers/chat_lists.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import List
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.users import User
from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.chat_history import ChatHistory

router = APIRouter(prefix="/chats", tags=["채팅-목록"])

class ChatListItem(BaseModel):
    chat_list_num: int
    last_date: str
    # last_time: str
    last_message: str | None = None

@router.get("/lists", response_model=List[ChatListItem])
def get_last_messages_of_each_room(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    각 방에서 '가장 마지막 메시지'만 뽑아서,
    last_date DESC → last_time DESC → chat_num DESC 로 정렬해 반환
    """
    uid = current_user.cognito_id

    # 윈도우 함수로 각 방의 최신 1건(rn=1)만 추려내기
    subq = (
        db.query(
            ChatHistory.chat_list_num,
            ChatHistory.message.label("last_message"),
            ChatHistory.chat_date.label("last_date"),
            ChatHistory.chat_time.label("last_time"),
            ChatHistory.chat_num,
            func.row_number().over(
                partition_by=ChatHistory.chat_list_num,
                order_by=(
                    ChatHistory.chat_date.desc(),
                    ChatHistory.chat_time.desc(),
                    ChatHistory.chat_num.desc(),
                ),
            ).label("rn"),
        )
        .filter(ChatHistory.owner_cognito_id == uid)
        .subquery()
    )

    rows = (
        db.query(
            subq.c.chat_list_num,
            subq.c.last_message,
            subq.c.last_date,
            subq.c.last_time,
        )
        .filter(subq.c.rn == 1)
        .order_by(
            subq.c.last_date.desc(),
            subq.c.last_time.desc(),
            subq.c.chat_list_num.desc(),  # 동시간대일 때 방번호 큰 것 먼저 보이고 싶으면 유지
        )
        .all()
    )

    return [
        ChatListItem(
            chat_list_num=r.chat_list_num,
            last_message=r.last_message,
            last_date=str(r.last_date),
            #last_time=str(r.last_time),
        )
        for r in rows
    ]

# @router.delete("")  # DELETE /chats?list_no=1&list_no=2&list_no=3
# def bulk_delete_chat_lists(
#     list_no: List[int] = Query(..., description="삭제할 채팅방 번호들. 반복 파라미터로 전달"),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     uid = current_user.cognito_id
#     targets = list(set(list_no))  # 중복 제거
#     if not targets:
#         raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제할 방번호가 없습니다.")

#     q = (
#         db.query(ChatHistory)
#           .filter(
#               ChatHistory.owner_cognito_id == uid,
#               ChatHistory.chat_list_num.in_(targets)
#           )
#     )
#     deleted = q.delete(synchronize_session=False)
#     db.commit()

#     if deleted == 0:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, detail="삭제할 메시지가 없습니다.")
#     return {"deleted_count": deleted, "chat_list_nums": targets}

class BulkDeleteBody(BaseModel):
    list_no: List[int]


@router.post("/bulk-delete")
def bulk_delete_chat_lists_post(
    body: BulkDeleteBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    여러 채팅방(list_no 배열)을 한 번에 삭제합니다.
    예시 요청:
        POST /chats/bulk-delete
        {
            "list_no": [1, 2, 3]
        }
        
    예시 요청 (단일값):
        POST /chats/bulk-delete
        {
            "list_no": [1]
        }
    """
    uid = current_user.cognito_id
    targets = list(set(body.list_no))  # 중복 제거

    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="삭제할 방번호가 없습니다.",
        )

    # 실제로 존재하는 방만 조회
    existing_lists = (
        db.query(ChatHistory.chat_list_num)
        .filter(
            ChatHistory.owner_cognito_id == uid,
            ChatHistory.chat_list_num.in_(targets),
        )
        .distinct()
        .all()
    )
    existing_nums = [r.chat_list_num for r in existing_lists]
    not_found = list(set(targets) - set(existing_nums))

    if not existing_nums:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="삭제할 메시지가 없습니다.",
        )

    # 삭제 실행
    deleted = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.owner_cognito_id == uid,
            ChatHistory.chat_list_num.in_(existing_nums),
        )
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        "deleted_count": deleted,
        "deleted_lists": sorted(existing_nums),
        "not_found": sorted(not_found),
    }