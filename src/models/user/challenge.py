from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableList
import enum
from src.db.database import Base


class ChallengeType(Base):
    __tablename__ = "challenges"
    
    id : Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100))
    subtitle: Mapped[str] = mapped_column(String(200))
    point: Mapped[int] = mapped_column(nullable=False, default=0)