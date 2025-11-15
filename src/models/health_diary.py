from sqlalchemy import ForeignKey, String, Date, Text, Time, Integer, func, Index
from datetime import date, time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base

class HealthDiary(Base):
    __tablename__ = "health_diaries"

    cognito_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    diary_date: Mapped[date] = mapped_column(
        Date, 
        primary_key=True,
        nullable=False)
    
    diary_text: Mapped[str] = mapped_column(
        Text,
        nullable=False)

    # 정렬/조회 최적화(선택)
    __table_args__ = (
        Index("idx_owner_diary_text", "cognito_id", "diary_date"),
    )

    user = relationship("User", back_populates="health_diaries")
