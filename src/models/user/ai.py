from sqlalchemy import String, Enum, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableList
import enum
from src.db.database import Base


# AI 성격/스타일/감정 표현 방식 열거형
class Personality(str, enum.Enum):
    friendly = "다정한"
    professional = "전문적인"
    humorous = "유머러스한"

class SpeechStyle(str, enum.Enum):
    honorific = "존댓말"
    cute = "귀여운"
    soft = "부드러운"


class AiProfile(Base):
    __tablename__ = "ai_profiles"
    __table_args__ = (
        Index("ix_ai_profiles_owner", "owner_id"),
    )

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
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
    speech_style: Mapped[SpeechStyle] = mapped_column(Enum(SpeechStyle), nullable=False, default=SpeechStyle.honorific)


    user = relationship(
        "User",
        back_populates="ai_profile",
        uselist=False,      
    )
