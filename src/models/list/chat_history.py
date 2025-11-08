import enum
from sqlalchemy import DateTime, ForeignKey, String, Date, Text, UniqueConstraint, Integer, func
from datetime import date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.user.ai import Personality
from routers import ai_profile
from src.db.database import Base

class Sender(str, enum.Enum):
    user = "user"
    ai = "ai"   

class ChatHistory(Base):
    __tablename__ = "chat_histories"
    __table_args__ = (
        UniqueConstraint("id", name="uq_chat_histories_id"),
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
    
    sender: Mapped[Sender] = mapped_column(
        enum.Enum(Sender),
        nullable=False
    )


    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    model: Mapped[ai_profile.Personality] = mapped_column(
        enum.Enum(ai_profile.Personality), 
        nullable=False, 
        default=ai_profile.Personality.friendly
    )

    tts_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    timestamp: Mapped[str] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False
    )
    user = relationship(
        "User",
        back_populates="chat_histories",
        uselist=False,      
    )