from sqlalchemy import String, Enum, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableList
import enum
from src.db.database import Base


# AI 성격/스타일/감정 표현 방식 열거형
class Personality(str, enum.Enum):
    friendly = "다정한"
    active = "활발한"
    pleasant = "유쾌한"
    reliable = "듬직한"


class AiProfile(Base):
    __tablename__ = "ai_profiles"
    

    owner_cognito_id: Mapped[str] = mapped_column(
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,     
    )
    # 닉네임: 유니크 + 인덱스 (사용자에게 보이는 이름)
    nickname: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    # 선호/스타일/감정/관심사(옵션)
    personality: Mapped[Personality] = mapped_column(Enum(Personality), nullable=False, default=Personality.friendly)


    user = relationship(
        "User",
        back_populates="ai_profile",
        uselist=False,      
    )
