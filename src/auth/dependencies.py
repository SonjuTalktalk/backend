# dependencies.py
from fastapi import Depends, HTTPException, Request, status, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.models.user.users import User  
from src.auth.token_verifier import verify_cognito_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request, 
    db: Session = Depends(get_db),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme)
    
):
    
    
    # 1) Bearer 토큰이 Security로 들어왔는지 확인
    if bearer and bearer.scheme.lower() == "bearer":
        access_token = bearer.credentials
    else:
        # Security(auto_error=False) 여서 안 들어왔을 수 있으므로 기존 헤더로도 체크
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "인증 헤더 없음")
        access_token = auth.replace("Bearer ", "", 1).strip()

    access_payload = verify_cognito_access_token(access_token)
    if access_payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "유효하지 않은 access_token")

    cognito_sub = access_payload.get("sub")
    if not cognito_sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access_token에 sub 없음")


    # 2) DB 조회 (항상 수행)
    user = db.query(User).filter(User.cognito_id == cognito_sub).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "가입되지 않은 사용자")

    # 3) 모든 보호 엔드포인트에 User 주입
    return user
