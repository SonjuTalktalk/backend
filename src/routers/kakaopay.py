# src/routers/kakaopay.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.users import User
from src.config.kakaopay_settings import kakaopay_settings
from src.services.kakaopay_service import (
    KakaoPayError,
    kakaopay_ready,
    kakaopay_approve_by_order_id,
    mark_canceled,
    mark_failed,
)

router = APIRouter(prefix="/pay/kakaopay", tags=["KakaoPay"])


class ReadyRequest(BaseModel):
    """
    📌 프론트 → 서버로 '결제 준비(ready)' 요청할 때 보내는 바디

    - amount: 결제 금액(원) (필수)
    - item_name: 결제창에 표시될 상품명 (선택, 기본 Premium)
    - quantity: 수량 (선택, 기본 1)
    - tax_free_amount: 비과세 금액 (선택, 기본 0)
    """
    amount: int = Field(..., ge=1, description="결제 금액(원). 예: 3900")
    item_name: str = Field(default="Premium", description="결제창에 보여줄 상품명")
    quantity: int = Field(default=1, ge=1, description="수량")
    tax_free_amount: int = Field(default=0, ge=0, description="비과세 금액")


@router.post("/ready", status_code=200)
async def ready_payment(
    body: ReadyRequest,
    # ✅ 선택: pc|mobile|app (PC 테스트 편하게)
    client: str | None = Query(default=None, description="pc|mobile|app (선택)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    ✅ [1단계] 결제 준비(Ready)  (프론트가 직접 호출하는 엔드포인트)

    📌 언제 호출하나요? (프론트 구현 포인트)
    - 사용자가 "프리미엄 결제" 버튼을 눌렀을 때

    📌 프론트 요청 형태
    - POST /pay/kakaopay/ready
    - Headers:
        Authorization: Bearer <Cognito Access Token>
        Content-Type: application/json
    - Body 예시:
        {
          "amount": 3900,
          "item_name": "Premium",
          "quantity": 1,
          "tax_free_amount": 0
        }

    - amount: 결제 금액(원) (필수)
    - item_name: 결제창에 표시될 상품명 (선택, 기본 Premium)
    - quantity: 수량 (선택, 기본 1)
    - tax_free_amount: 비과세 금액 (선택, 기본 0)
    
    📌 서버 내부 동작 방식
    1) get_current_user()가 Authorization 토큰을 검증하고,
       현재 로그인 유저를 current_user로 주입합니다.
    2) 카카오페이 ready API 호출 → tid, redirect URL들 반환
    3) DB에 order_id/tid/status=READY 저장 (approve에 필요!)

    📌 응답에서 프론트가 해야할 것
    - PC 테스트: redirect.pc를 브라우저로 열기
    - RN(안드/ios): redirect.app 우선 열기(없으면 redirect.mobile)
    """
    try:
        hint = None
        if client in ("pc", "mobile", "app"):
            hint = client  # type: ignore

        return await kakaopay_ready(
            db=db,
            user=current_user,
            amount=body.amount,
            item_name=body.item_name,
            quantity=body.quantity,
            tax_free_amount=body.tax_free_amount,
            client_hint=hint,
        )
    except KakaoPayError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/success", status_code=200)
async def payment_success(
    pg_token: str = Query(..., description="카카오페이가 붙여주는 pg_token"),
    order_id: str = Query(..., description="ready 때 서버가 생성한 주문ID"),
    db: Session = Depends(get_db),
):
    """
    ✅ [2단계] 결제 성공 리다이렉트 (Kakao → Server)

    ⚠️ 프론트가 직접 호출하는 엔드포인트가 아닙니다.
    - 카카오페이 결제 완료 후 브라우저/WebView가 자동으로 이 URL로 이동합니다.
    - 이 요청에는 Authorization 헤더가 없습니다. (그래서 인증 의존하면 401로 approve가 안 돎)

    📌 서버 내부 동작
    1) order_id로 DB에서 결제 row 찾기 (tid + user_id 확보)
    2) pg_token + tid로 카카오 approve API 호출
    3) 승인 성공 시:
       - 결제 status = APPROVED
       - users.is_premium = True

    📌 응답
    - (선택) 딥링크 설정 시: 앱으로 302 redirect
    - 딥링크 없으면: "결제 완료" HTML 페이지 표시
    """
    try:
        await kakaopay_approve_by_order_id(db=db, order_id=order_id, pg_token=pg_token)

        # ✅ 딥링크로 앱 복귀(선택)
        if kakaopay_settings.kakaopay_app_return_scheme:
            url = f"{kakaopay_settings.kakaopay_app_return_scheme}?status=approved&order_id={order_id}"
            return RedirectResponse(url=url, status_code=302)

        return HTMLResponse(
            f"""
            <html><body>
            <h3>결제 승인 완료</h3>
            <p>order_id: {order_id}</p>
            <p>이 창을 닫고 앱으로 돌아가세요.</p>
            </body></html>
            """,
            status_code=200,
        )
    except KakaoPayError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cancel", status_code=200)
def payment_cancel(
    order_id: str = Query(..., description="ready 때 서버가 생성한 주문ID"),
    db: Session = Depends(get_db),
):
    """
    ✅ 결제 취소 리다이렉트 (Kakao → Server)

    ⚠️ 프론트가 직접 호출하는 엔드포인트가 아닙니다.
    - 사용자가 결제창에서 '취소'를 누르면 카카오가 이 URL로 이동시킵니다.
    - 이 요청에도 Authorization은 없습니다.

    📌 서버 내부 동작
    - DB에서 해당 결제 status를 CANCELED로 기록

    📌 (선택) 딥링크 복귀
    - 설정되어 있으면 앱으로 302 redirect
    """
    mark_canceled(db, order_id)

    if kakaopay_settings.kakaopay_app_return_scheme:
        url = f"{kakaopay_settings.kakaopay_app_return_scheme}?status=canceled&order_id={order_id}"
        return RedirectResponse(url=url, status_code=302)

    return HTMLResponse("<html><body><h3>결제가 취소되었습니다.</h3></body></html>")


@router.get("/fail", status_code=200)
def payment_fail(
    order_id: str = Query(..., description="ready 때 서버가 생성한 주문ID"),
    db: Session = Depends(get_db),
):
    """
    ✅ 결제 실패 리다이렉트 (Kakao → Server)

    ⚠️ 프론트가 직접 호출하는 엔드포인트가 아닙니다.
    - 결제 실패/시간초과 등의 상황에서 카카오가 이 URL로 이동시킵니다.
    - 이 요청에도 Authorization은 없습니다.

    📌 서버 내부 동작
    - DB에서 해당 결제 status를 FAILED로 기록
    """
    mark_failed(db, order_id)

    if kakaopay_settings.kakaopay_app_return_scheme:
        url = f"{kakaopay_settings.kakaopay_app_return_scheme}?status=failed&order_id={order_id}"
        return RedirectResponse(url=url, status_code=302)

    return HTMLResponse("<html><body><h3>결제가 실패했습니다.</h3></body></html>")
