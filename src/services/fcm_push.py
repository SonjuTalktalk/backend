
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, List
import datetime as dt

import firebase_admin
from firebase_admin import messaging
from firebase_admin.exceptions import FirebaseError
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.models.fcm_token import FcmToken


def _firebase_ready() -> bool:
    # main.py에서 initialize_app이 되었는지 체크
    return bool(getattr(firebase_admin, "_apps", None))


def _data_to_str(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not data:
        return {}
    return {k: str(v) for k, v in data.items() if v is not None}


def _is_dead_token(exc: Exception) -> bool:
    # SDK 버전/환경 차이를 방어하기 위해 문자열 기반으로도 처리
    msg = (str(exc) or "").lower()
    name = exc.__class__.__name__.lower()
    return (
        "unregistered" in name
        or "unregistered" in msg
        or "not registered" in msg
        or "registration-token-not-registered" in msg
        or "invalid registration" in msg
        or "invalid argument" in msg
    )


def upsert_token(
    db: Session,
    owner_cognito_id: str,
    token: str,
    platform: str = "unknown",
    device_id: Optional[str] = None,
) -> None:
    now = dt.datetime.now().replace(microsecond=0)

    row = db.execute(select(FcmToken).where(FcmToken.token == token)).scalars().first()
    if row:
        row.owner_cognito_id = owner_cognito_id
        row.platform = platform
        row.device_id = device_id
        row.is_active = True
        row.last_seen_at = now
    else:
        db.add(
            FcmToken(
                owner_cognito_id=owner_cognito_id,
                token=token,
                platform=platform,
                device_id=device_id,
                is_active=True,
                last_seen_at=now,
            )
        )


def deactivate_token(db: Session, owner_cognito_id: str, token: str) -> int:
    row = db.execute(
        select(FcmToken).where(
            FcmToken.owner_cognito_id == owner_cognito_id,
            FcmToken.token == token,
        )
    ).scalars().first()
    if not row:
        return 0
    row.is_active = False
    return 1


def send_push_to_user(
    db: Session,
    owner_cognito_id: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int, int]:
    """
    return (success_count, fail_count, deactivated_count)
    DB commit은 호출자가 한다.
    """
    if not _firebase_ready():
        # 개발환경에서 키 없을 수 있으니 “조용히 실패”로 처리하고 싶으면 여기서 return 0,0,0
        raise RuntimeError("Firebase Admin SDK가 초기화되지 않았습니다. (firebase-key.json / initialize_app 확인)")

    tokens = (
        db.execute(
            select(FcmToken).where(
                FcmToken.owner_cognito_id == owner_cognito_id,
                FcmToken.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )

    token_list = [t.token for t in tokens]
    if not token_list:
        return 0, 0, 0

    payload = _data_to_str(data)
    now = dt.datetime.now().replace(microsecond=0)

    # 권장: send_each_for_multicast (있으면 사용)
    if hasattr(messaging, "send_each_for_multicast"):
        msg = messaging.MulticastMessage(
            tokens=token_list,
            notification=messaging.Notification(title=title, body=body),
            data=payload,
        )
        resp = messaging.send_each_for_multicast(msg)

        deactivated = 0
        for idx, r in enumerate(resp.responses):
            if r.success:
                tokens[idx].last_sent_at = now
            else:
                exc = r.exception or Exception("unknown fcm error")
                if _is_dead_token(exc):
                    tokens[idx].is_active = False
                    deactivated += 1

        return resp.success_count, resp.failure_count, deactivated

    # fallback: 단건 send
    success = 0
    fail = 0
    deactivated = 0

    for t in tokens:
        try:
            messaging.send(
                messaging.Message(
                    token=t.token,
                    notification=messaging.Notification(title=title, body=body),
                    data=payload,
                )
            )
            success += 1
            t.last_sent_at = now
        except Exception as e:
            fail += 1
            if _is_dead_token(e):
                t.is_active = False
                deactivated += 1

    return success, fail, deactivated
