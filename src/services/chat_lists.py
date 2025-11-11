# src/services/chat_lists.py
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from src.models.chat_history import ChatHistory

def next_chat_list_num(db: Session, uid: str) -> int:
    # 삭제된 번호는 재사용하지 않고 항상 max+1
    last = (
        db.query(ChatHistory.chat_list_num)
          .filter(ChatHistory.owner_cognito_id == uid)
          .order_by(desc(ChatHistory.chat_list_num))
          .with_for_update()
          .first()
    )
    return (last[0] if last else 0) + 1
