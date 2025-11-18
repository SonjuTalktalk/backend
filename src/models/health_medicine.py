# src/models/health_medicine.py
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Date, SmallInteger
from datetime import date
from src.db.database import Base

class HealthMedicine(Base):
    __tablename__ = "health_medicine"

    # 복합 PK: cognito_id + medicine_name + medicine_date
    cognito_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.cognito_id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    medicine_name: Mapped[str] = mapped_column(
        String(20), 
        primary_key=True,
    )
    
    medicine_daily: Mapped[int] = mapped_column(
        SmallInteger, 
        nullable=False,
    )

    medicine_period: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False
    )

    medicine_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True
    )

    user = relationship("User", back_populates="health_medicine")
