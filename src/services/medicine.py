# src/services/medicine.py
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List
from src.models.health_medicine import HealthMedicine
from src.models.users import User
from src.schemas.schema_medicine import (
    CreateRoutineHealthMedicine,
    ResponseRoutineMedicine
)
from datetime import date, timedelta

def update_response_by_validity(
    routine: ResponseRoutineMedicine, 
    today: date,
    registered: set()
) -> str:
    if routine.medicine_name == "":
        return "약 이름이 없습니다."

    elif routine.medicine_daily <= 0:
        return "유효한 하루 투약량이 아닙니다."
    elif routine.medicine_daily > 4:
        return "하루 투약량은 4회까지 지원합니다."

    elif routine.medicine_period <= 0:
        return "유효한 하루 투약량이 아닙니다."
    elif routine.medicine_period > 31:
        return "복용 기간은 31일까지 지원합니다."

    elif routine.medicine_start_date < today:
        return "유효하지 않은 투약 시작일입니다. 투약 시작은 오늘부터 가능합니다."
    
    else: 
        pass

    for name in registered:
        if name == routine.medicine_name:
            return "이미 등록된 복약 루틴입니다. 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다."

    return ""
    
    
    
def calculate_end_date(start_date: date, period: int) -> date:
    return start_date + timedelta(days=period - 1)

def create_medicine_routine(
    db: Session, 
    bodies: List[CreateRoutineHealthMedicine], 
    current_user: User
) -> List[ResponseRoutineMedicine]:
    response = []
    registerd_medicine = set()
    today = date.today()
    for body in bodies:
        end_date = calculate_end_date(body.medicine_start_date, body.medicine_period)

        medicine = ResponseRoutineMedicine(
            response_message = "",
            registered = False,
            medicine_name = body.medicine_name,
            medicine_daily = body.medicine_daily,
            medicine_period = body.medicine_period,
            medicine_start_date = body.medicine_start_date,
            medicine_end_date = end_date
        )
        medicine.response_message = update_response_by_validity(medicine, today, registerd_medicine)
        
        if medicine.response_message:
            response.append(medicine)
            continue
        
        routine = db.query(HealthMedicine).filter(
            and_(
                HealthMedicine.cognito_id == current_user.cognito_id,
                HealthMedicine.medicine_name == medicine.medicine_name,
                HealthMedicine.medicine_start_date == medicine.medicine_start_date
            )
        ).first()


        if routine:
            medicine.response_message = (
                "이미 등록된 복약 루틴입니다."
                " 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다."
            )

        else:
            new_routine = HealthMedicine(
                cognito_id=current_user.cognito_id,
                medicine_name=medicine.medicine_name,
                medicine_daily=medicine.medicine_daily,
                medicine_period=medicine.medicine_period,
                medicine_start_date = medicine.medicine_start_date,
                medicine_end_date = medicine.medicine_end_date
            )

            db.add(new_routine)

            medicine.response_message = "복약 루틴이 등록되었습니다."
            medicine.registered = True
            registerd_medicine.add(new_routine.medicine_name)
        response.append(medicine)
    db.commit()
    return response