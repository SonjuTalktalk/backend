# src/routers/health.py
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from datetime import date, timedelta

from src.auth.dependencies import get_current_user
from src.db.database import get_db
from src.models.users import User
from src.models.health_memo import HealthMemo
from src.models.health_medicine import HealthMedicine
from src.services.medicine import create_medicine_routine
from src.schemas.schema_medicine import (
    CreateHealthMemo, 
    ResponseHealthMemo, 
    CreateRoutineHealthMedicine, 
    GetRoutineHealthMedicine, 
    CreateHealthMedicine,
    ScannedHealthMedicine,
    ResponseScannedMedicine,
    ResponseHealthMedicine,
    DeleteHealthMedicine,
    ResponseDeleteMedicine,
    ModifiedContents,
    PatchHealthMedicine,
    ResponsePatchMedicine,
    ResponseGetMedicine
)

from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from sonju_ai.core.health_service import HealthService
from typing import List
import re

router = APIRouter(prefix="/health", tags=["건강"])


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
   
@router.get("/memos/date", response_model=ResponseHealthMemo)
def get_health_memo_by_date(
    requested_date: date = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    쿼리 파라미터 requested_date 필요함. \n
    
    ex) /health/memos/date?requested_date=2025-11-18 \n
    **응답**
    1. 해당 날짜에 일지가 있는 경우: 일지 텍스트 반환
    2. 해당 날짜에 일지가 없는 경우: 빈 문자열('') 반환
    """
    
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

    return response

@router.get("/memos/month", response_model=List[ResponseHealthMemo])
def get_health_memo_by_month(
    requested_month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    쿼리 파라미터 requested_month 필요함. \n
    
    ex) /health/memos?requested_month=2025-11 \n
    **응답** \n
    해당 월에 작성한 모든 일지를 반환
    \n
    
    """

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
    "medicine_start_date": "2025-12-01" \n
    "medicine_end_date": "2025-12-03" \n
    } \n
    
    ### 2. 등록 실패 \n
    { \n
    "response_message": "이미 등록된 복약 루틴입니다. 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다.", \n
    "registered": false, \n
    "medicine_name": "약이름", \n
    "medicine_daily": "3(하루 세 번)", \n
    "medicine_period": "3(3일치)", \n
    "medicine_start_date": "2025-12-01" \n
    "medicine_end_date": "2025-12-03" \n
    } \n
    """
    
    response = create_medicine_routine(db, body.target, current_user)
    return ResponseHealthMedicine(response = response)

@router.get("/medicine", response_model=ResponseGetMedicine)
def get_health_medicine(
    requested_date: date = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    쿼리 파라미터 requested_date 필요함. \n
    ex) /health/medicine?requested_date=2025-12-13 \n
    **응답** \n
    해당 날짜에 수행해야 하는 복약 루틴을 반환 \n
    \n
    """
    response = []
    
    candidates = db.query(HealthMedicine).filter(
        HealthMedicine.cognito_id == current_user.cognito_id,  
    ).all()

    for routine in candidates:
        if (
            routine.medicine_start_date 
            <= requested_date 
            <= routine.medicine_end_date
        ):
            response.append(
                GetRoutineHealthMedicine(
                    medicine_name = routine.medicine_name,
                    medicine_daily = routine.medicine_daily,
                    medicine_period = routine.medicine_period,
                    medicine_start_date = routine.medicine_start_date,
                    medicine_end_date = routine.medicine_end_date
                )
            )
    return ResponseGetMedicine(result = response)

@router.post("/automedicine", response_model=ResponseScannedMedicine)
async def scan_health_medicine(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    클라이언트에서 이미지 파일을 서버로 전송 \n \n

    OCR을 통해 약 봉투 이미지 파일에서 필요한 내용 추출 \n
    ---
    ## 응답 \n
    ### ex) \n
    { \n
    "result": [ \n
    { \n
    "medicine_name": "알부테롤", \n
    "medicine_daily": 3, \n
    "medicine_period": 6, \n
    "medicine_start_date": "2020-02-07" \n
    }, \n
    { \n
    "medicine_name": "슈가메트", \n
    "medicine_daily": 3, \n
    "medicine_period": 6, \n
    "medicine_start_date": "2020-02-07" \n
    }, \n
     \n
    ... \n
     \n
    { \n
    "medicine_name": "소론도정", \n
    "medicine_daily": 3, \n
    "medicine_period": 6, \n
    "medicine_start_date": "2020-02-07" \n
    } \n
    ] \n
    } \n

    """
    OCR = HealthService()
    content = await file.read()

    scanned_data = OCR.extract_prescription_info(content)
    
    result = [
        ScannedHealthMedicine(
            medicine_name = routine["name"],
            medicine_daily = int(re.search(r"(\d+)회", routine["frequency"]).group(1)),
            medicine_period = routine["duration_days"],
            medicine_start_date = routine["prescription_date"]
        )
        for routine in scanned_data["medicines"]
    ]
    for a in result:
        print(a)

    return ResponseScannedMedicine(result = result)

@router.delete("/medicine", response_model=ResponseDeleteMedicine)
def delete_health_medicine(
    body: DeleteHealthMedicine,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ## 응답 \n
    { \n
    "response_message": "복약 루틴이 삭제되었습니다.", \n
    "medicine_name": "약이름", \n
    "medicine_start_date": "2025-12-01" \n
    } \n
    """

    routine = db.query(HealthMedicine).filter(
        and_(
            HealthMedicine.cognito_id == current_user.cognito_id,
            HealthMedicine.medicine_name == body.medicine_name,
            HealthMedicine.medicine_start_date == body.medicine_start_date
        )
    ).first()

    if not routine:
        raise HTTPException(
            status_code=404, 
            detail="등록되지 않은 복약 루틴입니다."
        )

    db.delete(routine)
    db.commit()

    return ResponseDeleteMedicine(
            response_message = "복약 루틴이 삭제되었습니다.",
            medicine_name = routine.medicine_name,
            medicine_start_date = routine.medicine_start_date
        )

@router.patch("/medicine", response_model=ResponsePatchMedicine)
def patch_health_medicine(
    body: PatchHealthMedicine,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ## 요청 \n
    수정하고자 하는 복약 루틴의 정보와 (medicine_name과 medicine_start_date) \n
    수정하고자 하는 정보를 update의 값 객체의 키 값으로 넣어서 보내기. \n
    수정할 정보만 넣어주면 됨. 예를 들어 약 이름만 바꿀거면 "update" 에서 "update_name"만 부여 \n
    최소 하나의 필드는 주어져야 함. 변경사항 유무를 클라이언트에서 체크 후에 변경한 필드가 있을 때에만 \n
    형식에 맞춰서 엔드포인트에 요청 보내주세요. \n

    ### ex) A라는 약 이름을 B로 변경 \n
    { \n
    "medicine_name": "A", \n
    "medicine_start_date": "2025-12-13", \n
    "update": { \n
    "update_name": "B", \n
    } \n
    } \n

    ---

    ## 응답 \n
    ### ex) \n
    ### 2025년 12월 13일부터 약 C 복용을 시작하는 루틴을 \n
    ### 2025년 12월 20일부터 약 D를 하루에 2번씩 3일 복용하는 루틴으로 \n
    ### 수정에 성공했을 때
    {
    "response_message": "복약 루틴이 수정되었습니다.", \n
    "old_name": "C", \n
    "old_date": "2025-12-13", \n
    "updated": { \n
    "update_name": "D", \n
    "update_daily": 2, \n
    "update_period": 3, \n
    "update_date": "2025-12-20" \n
    } \n
    } \n
    """

    
    routine = db.query(HealthMedicine).filter(
        and_(
            HealthMedicine.cognito_id == current_user.cognito_id,
            HealthMedicine.medicine_name == body.medicine_name,
            HealthMedicine.medicine_start_date == body.medicine_start_date
        )
    ).first()

    

    if not routine:
        raise HTTPException(
            status_code=404, 
            detail="등록되지 않은 복약 루틴입니다."
        )
    
    old_routine = HealthMedicine(
        cognito_id=routine.cognito_id,
        medicine_name=routine.medicine_name,
        medicine_daily=routine.medicine_daily,
        medicine_period=routine.medicine_period,
        medicine_start_date = routine.medicine_start_date,
        medicine_end_date = routine.medicine_end_date
    )

    update_fields = {
        "update_name": "medicine_name",
        "update_daily": "medicine_daily",
        "update_period": "medicine_period",
        "update_date": "medicine_start_date",
    }

    for update_key, model_field in update_fields.items():
        value = getattr(body.update, update_key)
        if value is not None:
            setattr(routine, model_field, value)
            
    routine.medicine_end_date = routine.medicine_start_date + timedelta(days=routine.medicine_period - 1)

    if (
        old_routine.medicine_name == routine.medicine_name and
        old_routine.medicine_daily == routine.medicine_daily and
        old_routine.medicine_period == routine.medicine_period and
        old_routine.medicine_start_date == routine.medicine_start_date
    ):
        return ResponsePatchMedicine(
            response_message = "수정할 사항이 없습니다.",
            old_name = body.medicine_name,
            old_date = body.medicine_start_date,
            updated = body.update
        )

    try:
        db.commit()
        db.refresh(routine)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, 
            detail="이미 등록된 복약 루틴입니다. 약 이름과 투약 시작일이 동일한 경우 같은 루틴으로 취급합니다."
        )
    
    return ResponsePatchMedicine(
        response_message = "복약 루틴이 수정되었습니다.",
        old_name = body.medicine_name,
        old_date = body.medicine_start_date,
        updated = body.update
    )