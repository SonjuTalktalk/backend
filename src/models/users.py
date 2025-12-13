# src/models/users.py
from __future__ import annotations

from datetime import date
from typing import List, TYPE_CHECKING

from sqlalchemy import String, Date, UniqueConstraint, Integer, Boolean, ForeignKey, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import SMALLINT

from src.db.database import Base
import enum
if TYPE_CHECKING:
    from src.models.chat_history import ChatHistory
    from src.models.ai import AiProfile

class FontSize(str, enum.Enum):
    small = "small"
    medium = "medium"
    large = "large"

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
        index=True,
    )

    phone_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    gender: Mapped[str] = mapped_column(String(10), nullable=False)

    birthdate: Mapped[date] = mapped_column(Date, nullable=False)

    point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ✅ 배경 장착 저장 (background.py에서 사용 중)
    equipped_background: Mapped[int | None] = mapped_column(
        SMALLINT(unsigned=True),
        ForeignKey("background_list.background_number", ondelete="SET NULL"),
        nullable=True,
        default=None,
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
        passive_deletes=True,
    )

    font_size: Mapped[FontSize] = mapped_column(
        SqlEnum(FontSize, name="font_size"),
        nullable=False,
        default=FontSize.medium,
    )

    todo_lists = relationship(
        "ToDoList",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    health_memos = relationship(
        "HealthMemo",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    health_medicine = relationship(
        "HealthMedicine",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    daily_challenges = relationship(
        "DailyChallengePick",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ✅ 여기 cascade 없으면 삭제할 때 꼬일 수 있음(너가 봤던 AssertionError 계열)
    daily_challenge_states = relationship(
        "DailyChallengeUserState",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    item_buy_list = relationship(
        "ItemBuyList",
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ✅ BackgroundBuyList.users(back_populates="background_buy_list")를 만족시켜야 함
    background_buy_list = relationship(
        "BackgroundBuyList",
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ✅ Notification.user(back_populates="notifications")를 만족시켜야 함
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
