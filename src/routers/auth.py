# 인증 관련 API 엔드포인트 (회원가입)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date
from src.db.database import get_db
from src.models.user.users import User
from src.auth.token_verifier import verify_id_token

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

    db.add(new_user)                                     # 새 User 객체를 세션에 추가 준비
    db.commit()                                          # 변경사항을 데이터베이스에 커밋하여 실제로 저장
    db.refresh(new_user)                                 # 새로 생성된 사용자의 최신 상태를 가져옴

    return {
        "message": "회원가입이 완료되었습니다",
        "phone_number": new_user.phone_number,
        "name": new_user.name
    }


class LoginRequest(BaseModel):
    # 프론트에서 보내는 camelCase 키도 자동 인식하도록
    id_token: str = Field(alias="idToken")

    class Config:
        validate_by_name = True
        
@router.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    로그인 엔드포인트
    - 클라이언트에서 Cognito 로그인 후 받은 access_token을 전달
    - 서버는 access_token을 검증하고, DB 사용자 조회 후 로그인 처리
    """

    # 1) Access 토큰 검증
    access_payload = verify_id_token(request.id_token)
    if not access_payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "유효하지 않은 id_token")

    # 2) Cognito 사용자 ID(sub) 추출
    cognito_sub = access_payload.get("sub")
    if not cognito_sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "id_token에 sub 없음")

    # 3) DB에서 사용자 조회
    user = db.query(User).filter(User.cognito_id == cognito_sub).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "가입되지 않은 사용자")

    # 4) 로그인 성공 — 사용자 정보 반환
    return {
        "login": "ok",
        "user_id": user.cognito_id,
        "name": user.name,
        "phone_number": user.phone_number,
        "gender": user.gender,
        "birthdate": str(user.birthdate),
        "point": user.point,
    }
    
