from typing import List
from pydantic import BaseModel
class AddPurchaseInfo(BaseModel):
    item_number: int 

class ResponseAddPurchase(BaseModel):
    item_number: int
    message: str

class EquipItem(BaseModel):
    item_number: int 

class ResponseEquipStatus(BaseModel):
    item_number: int
    message: str

class ResponseUnequip(BaseModel):
    message: str

class BoughtItem(BaseModel):
    item_number: int
    item_name: str

class ResponseBought(BaseModel):
    result: List[BoughtItem]