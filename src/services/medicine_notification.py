# src/services/medicine_notificiation.py
import sys
import enum
import os
from dotenv import load_dotenv
from src.db.database import SessionLocal
from src.models.health_medicine import HealthMedicine
from src.services.fcm_push import send_push_to_user
import logging
import firebase_admin
from firebase_admin import credentials

load_dotenv()

logging.basicConfig(
    filename="/home/ec2-user/backup/medicine_notification/medicine_notification.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

key_path = "/home/ec2-user/backup/backend/firebase-key.json"
if not firebase_admin._apps:
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

class MedicineTime(str, enum.Enum):
        morning = "morning" # 오전 8시
        afternoon = "afternoon" # 오후 12시
        evening = "evening" # 오후 6시
        bedtime = "bedtime" # 오후 10시

TIME_LABEL_MAP = {
        "morning": "아침",
        "afternoon": "점심",
        "evening": "저녁",
        "bedtime": "취침",
    }

QUERY_MAP = {
            "morning": lambda db: db.query(HealthMedicine).all(),
            "afternoon": lambda db: db.query(HealthMedicine).filter(HealthMedicine.medicine_daily >= 3).all(),
            "evening": lambda db: db.query(HealthMedicine).filter(HealthMedicine.medicine_daily >= 2).all(),
            "bedtime": lambda db: db.query(HealthMedicine).filter(HealthMedicine.medicine_daily == 4).all(),
        }  

def send_medicine_notification(requested_time: MedicineTime):
    with SessionLocal() as db:
        routines = QUERY_MAP.get(requested_time.value, lambda db: [])(db)
        time_label = TIME_LABEL_MAP.get(requested_time.value, "지정 시간")

        for routine in routines:
            title = "복용 알림"
            body = f"[{time_label}] {routine.medicine_name} 약을 복용할 시간이에요"

            # data는 선택. 프론트가 딥링크/화면이동에 쓰고 싶으면 todo_num 넣어두면 편함.
            data = {
                "type": "medicine",
                "medicine_name": routine.medicine_name,
                "medicine_start_date": routine.medicine_start_date,
                "medicine_time": requested_time.value,
            }

            success, fail, deactivated = send_push_to_user(
                db = db,
                owner_cognito_id = routine.cognito_id,
                title = title,
                body = body,
                data = data,
            )
            #logging.info(f"success: {success}, fail: {fail}, deactivated: {deactivated}")
            
            if success > 0:
                logging.info(f"[target]: {routine.cognito_id}, [medicine]: {routine.medicine_name}")
        
        logging.info("알림 완료")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        logging.error("사용법: python3.11 medicine_notification.py <morning|afternoon|evening|bedtime>")
        sys.exit(1) # 인자가 없으면 바로 종료
    
    requested_time_str = sys.argv[1] 
    try:
        requested_time = MedicineTime(requested_time_str)
        send_medicine_notification(requested_time)
    except ValueError:
        logging.error(f"잘못된 복용 시간입니다: {requested_time_str}")
        sys.exit(1)
    
    
    

    

    



    
    