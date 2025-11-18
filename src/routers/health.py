# src/routers/health.py
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from datetime import date, datetime
from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from sqlalchemy.orm import Session
from sqlalchemy import and_
from src.models.health_memo import HealthMemo
from src.models.health_medicine import HealthMedicine
from src.services.medicine import create_medicine_routine
from sonju_ai.core.health_service import HealthService
import re

router = APIRouter(prefix="/health", tags=["건강"])

class CreateHealthMemo(BaseModel):
    memo_date: date
    memo_text: str

class ResponseHealthMemo(BaseModel):
    response_message: str
    memo_date: date
    status: str

class CreateHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

class ResponseHealthMedicine(BaseModel):
    response_message: str
    medicine_name: str
    medicine_date: date

@router.post("/memos", response_model=ResponseHealthMemo)
def create_health_memo(
    body: CreateHealthMemo,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지
    1. 기존에 있는 일지를 수정한 경우: '건강 요약 일지가 수정되었습니다.'
    2. 새로운 일지를 작성한 경우: '건강 요약 일지가 등록되었습니다.'
    """
    memo = db.query(HealthMemo).filter(
        and_(
            HealthMemo.cognito_id == current_user.cognito_id,
            HealthMemo.memo_date == body.memo_date
        )
    ).first()

    analysis = HealthService()

    # 1. 기존에 작성한 메모를 수정한거라면 원래 튜플에서 memo_text만 수정
    if memo:
        memo.memo_text = body.memo_text
        memo.status = analysis.analyze_health_memo(body.memo_text)["status"]
        db.commit()
        db.refresh(memo)
        message = "건강 요약 일지가 수정되었습니다."
        memo_date = memo.memo_date
        status = memo.status
        
        
    # 2. 새로 작성한 메모라면 새 튜플 추가 
    else:
        new_memo = HealthMemo(
            cognito_id=current_user.cognito_id,
            memo_date=body.memo_date,
            memo_text=body.memo_text,
            status=analysis.analyze_health_memo(body.memo_text)["status"]
        )
        db.add(new_memo)
        db.commit()
        db.refresh(new_memo)
        message = "건강 요약 일지가 등록되었습니다."
        memo_date = new_memo.memo_date
        status = new_memo.status

    return ResponseHealthMemo(
        response_message = message,
        memo_date = memo_date,
        status = status
    )
   
@router.get("/memos")
def get_health_memo(
    requested_date: date = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    쿼리 파라미터 requested_date 필요함. \n
    ex) /health/memos?requested_date=2025-11-18
    \n
    응답
    1. 해당 날짜에 일지가 있는 경우: 일지 텍스트 반환
    2. 해당 날짜에 일지가 없는 경우: 빈 문자열('') 반환
    """
    memo = db.query(HealthMemo).filter(
        and_(
            HealthMemo.cognito_id == current_user.cognito_id,
            HealthMemo.memo_date == requested_date
        )
    ).first()
    
    return memo.memo_text if memo else ""
    
@router.post("/medicine", response_model=ResponseHealthMedicine)
def create_health_medicine(
    body: CreateHealthMedicine,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    응답 메시지
    - '복약 루틴이 등록되었습니다.'

    ---
    
    약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급하고 \n
    409 Conflict 로 처리
    """
    
    return create_medicine_routine(db, body, current_user)


@router.post("/automedicine")
async def create_health_medicine_automatically(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    클라이언트에서 이미지 파일을 서버로 전송 \n \n

    OCR을 통해 약 봉투 이미지 파일에서 필요한 내용 추출 \n

    ## 응답 \n
    { \n
    "response_message": "복약 루틴이 등록되었습니다.", \n
    "medicine_name": "약이름", \n
    "medicine_date": "2025-11-18" \n
    } \n x 인식한 약 종류 갯수 만큼 \n
    
    
    약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급하고 \n
    409 Conflict 로 처리 \n
    ---
    ## (아직 처리되지 않은 예외케이스) \n
    만약 수동으로 입력한 복약 루틴이 있고 \n
    약 봉투에 기재된 복약 루틴 중 \n
    첫 번째 약에 대한 복약 루틴만 수동 입력한 것과 겹칠 때 \n
    두 번째 이후부터 중복되지 않는 복약 루틴을 등록하지 않은 채 409 Conflict로 응답함
    """
    OCR = HealthService()
    content = await file.read()

    scanned_data = OCR.extract_prescription_info(content)
    
    data = [
    
        CreateHealthMedicine(
            medicine_name = routine["name"],
            medicine_daily = int(re.search(r"(\d+)회", routine["frequency"]).group(1)),
            medicine_period = routine["duration_days"],
            medicine_date = routine["prescription_date"]
        )

        for routine in scanned_data["medicines"]
    ]
    
    for a in data:
        print(a)
        
    return [
        create_medicine_routine(db, item, current_user)
        for item in data
    ]
