# src/models/chat_history.py
from sqlalchemy import ForeignKey, String, Date, Text, Time, Integer, func, Index
from datetime import date, time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base

class ChatHistory(Base):
    __tablename__ = "chat_histories"

    # ▶ 복합 PK: 같은 유저-같은 방 안에서 chat_num 유일
    owner_cognito_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    chat_list_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_num: Mapped[int] = mapped_column(Integer, primary_key=True)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    tts_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tts_voice: Mapped[str | None] = mapped_column(String(32), nullable=True)


    chat_date: Mapped[date] = mapped_column(Date, nullable=False)
    chat_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)

    # 정렬/조회 최적화(선택)
    __table_args__ = (
        Index("idx_owner_list_num", "owner_cognito_id", "chat_list_num", "chat_num"),
        Index("idx_owner_list_date_time", "owner_cognito_id", "chat_list_num", "chat_date", "chat_time"),
    )

    user = relationship("User", back_populates="chat_histories", uselist=False)