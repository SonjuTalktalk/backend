import uuid
from sqlalchemy import String, Date, Enum, UniqueConstraint, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from src.db.database import Base

class Gender(str, enum.Enum):
    male = "남자"
    female = "여자"

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("cognito_id", name="uq_users_cognito_id"),
        UniqueConstraint("phone_number", name="uq_users_phone_number"),
        Index("ix_users_name", "name"),
    )

    # 내부 고유 PK: UUID 문자열(36자)
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )


    cognito_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True
    )

   
    phone_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True
    )

    # 이름/성별/생일
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )
    
    gender: Mapped[Gender] = mapped_column(
        Enum(Gender), 
        nullable=True
    )
    
    birthdate: Mapped[Date] = mapped_column(
        Date, 
        nullable=True
    )

    point: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    ai_profile = relationship(
        "AiProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,               
    )
