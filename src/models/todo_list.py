# src/models/todo_list.py
from __future__ import annotations

import datetime as dt
from datetime import date, time
from typing import Optional

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time as SqlTime, text,)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base
from src.models.users import User


class ToDoList(Base):
    __tablename__ = "todo_lists"

    # 복합 PK: 같은 유저 안에서 todo_num 유일
    owner_cognito_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    todo_num: Mapped[int] = mapped_column(Integer, primary_key=True)  # autoincrement X

    task: Mapped[str] = mapped_column(Text, nullable=False)

    # MySQL/SQLite 기준 서버 기본값 0 (PostgreSQL이면 text("false") 권장)
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )

    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_time: Mapped[Optional[time]] = mapped_column(SqlTime(timezone=False), nullable=True)

    # ✅ 30분 전 푸시 중복 발송 방지용: "발송 성공 시각"
    reminder_sent_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_owner_due", "owner_cognito_id", "due_date"),
        Index("idx_owner_completed", "owner_cognito_id", "is_completed"),
        Index("idx_todo_reminder_scan", "due_date", "due_time", "is_completed", "reminder_sent_at"),
    )

    # 자식(투두) → 부모(유저)
    # ⚠️ 순환 import 방지를 위해 "User"는 문자열로만 참조 (users.py를 직접 import 안 함)
    user: Mapped["User"] = relationship("User", back_populates="todo_lists", uselist=False)
