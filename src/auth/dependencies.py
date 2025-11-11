# src/auth/dependencies.py
from __future__ import annotations

from datetime import date
import os
import zlib
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.models.users import User
from src.auth.token_verifier import verify_cognito_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
):
  
    # Authorization: Bearer <token> 우선, 없으면 Security(auto_error=False) 결과 확인
    if bearer and getattr(bearer, "scheme", "").lower() == "bearer":
        access_token = bearer.credentials
    else:
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

    user = db.query(User).filter(User.cognito_id == cognito_sub).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "가입되지 않은 사용자")

    return user
