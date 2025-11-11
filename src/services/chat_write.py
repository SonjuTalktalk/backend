from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from src.models.chat_history import ChatHistory

def next_chat_num(db: Session, uid: str, list_no: int) -> int:
    last = (
        db.query(ChatHistory.chat_num)
          .filter(ChatHistory.owner_cognito_id == uid,
                  ChatHistory.chat_list_num == list_no)
          .order_by(desc(ChatHistory.chat_num))
          .with_for_update()
          .first()
    )
    return (last[0] if last else 0) + 1

# src/services/chat_write.py
def append_message_row(db: Session, uid: str, list_no: int, message: str, tts_path: str | None = None) -> ChatHistory:
    # ★ 여기서도 db.begin() 쓰지 않음
    n = next_chat_num(db, uid, list_no)

    now = datetime.now()
    row = ChatHistory(
        owner_cognito_id=uid,
        chat_list_num=list_no,
        chat_num=n,
        message=message,
        tts_path=tts_path,
        chat_date=now.date(),
        chat_time=now.time(),
    )
    db.add(row)
    db.flush()
    return row
