# src/models/health_memo.py
from sqlalchemy import ForeignKey, String, Date, Text, Time, Integer, func, Index
from datetime import date, time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base

class HealthMemo(Base):
    __tablename__ = "health_memos"

    # 복합 PK: cognito_id + memo_date (일지는 하루에 한 번만 쓸 수 있음)
    cognito_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    memo_date: Mapped[date] = mapped_column(
        Date, 
        primary_key=True,
        nullable=False)
    
    memo_text: Mapped[str] = mapped_column(
        Text,
        nullable=False)

    user = relationship("User", back_populates="health_memos")
