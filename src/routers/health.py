# src/routers/health.py
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from datetime import date, datetime, timedelta
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
    memo_text: str
    memo_date: date
    status: str

class CreateHealthMedicine(BaseModel):
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

class ResponseHealthMedicine(BaseModel):
    response_message: str
    registered: bool
    medicine_name: str
    medicine_daily: int
    medicine_period: int
    medicine_date: date

MAX_TEXT_BYTES = 65533

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

    if len(body.memo_text.encode('utf-8')) > MAX_TEXT_BYTES:
        raise HTTPException(
            status_code=400, 
            detail="일지가 너무 깁니다."
        )
    
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

        response = ResponseHealthMemo(
            response_message = "건강 요약 일지가 수정되었습니다.",
            memo_text = memo.memo_text,
            memo_date = memo.memo_date,
            status = memo.status
        )
        
        
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

        response = ResponseHealthMemo(
            response_message = "건강 요약 일지가 등록되었습니다.",
            memo_text = new_memo.memo_text,
            memo_date = new_memo.memo_date,
            status = new_memo.status
        )
        
    return response
   
@router.get("/memos")
def get_health_memo(
    requested_date: date | None = Query(None),
    requested_month: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    쿼리 파라미터 requested_date나 requested_month 필요함. \n
    둘 다 들어올 수는 없음 (400 Bad Request로 처리) \n

    ## 1. requested_date
    ex) /health/memos?requested_date=2025-11-18 \n
    **응답**
    1. 해당 날짜에 일지가 있는 경우: 일지 텍스트 반환
    2. 해당 날짜에 일지가 없는 경우: 빈 문자열('') 반환

    ## 2. requested_month
    ex) /health/memos?requested_month=2025-11 \n
    **응답** \n
    해당 월에 작성한 모든 일지를 반환
    \n
    
    """

    if requested_date and requested_month:
        raise HTTPException(
            status_code=400, 
            detail="requested_date와 requested_month 중 하나만 파리미터로 받을 수 있습니다."
        )

    if not requested_date and not requested_month:
        raise HTTPException(
            status_code=400, 
            detail="쿼리 파라미터가 없습니다."
        )

    if requested_date:
        memo = db.query(HealthMemo).filter(
            and_(
                HealthMemo.cognito_id == current_user.cognito_id,
                HealthMemo.memo_date == requested_date
            )
        ).first()
        response = ResponseHealthMemo(
            response_message = f"{requested_date}에 작성한 건강 일지입니다." if memo else "해당 날짜에 작성한 건강 일지가 없습니다.",
            memo_text = memo.memo_text if memo else "",
            memo_date = requested_date,
            status = memo.status if memo else ""
        )

    else:
        year, month = map(int, requested_month.split("-"))
        start_date = date(year, month, 1)
        end_date = date(year, month, 28) + timedelta(days=4)
        end_date = end_date.replace(day=1)

        memos = db.query(HealthMemo).filter(
            and_(
                HealthMemo.cognito_id == current_user.cognito_id,
                HealthMemo.memo_date >= start_date,
                HealthMemo.memo_date < end_date
            )
        ).all()

        response = [
            ResponseHealthMemo(
                response_message = f"{memo.memo_date}에 작성한 건강 일지입니다.",
                memo_text = memo.memo_text,
                memo_date = memo.memo_date,
                status = memo.status
            )
            for memo in memos
        ]

    return response
    
@router.post("/medicine", response_model=ResponseHealthMedicine)
def create_health_medicine(
    body: CreateHealthMedicine,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ## 응답 \n
    ### 1. 등록 성공 \n
    { \n
    "response_message": "복약 루틴이 등록되었습니다.", \n
    "registered": true, \n
    "medicine_name": "약이름", \n
    "medicine_daily": "3(하루 세 번)", \n
    "medicine_period": "3(3일치)", \n
    "medicine_date": "2025-12-01" \n
    } \n
    
    ### 2. 등록 실패 \n
    { \n
    "response_message": "이미 등록된 복약 루틴입니다. 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다.", \n
    "registered": false, \n
    "medicine_name": "약이름", \n
    "medicine_daily": "3(하루 세 번)", \n
    "medicine_period": "3(3일치)", \n
    "medicine_date": "2025-12-01" \n
    } \n
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
    ---
    ## 응답 \n
    ### 1. 등록 성공 \n
    { \n
    "response_message": "복약 루틴이 등록되었습니다.", \n
    "registered": true, \n
    "medicine_name": "약이름", \n
    "medicine_daily": "3(하루 세 번)", \n
    "medicine_period": "3(3일치)", \n
    "medicine_date": "2025-12-01" \n
    } \n
    
    ### 2. 등록 실패 \n
    { \n
    "response_message": "이미 등록된 복약 루틴입니다. 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다.", \n
    "registered": false, \n
    "medicine_name": "약이름", \n
    "medicine_daily": "3(하루 세 번)", \n
    "medicine_period": "3(3일치)", \n
    "medicine_date": "2025-12-01" \n
    } \n

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
