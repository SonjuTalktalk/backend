# src/services/medicine_delete_expired.py
from dotenv import load_dotenv
from src.db.database import SessionLocal
from src.models.health_medicine import HealthMedicine
import logging
from datetime import date
load_dotenv()

logging.basicConfig(
    filename="/home/ec2-user/backup/medicine_notification/medicine_notification.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def delete_expired_medicine():
    with SessionLocal() as db:
        today = date.today()
        #today = date(2025, 12, 17) 디버깅용
        expired = db.query(HealthMedicine).filter(HealthMedicine.medicine_end_date < today).all()
        
        for routine in expired:
            logging.info(
                f"DELETE [cognito_id]: {routine.cognito_id} "
                f"[medicine_name]: {routine.medicine_name} "
                f"[medicine_start_date]: {routine.medicine_start_date}"
            )
            db.delete(routine)
        db.commit()
        logging.info("만료 루틴 삭제 완료")


if __name__ == "__main__":
    delete_expired_medicine()
    
    
    
    

    

    



    
    