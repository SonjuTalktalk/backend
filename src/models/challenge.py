# src/models/user/challenge.py
from __future__ import annotations
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
    __tablename__ = "daily_challenge_picks"

    # 복합 PK로 중복 방지 (자동 인덱스)
    date_for: Mapped[date] = mapped_column(Date, primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )

    # 편의 접근용 (pick.challenge.title)
    challenge: Mapped["Challenges"] = relationship("Challenges")
