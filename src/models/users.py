from sqlalchemy import String, Date, UniqueConstraint, Integer
from datetime import date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
        from src.models.chat_history import ChatHistory
        from src.models.ai import AiProfile
        
class User(Base):
    
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("cognito_id", name="uq_users_cognito_id"),
        UniqueConstraint("phone_number", name="uq_users_phone_number"),
    )

    cognito_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        nullable=False,
        unique=True,
        index=True
    )

   
    phone_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True
    )

    # 이름/성별/생일
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )
    
    gender: Mapped[str] = mapped_column(
        String(10), 
        nullable=False
    )
    
    birthdate: Mapped[date] = mapped_column(
        Date, 
        nullable=False
    )

    point: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    ai_profile: Mapped["AiProfile"] = relationship(
        "AiProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,               
    )

    chat_histories: Mapped[List["ChatHistory"]] = relationship(
        "ChatHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # health_memos = relationship(
    #     "HealthMemo",
    #     back_populates="user",
    #     cascade="all, delete-orphan"
    # )