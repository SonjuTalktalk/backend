from pydantic import BaseModel, model_validator, Field, field_validator
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

class CreateRoutineHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_start_date: date

class GetRoutineHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_start_date: date
    medicine_end_date: date

class CreateHealthMedicine(BaseModel):
    target: List[CreateRoutineHealthMedicine]

class ResponseGetMedicine(BaseModel):
    result: List[GetRoutineHealthMedicine]

class ScannedHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_start_date: date

class ResponseScannedMedicine(BaseModel):
    result: List[ScannedHealthMedicine]

class ResponseRoutineMedicine(BaseModel):
    response_message: str
    registered: bool
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_start_date: date
    medicine_end_date: date

class ResponseHealthMedicine(BaseModel):
    response: List[ResponseRoutineMedicine]

class DeleteHealthMedicine(BaseModel):
    medicine_name: str
    medicine_start_date: date

class ResponseDeleteMedicine(BaseModel):
    response_message: str
    medicine_name: str
    medicine_start_date: date

class ModifiedContents(BaseModel):
    update_name: str | None = Field(default=None, min_length=1)
    update_daily: int | None = Field(default=None, ge=1, le=4)
    update_period: int | None = Field(default=None, ge=1, le=31)
    update_date: date | None = None

    @field_validator("update_date")
    @classmethod
    def update_date_not_past(cls, v):
        if v is None:
            return v
        if v < date.today():
            raise ValueError("투약 시작일은 오늘부터 가능합니다.")
        return v
    
    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not any([self.update_name, self.update_daily, self.update_period, self.update_date]):
            raise ValueError("하나 이상의 필드가 필요합니다.")
        return self
    
class PatchHealthMedicine(BaseModel):
    medicine_name: str = Field(min_length=1)
    medicine_start_date: date
    update: ModifiedContents

    @field_validator("medicine_start_date")
    @classmethod
    def update_date_not_past(cls, v):
        if v is None:
            return v
        if v < date.today():
            raise ValueError("투약 시작일은 오늘부터 가능합니다.")
        return v
    
class ResponsePatchMedicine(BaseModel):
    response_message: str
    old_name: str
    old_date: date
    updated: ModifiedContents