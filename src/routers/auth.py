# 인증 관련 API 엔드포인트 (회원가입)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date
from src.db.database import get_db
from src.models.users import User
from src.auth.token_verifier import verify_id_token

from fastapi import APIRouter, Depends, status
from src.auth.dependencies import get_current_user
from src.models.users import User

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

@router.post("/login")
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

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: User = Depends(get_current_user)):
    """
    [로그아웃 엔드포인트 안내]

    이 API의 역할

    - 이 엔드포인트는 "로그아웃 요청"을 서버에 알려주는 용도입니다.
    - 서버는 JWT(토큰)를 따로 저장하거나 세션을 관리하지 않습니다.
      → 즉, 서버 쪽에서는 "로그인 상태"를 들고 있지 않기 때문에
        이 API를 호출해도 서버가 무언가를 해제/삭제하진 않습니다.
    - 대신, 이 API를 호출할 때 넘겨진 Authorization 헤더의 토큰이
      *정상적인 유저의 유효한 토큰인지*를 한 번 검증합니다.
      → 유효하지 않은 토큰이면 401/403 에러가 나고,
        유효하면 200과 메시지만 돌려줍니다.


    - "진짜 로그아웃" 효과는 **클라이언트가 토큰을 지워야** 발생합니다.
    - 이 API는 단지 "서버 기준으로 유효한 유저가 로그아웃을 요청했다"는
      이벤트만 남기는 수준입니다. (필요하면 나중에 로그/통계용으로 사용 가능)

    프론트에서의 사용 예시 

    1) 로그아웃 버튼 클릭 시:

        - 현재 가지고 있는 idToken(또는 accessToken)을 Authorization 헤더에 넣고
          `POST /auth/logout`을 호출합니다.

          예시:
          Authorization: Bearer <idToken>

    2) 서버에서 200 OK가 오면:

        - 디바이스에 저장해 둔 모든 인증 관련 토큰을 삭제해야 합니다.
          (예: SecureStore / localStorage / AsyncStorage 등)

          - idToken 삭제
          - accessToken 삭제
          - refreshToken 삭제 (사용 중인 경우)

    3) 토큰 삭제 이후:

        - 네이게이션을 로그인/온보딩 화면으로 초기화합니다.
        - 이후부터는 Authorization 헤더에 토큰을 붙이지 않기 때문에,
          보호된 API를 호출하면 서버에서 자동으로 401(인증 없음)을 응답하게 됩니다.

    📌 요약

    - 이 API만 호출한다고 해서 자동으로 "서버에서 세션이 끊어지는 구조"가 아닙니다.
    - 이 프로젝트는 서버가 세션을 저장하지 않는 **stateless JWT 구조**이기 때문에,
      "로그아웃"은 결국 **프론트가 토큰을 버리는 순간**에 이루어집니다.
    - 이 엔드포인트는 그 전에 "토큰이 유효한 사용자가 로그아웃을 요청했다"는
      체크 및 이벤트용이라고 이해하면 됩니다.
    """

    return {"message": "로그아웃 되었습니다. 클라이언트에서 토큰을 삭제해주세요."}