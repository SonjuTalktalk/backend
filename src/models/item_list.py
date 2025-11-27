# src/models/item_list.py
from sqlalchemy import String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.database import Base
from sqlalchemy.dialects.mysql import SMALLINT

class ItemList(Base):
    __tablename__ = "item_list"
    __table_args__ = {"mysql_engine": "InnoDB"} # item_number는 0부터 1씩 증가함
    item_number: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True),
        primary_key=True,
        autoincrement=True
    )
    
    item_name: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    
    item_price: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True),
        nullable=False
    )

    ai = relationship(
        "AiProfile", 
        back_populates="item_list",
    )

    item_buy_list = relationship(
        "ItemBuyList",
        back_populates="item_list",
    )

    
@event.listens_for(ItemList.__table__, "after_create")
def insert_default_item(target, connection, **kw):
    connection.execute(
        target.insert().values(
            item_number=1,
            item_name="nothing",
            item_price=0
        )
    )
