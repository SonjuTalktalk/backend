# src/models/todo_list.py
from __future__ import annotations
from datetime import date, time
from typing import Optional

from sqlalchemy import ForeignKey, String, Date, Text, Time as SqlTime, Integer, Boolean, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.users import User 
from src.db.database import Base


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

    __table_args__ = (
        Index("idx_owner_due", "owner_cognito_id", "due_date"),
        Index("idx_owner_completed", "owner_cognito_id", "is_completed"),
    )

    # 자식(투두) → 부모(유저)
    user: Mapped["User"] = relationship("User", back_populates="todo_lists", uselist=False)