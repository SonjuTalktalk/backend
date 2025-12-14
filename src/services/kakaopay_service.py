# src/services/kakaopay_service.py
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional, Literal

import httpx
from sqlalchemy.orm import Session

from src.config.kakaopay_settings import kakaopay_settings
from src.models.kakaopay_payment import KakaoPayPayment
from src.models.users import User


class KakaoPayError(Exception):
    pass


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"{kakaopay_settings.kakaopay_auth_scheme} {kakaopay_settings.kakaopay_secret_key}",
        "Content-Type": "application/json",
    }


def _pick_default_redirect(
    redirect: Dict[str, Optional[str]],
    client_hint: Optional[Literal["pc", "mobile", "app"]] = None,
) -> Optional[str]:
    """
    서버가 기본 redirect_url 하나를 골라주고 싶을 때 사용.
    - PC 테스트면 pc 우선
    - 모바일이면 app -> mobile 우선
    """
    if client_hint == "pc":
        return redirect.get("pc") or redirect.get("mobile") or redirect.get("app")
    if client_hint == "mobile":
        return redirect.get("mobile") or redirect.get("app") or redirect.get("pc")
    if client_hint == "app":
        return redirect.get("app") or redirect.get("mobile") or redirect.get("pc")

    # 힌트 없으면 모바일 사용자 가정(app->mobile->pc)
    return redirect.get("app") or redirect.get("mobile") or redirect.get("pc")


async def kakaopay_ready(
    *,
    db: Session,
    user: User,
    amount: int,
    item_name: str = "Premium",
    quantity: int = 1,
    tax_free_amount: int = 0,
    client_hint: Optional[Literal["pc", "mobile", "app"]] = None,
) -> Dict[str, Any]:
    if amount <= 0:
        raise KakaoPayError("amount must be positive")

    order_id = uuid.uuid4().hex  # partner_order_id
    partner_user_id = user.cognito_id

    approval_url = f"{kakaopay_settings.kakaopay_approval_url}?order_id={order_id}"
    cancel_url = f"{kakaopay_settings.kakaopay_cancel_url}?order_id={order_id}"
    fail_url = f"{kakaopay_settings.kakaopay_fail_url}?order_id={order_id}"

    payload = {
        "cid": kakaopay_settings.kakaopay_cid,
        "partner_order_id": order_id,
        "partner_user_id": partner_user_id,
        "item_name": item_name,
        "quantity": quantity,
        "total_amount": amount,
        "tax_free_amount": tax_free_amount,
        "approval_url": approval_url,
        "cancel_url": cancel_url,
        "fail_url": fail_url,
    }

    url = f"{kakaopay_settings.kakaopay_base_url}/online/v1/payment/ready"

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, headers=_auth_headers(), json=payload)

    if r.status_code >= 400:
        raise KakaoPayError(f"ready failed: {r.status_code} {r.text}")

    data = r.json()
    tid = data.get("tid")
    if not tid:
        raise KakaoPayError(f"ready response missing tid: {data}")

    redirect = {
        "app": data.get("next_redirect_app_url"),
        "mobile": data.get("next_redirect_mobile_url"),
        "pc": data.get("next_redirect_pc_url"),
    }
    if not any(redirect.values()):
        raise KakaoPayError(f"ready response missing redirect urls: {data}")

    redirect_url = _pick_default_redirect(redirect, client_hint=client_hint)
    if not redirect_url:
        raise KakaoPayError(f"ready response missing redirect_url after pick: {data}")

    # ✅ DB에 tid 저장(approve에 필요)
    row = KakaoPayPayment(
        order_id=order_id,
        user_id=user.cognito_id,  # ✅ 나중에 콜백에서 여기 값으로 user를 찾음
        tid=tid,
        amount=amount,
        status="READY",
        ready_raw=json.dumps(data, ensure_ascii=False),
    )
    db.add(row)
    db.commit()

    return {
        "order_id": order_id,
        "tid": tid,
        "redirect": redirect,
        "redirect_url": redirect_url,
    }


# ✅ 핵심: 카카오 콜백(success)에서 Authorization 없이도 승인 가능하도록
async def kakaopay_approve_by_order_id(
    *,
    db: Session,
    order_id: str,
    pg_token: str,
) -> Dict[str, Any]:
    pay: Optional[KakaoPayPayment] = (
        db.query(KakaoPayPayment)
        .filter(KakaoPayPayment.order_id == order_id)
        .first()
    )
    if not pay:
        raise KakaoPayError("payment not found (invalid order_id)")

    # 멱등 처리(redirect가 두 번 들어오거나 새로고침해도 안전)
    if pay.status == "APPROVED":
        return {"status": "already_approved", "order_id": order_id}

    # ✅ ready 때 저장해둔 user_id를 partner_user_id로 사용(ready와 approve 일치 보장)
    partner_user_id = pay.user_id

    payload = {
        "cid": kakaopay_settings.kakaopay_cid,
        "tid": pay.tid,
        "partner_order_id": order_id,
        "partner_user_id": partner_user_id,
        "pg_token": pg_token,
    }

    url = f"{kakaopay_settings.kakaopay_base_url}/online/v1/payment/approve"

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, headers=_auth_headers(), json=payload)

    if r.status_code >= 400:
        pay.status = "FAILED"
        db.commit()
        raise KakaoPayError(f"approve failed: {r.status_code} {r.text}")

    data = r.json()

    # 결제 승인 처리
    pay.status = "APPROVED"
    pay.approve_raw = json.dumps(data, ensure_ascii=False)

    # ✅ 유저 프리미엄 활성화
    user = db.query(User).filter(User.cognito_id == partner_user_id).first()
    if user:
        user.is_premium = True

    db.commit()

    return {
        "status": "approved",
        "order_id": order_id,
        "is_premium": True,
    }


# (옵션) 나중에 "앱이 직접 approve"할 수도 있으니 남겨둠
async def kakaopay_approve(
    *,
    db: Session,
    user: User,
    order_id: str,
    pg_token: str,
) -> Dict[str, Any]:
    """
    앱이 직접 approve를 호출하는 구조가 필요할 때 사용 가능.
    지금 구조(카카오 redirect 콜백)에서는 approve_by_order_id를 쓰는게 안전.
    """
    # user를 받아도, 결국 order_id 기준으로 처리하는 게 멱등/안전함
    return await kakaopay_approve_by_order_id(db=db, order_id=order_id, pg_token=pg_token)


def mark_canceled(db: Session, order_id: str) -> None:
    pay = db.query(KakaoPayPayment).filter(KakaoPayPayment.order_id == order_id).first()
    if pay and pay.status == "READY":
        pay.status = "CANCELED"
        db.commit()


def mark_failed(db: Session, order_id: str) -> None:
    pay = db.query(KakaoPayPayment).filter(KakaoPayPayment.order_id == order_id).first()
    if pay and pay.status == "READY":
        pay.status = "FAILED"
        db.commit()
