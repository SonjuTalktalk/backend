# src/models/background_buy_list.py
from sqlalchemy import String, event, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base
from sqlalchemy.dialects.mysql import SMALLINT

class BackgroundBuyList(Base):
    __tablename__ = "background_buy_list"

    # 복합 PK: cognito_id + background_number (아이템은 중복해서 구매할 수 없음)
    cognito_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    background_number: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True),
        ForeignKey("background_list.background_number", ondelete="CASCADE"),
        primary_key=True,
    )
    
    background_list = relationship(
        "BackgroundList", 
        back_populates="background_buy_list"
    )

    users = relationship(
        "User", 
        back_populates="background_buy_list"
    )

