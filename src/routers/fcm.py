from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.users import User
from src.services.fcm_push import upsert_token, deactivate_token

router = APIRouter(prefix="/fcm", tags=["FCM"])


class RegisterTokenReq(BaseModel):
    token: str = Field(..., min_length=10)
    platform: str = "unknown"
    device_id: Optional[str] = None


@router.post("/token", status_code=status.HTTP_201_CREATED)
def register_fcm_token(
    body: RegisterTokenReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    FCM 토큰 등록(업서트)

    📌 언제 호출하나요? (프론트 구현 포인트)
    - 로그인 성공 직후 / 앱 실행 직후(자동 로그인 완료 직후)
    - FCM 토큰이 새로 발급되거나 갱신(onTokenRefresh) 되었을 때
    → 토큰은 디바이스/앱 재설치/환경 변화로 바뀔 수 있어서 "그때마다" 다시 등록해야 합니다.

    📌 프론트 요청 형태
    - POST /fcm/token
    - Headers:
        Authorization: Bearer <Cognito Access Token>
        Content-Type: application/json
    - Body:
        {
          "token": "<FCM_DEVICE_TOKEN>",
          "platform": "android" | "ios" | "web" | "unknown",
          "device_id": "<optional-uuid>"
        }

    📌 서버 내부 동작 방식
    1) get_current_user()가 Authorization 토큰을 검증하고,
       현재 로그인 유저를 current_user로 주입합니다.
       → 그래서 프론트는 owner_id를 따로 보내지 않습니다.
    2) upsert_token()이 DB fcm_tokens 테이블에 토큰을 저장합니다.
       - 같은 token이 이미 있으면 UPDATE (활성화/유저 매핑 갱신)
       - 없으면 INSERT
    3) db.commit()으로 저장 확정

    📌 응답
    - {"ok": true}  → 저장 성공

    ⚠️ 참고
    - 서버는 FCM 토큰을 생성할 수 없습니다. 반드시 디바이스(Firebase SDK)에서 얻어서 보내야 합니다.
    """
    upsert_token(db, current_user.cognito_id, body.token, body.platform, body.device_id)
    db.commit()
    return {"ok": True}


@router.delete("/token", status_code=status.HTTP_200_OK)
def unregister_fcm_token(
    token: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    FCM 토큰 해제(비활성화)

    📌 언제 호출하나요? (프론트 구현 포인트)
    - 로그아웃 직후 (특히 공용폰/가족폰 가능성 있으면 강력 추천)
    - 앱 내 "푸시 알림 끄기" 토글 OFF로 변경했을 때
    - (선택) 계정 전환 시에도 이전 계정 토큰을 끊고 새 계정으로 등록하면 안전합니다.

    📌 프론트 요청 형태
    - DELETE /fcm/token?token=<FCM_DEVICE_TOKEN>
    - Headers:
        Authorization: Bearer <Cognito Access Token>

    📌 서버 내부 동작 방식
    1) get_current_user()가 Authorization 토큰을 검증하고,
       현재 로그인 유저를 current_user로 주입합니다.
    2) deactivate_token()이 DB에서 "해당 유저의 해당 token"을 찾아
       is_active=False로 비활성화 합니다.
       → 보통은 기록/재등록(업서트) 대비를 위해 물리 삭제 대신 비활성화를 사용합니다.
    3) db.commit()으로 반영

    📌 응답 의미
    - {"updated": 1}  → 해당 토큰을 찾아 비활성화 성공
    - {"updated": 0}  → 해당 토큰이 없었음(이미 비활성화/잘못된 token/다른 유저 토큰 등)

    💡 왜 token을 query로 받나요?
    - 끊고 싶은 대상이 "현재 디바이스 토큰 1개"라서,
      프론트가 알고 있는 token 값을 그대로 넘기는 방식이 가장 단순하고 정확합니다.
    """
    updated = deactivate_token(db, current_user.cognito_id, token)
    db.commit()
    return {"updated": updated}
