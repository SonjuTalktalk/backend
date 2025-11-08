# 인증 관련 API 엔드포인트 (회원가입)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date
from src.db.database import get_db
from src.models.user.users import User
from src.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["인증"])


# 회원가입 요청 스키마
class SignUpRequest(BaseModel):
    phone_number: str = Field(...)
    cognito_id: str = Field(...)
    gender: str = Field(...)
    birthdate: date = Field(...)
    name : str = Field(...)
    point : int = Field(default=0)

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: SignUpRequest, db: Session = Depends(get_db)):
    """
    회원가입 엔드포인트
    - 앱이 Cognito에 직접 가입 후 받은 정보를 백엔드 DB에 저장
    - Cognito 인증은 이미 완료된 상태 (앱이 처리)
    
    [앱의 회원가입 흐름]
    1. 앱 → Cognito: 전화번호/비밀번호로 회원가입
    2. Cognito → 앱: cognito_id (sub) 발급
    3. 앱 → 백엔드: 이 API를 호출하여 사용자 정보 저장
    """
    
    
    # 이미 존재하는 전화번호인지 확인
    existing_user = (
        db.query(User)                                         
        .filter(User.phone_number == request.phone_number)     
        .first()                                                                            
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 전화번호입니다"
        )
    
    # 이미 존재하는 cognito_id인지 확인
    existing_cognito = db.query(User).filter(User.cognito_id == request.cognito_id).first()
    if existing_cognito:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 Cognito ID입니다"
        )
    
    # 새 사용자 생성
    new_user = User(
        phone_number=request.phone_number,
        cognito_id=request.cognito_id,
        gender=request.gender,
        birthdate=request.birthdate,
        name=request.name,
        point=request.point
        
    )
    
    db.add(new_user)                                   
    db.commit()                                         
    db.refresh(new_user)
    
    return {
        "message": "회원가입이 완료되었습니다",
        "phone_number": new_user.phone_number,
        "name": new_user.name
    }

class LoginResponse(BaseModel):
    cognito_id: str
    phone_number: str
    name: str
    gender: str 
    birthdate: date
    point: int

    class Config:
        from_attributes = True  


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(current_user: User = Depends(get_current_user)):
    
    
    """
    Cognito JWT를 Authorization 헤더로 받는다.
    - 헤더 예시: Authorization: Bearer <JWT>
    - get_current_user가 토큰 검증 후 DB(User)에서 유저를 찾아 반환한다.
    - 예외:
      * 401: 토큰 불량/만료
      * 404: 토큰은 유효하지만 로컬 DB에 유저 없음(회원가입 필요)
    """
    return current_user