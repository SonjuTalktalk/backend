# src/models/challenge.py

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base


class Challenges(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(200), nullable=False)
    give_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DailyChallengePick(Base):
    """
    유저별 오늘의 챌린지 4개
    - slot_index 제거 버전
    - (owner_cognito_id, date_for, challenge_id) 복합 PK
    """
    __tablename__ = "daily_challenge_picks"

    owner_cognito_id: Mapped[str] = mapped_column(
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    date_for: Mapped[date] = mapped_column(Date, primary_key=True)

    # 🔥 slot_index 대신 challenge_id를 PK에 포함
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"),
        primary_key=True,
    )

    challenge: Mapped["Challenges"] = relationship("Challenges")

    owner = relationship(
        "User",
        back_populates="daily_challenges",
    )


class DailyChallengeUserState(Base):
    """
    유저별 daily 상태 (프리미엄 새로고침 횟수)
    """
    __tablename__ = "daily_challenge_user_states"

    owner_cognito_id: Mapped[str] = mapped_column(
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    date_for: Mapped[date] = mapped_column(Date, primary_key=True)
    refresh_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    owner = relationship(
        "User",
        back_populates="daily_challenge_states",
    )
