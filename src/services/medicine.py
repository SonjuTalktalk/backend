# src/services/medicine.py
from sqlalchemy.orm import Session
from src.models.health_medicine import HealthMedicine
from fastapi import HTTPException
from datetime import date
from src.auth.dependencies import get_current_user
from src.models.users import User
from pydantic import BaseModel
from sqlalchemy import and_

class CreateHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

class ResponseHealthMedicine(BaseModel):
    response_message: str
    medicine_name: str
    medicine_date: date

def create_medicine_routine(db: Session, body: CreateHealthMedicine, current_user: User) -> ResponseHealthMedicine:

    routine = db.query(HealthMedicine).filter(
        and_(
            HealthMedicine.cognito_id == current_user.cognito_id,
            HealthMedicine.medicine_name == body.medicine_name,
            HealthMedicine.medicine_date == body.medicine_date
        )
    ).first()

    
    if routine:
        raise HTTPException(
            status_code=409, 
            detail=(
                "이미 등록된 복약 루틴입니다."
                "약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다."
            )
        )

    new_routine = HealthMedicine(
        cognito_id=current_user.cognito_id,
        medicine_name=body.medicine_name,
        medicine_daily=body.medicine_daily,
        medicine_period=body.medicine_period,
        medicine_date=body.medicine_date,
    )
    db.add(new_routine)
    db.commit()
    db.refresh(new_routine)

    return ResponseHealthMedicine(
        response_message = "복약 루틴이 등록되었습니다.",
        medicine_name = new_routine.medicine_name,
        medicine_date = new_routine.medicine_date
    )