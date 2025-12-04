# src/models/background_list.py
from sqlalchemy import String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base
from sqlalchemy.dialects.mysql import SMALLINT

class BackgroundList(Base):
    __tablename__ = "background_list"
    __table_args__ = {"mysql_engine": "InnoDB"}
    background_number: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True),
        primary_key=True,
        autoincrement=True
    )
    
    background_name: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    
    background_price: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True),
        nullable=False
    )

    users = relationship(
        "User", 
        back_populates="background_list",
    )

    background_buy_list = relationship(
        "BackgroundBuyList",
        back_populates="background_list",
    )

"""
@event.listens_for(ItemList.__table__, "after_create")
def insert_default_item(target, connection, **kw):
    connection.execute(
        target.insert().values(
            item_number=1,
            item_name="nothing",
            item_price=0
        )
    )
"""