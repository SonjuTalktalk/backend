from typing import List
from pydantic import BaseModel

class AddPurchaseInfo(BaseModel):
    background_number: int 

class ResponseAddPurchase(BaseModel):
    background_number: int
    message: str

class EquipBackground(BaseModel):
    background_number: int 

class ResponseEquipStatus(BaseModel):
    background_number: int
    message: str

class ResponseUnequip(BaseModel):
    message: str

class BoughtBackground(BaseModel):
    background_number: int
    background_name: str

class ResponseBought(BaseModel):
    result: List[BoughtBackground]