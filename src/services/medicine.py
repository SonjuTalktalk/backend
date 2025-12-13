# src/services/medicine.py
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List
from src.models.health_medicine import HealthMedicine
from src.models.users import User
from src.schemas.schema_medicine import (
    RoutineHealthMedicine,
    ResponseRoutineMedicine
)


def create_medicine_routine(db: Session, bodies: List[RoutineHealthMedicine], current_user: User) -> ResponseRoutineMedicine:
    response = []
    for body in bodies:
        routine = db.query(HealthMedicine).filter(
            and_(
                HealthMedicine.cognito_id == current_user.cognito_id,
                HealthMedicine.medicine_name == body.medicine_name,
                HealthMedicine.medicine_date == body.medicine_date
            )
        ).first()

    
        if routine:
            response.append(
                ResponseRoutineMedicine(
                    response_message = (
                        "이미 등록된 복약 루틴입니다."
                        " 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다."
                    ),
                    registered = False,
                    medicine_name = body.medicine_name,
                    medicine_daily = body.medicine_daily,
                    medicine_period = body.medicine_period,
                    medicine_date = body.medicine_date
                )
            )
            
        else:
            new_routine = HealthMedicine(
                cognito_id=current_user.cognito_id,
                medicine_name=body.medicine_name,
                medicine_daily=body.medicine_daily,
                medicine_period=body.medicine_period,
                medicine_date=body.medicine_date,
            )

            db.add(new_routine)
            response.append(
                ResponseRoutineMedicine(
                    response_message = "복약 루틴이 등록되었습니다.",
                    registered = True,
                    medicine_name = new_routine.medicine_name,
                    medicine_daily = new_routine.medicine_daily,
                    medicine_period = new_routine.medicine_period,
                    medicine_date = new_routine.medicine_date
                )
            )
    db.commit()
    return response