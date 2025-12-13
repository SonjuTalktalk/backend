from pydantic import BaseModel, model_validator
from datetime import date
from typing import List
class CreateHealthMemo(BaseModel):
    memo_date: date
    memo_text: str

class ResponseHealthMemo(BaseModel):
    response_message: str
    memo_text: str
    memo_date: date
    status: str

class RoutineHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

class CreateHealthMedicine(BaseModel):
    target: List[RoutineHealthMedicine]

class ResponseGetMedicine(BaseModel):
    result: List[RoutineHealthMedicine]

class ScannedHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

class ResponseScannedMedicine(BaseModel):
    result: List[ScannedHealthMedicine]

class ResponseRoutineMedicine(BaseModel):
    response_message: str
    registered: bool
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

class ResponseHealthMedicine(BaseModel):
    response: List[ResponseRoutineMedicine]

class DeleteHealthMedicine(BaseModel):
    medicine_name: str
    medicine_date: date

class ResponseDeleteMedicine(BaseModel):
    response_message: str
    medicine_name: str
    medicine_date: date

class ModifiedContents(BaseModel):
    update_name: str | None = None
    update_daily: int | None = None
    update_period: int | None = None
    update_date: date | None = None

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not any([self.update_name, self.update_daily, self.update_period, self.update_date]):
            raise ValueError("하나 이상의 필드가 필요합니다.")
        return self
    
class PatchHealthMedicine(BaseModel):
    current_name: str
    current_date: date
    update: ModifiedContents

class ResponsePatchMedicine(BaseModel):
    response_message: str
    old_name: str
    old_date: date
    updated: ModifiedContents