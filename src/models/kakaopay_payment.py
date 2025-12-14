# 결제 트랜잭션 테이블 (tid 저장용)
from __future__ import annotations

import datetime as dt
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base

class KakaoPayPayment(Base):
    __tablename__ = "kakaopay_payments"

    # 서버 내부 주문번호(카카오 partner_order_id로도 사용)
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    tid: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="READY")  
    # READY / APPROVED / CANCELED / FAILED

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, nullable=False)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # 디버깅/감사 로그용(원하면 지워도 됨)
    ready_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    approve_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User")
