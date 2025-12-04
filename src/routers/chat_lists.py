# src/routers/chat_lists.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import List
from sqlalchemy import func
from sqlalchemy.orm import Session
from pathlib import Path


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

    - 이 API를 호출하면:
      1) 이 유저의 해당 채팅방들에 있는 모든 채팅 메시지가 DB에서 삭제되고
      2) 그 메시지들에 대해 생성돼 있던 TTS(mp3) 파일도 같이 삭제됩니다.

    ▶ 예시 요청 (여러 개)
        POST /chats/bulk-delete
        {
            "list_no": [1, 2, 3]
        }

    ▶ 예시 요청 (하나만)
        POST /chats/bulk-delete
        {
            "list_no": [1]
        }

    ▶ 응답 예시
        {
          "deleted_count": 12,           # 실제로 삭제된 메시지 개수
          "deleted_lists": [1, 2],       # 실제로 존재해서 삭제된 방 번호
          "not_found": [3]               # 요청했지만 이 유저에게는 없는 방 번호
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

    # -------------------------------
    # 🔊 1) 이 방들에 속한 메시지들의 TTS 파일 먼저 삭제
    # -------------------------------
    # - ChatHistory.tts_path에는 "/static/tts/xxx.mp3" 형태로 저장돼 있다고 가정
    # - 실제 파일은 "outputs/tts/xxx.mp3" 경로에 있음
    rows_with_tts: list[ChatHistory] = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.owner_cognito_id == uid,
            ChatHistory.chat_list_num.in_(existing_nums),
            ChatHistory.tts_path.isnot(None),
        )
        .all()
    )

    for row in rows_with_tts:
        url_path = row.tts_path  # 예: "/static/tts/tts_output_20251204_123456.mp3"
        if not url_path:
            continue

        # "/static/..."  ->  "outputs/..."
        # main.py 에서 app.mount("/static", StaticFiles(directory="outputs"), ...) 했기 때문에
        if url_path.startswith("/static"):
            disk_path = url_path.replace("/static", "outputs", 1)
        else:
            disk_path = url_path  # 혹시 다른 형식으로 저장됐다면 그대로 사용

        file_path = Path(disk_path)
        try:
            if file_path.exists():
                file_path.unlink()  # 실제 mp3 파일 삭제
        except Exception:
            # 파일 삭제 실패해도 방 삭제 자체는 계속 가는 게 일반적이라서
            # 여기서는 조용히 무시 (원하면 logger.warning 찍어도 됨)
            pass

    # -------------------------------
    # 🗑 2) DB에서 채팅 메시지 삭제
    # -------------------------------
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
