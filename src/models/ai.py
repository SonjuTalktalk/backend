from sqlalchemy import String, Enum as SqlEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from src.db.database import Base
from sqlalchemy.dialects.mysql import SMALLINT

# AI 성격/스타일/감정 표현 방식 열거형
class Personality(str, enum.Enum):
    friendly = "friendly"
    active = "active"
    pleasant = "pleasant"
    reliable = "reliable"


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
    personality: Mapped[Personality] = mapped_column(
        SqlEnum(Personality, name="personality"),
        nullable=False,
        default=Personality.friendly,
    )

    equipped_item: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True),
        ForeignKey("item_list.item_number"),
        nullable=True
    )

    user = relationship(
        "User",
        back_populates="ai_profile",    
        uselist=False,      
    )

    item_list = relationship(
        "ItemList",
        back_populates="ai",
    )
    