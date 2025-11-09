import enum
from sqlalchemy import DateTime, ForeignKey, String, Date, Text, UniqueConstraint, Integer
from datetime import date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.user.ai import Personality
from routers import ai_profile
from src.db.database import Base

class HealthMemo(Base):
    __tablename__ = "health_memos"
    __table_args__ = (
        UniqueConstraint("id", name="uq_health_memos_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        unique=True,
        index=True
    )

    owner_cognito_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    memo_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    
    memo_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    
    
    user = relationship(
        "User",
        back_populates="health_memos",
    )