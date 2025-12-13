from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Date, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    owner_cognito_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # 네가 정한 변수명 그대로
    noti_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    noti_time: Mapped[dt.time] = mapped_column(Time(timezone=False), nullable=False)

    __table_args__ = (
        Index(
            "idx_notifications_owner_date_time",
            "owner_cognito_id",
            "noti_date",
            "noti_time",
        ),
    )

    user = relationship("User", back_populates="notifications", uselist=False)
