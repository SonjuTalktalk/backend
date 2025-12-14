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
    kakaopay_approve,
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
    # ✅ 선택: PC/모바일 어떤 URL을 기본으로 줄지 지정할 수도 있음
    # 프론트가 안 보내면 서버는 기본값(app->mobile->pc)로 골라줌
    client: str | None = Query(default=None, description="pc|mobile|app (선택)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    ✅ [1단계] 결제 준비(Ready)

    📌 언제 호출하나요? (프론트 구현 포인트)
    - 사용자가 "프리미엄 결제" 버튼을 눌렀을 때

    📌 프론트 요청 형태
    - POST /pay/kakaopay/ready
    - Headers:
        Authorization: Bearer <Cognito Access Token>
        Content-Type: application/json
    - Body (예시):
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
    2) 서버가 카카오페이 'ready' API를 호출합니다.
       - 카카오페이가 'tid'와 'redirect URL(결제창 URL)'을 반환합니다.
    3) 서버는 DB에 결제 트랜잭션(order_id, tid, amount, status=READY)을 저장합니다.
       - order_id: 서버가 생성한 주문 ID (partner_order_id)
       - tid: 카카오페이 트랜잭션 ID (approve에 필요!)
    4) 프론트에게 결제창 URL을 반환합니다.

    📌 응답 의미 (프론트가 제일 중요)
    - redirect.pc: PC 브라우저에서 열 URL
    - redirect.mobile: 모바일 웹 결제 URL
    - redirect.app: 카카오페이 앱으로 넘기는 URL
    - redirect_url: 서버가 기본으로 골라준 URL (호환용)

    ✅ 프론트에서 뭘 열어야 하나요?
    - PC 테스트: redirect.pc 열기
    - RN(안드/ios): redirect.app 우선(없으면 mobile)
    """
    try:
        hint = None
        if client in ("pc", "mobile", "app"):
            hint = client  # type: ignore

        data = await kakaopay_ready(
            db=db,
            user=current_user,
            amount=body.amount,
            item_name=body.item_name,
            quantity=body.quantity,
            tax_free_amount=body.tax_free_amount,
            client_hint=hint,
        )
        return data

    except KakaoPayError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/success", status_code=200)
async def payment_success(
    pg_token: str = Query(..., description="카카오페이가 붙여주는 토큰(성공 시)"),
    order_id: str = Query(..., description="ready 때 서버가 만든 주문ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    ✅ [2단계] 결제 성공 리다이렉트 (Kakao → Server)

    ⚠️ 프론트가 직접 호출하는 엔드포인트가 아닙니다.
    - 카카오페이가 결제 성공 후, 자동으로 이 URL로 이동시킵니다.
    - URL 형태:
      GET /pay/kakaopay/success?pg_token=...&order_id=...

    📌 서버 내부 동작 방식
    1) pg_token + order_id를 받습니다.
    2) DB에서 order_id로 결제 트랜잭션을 찾고 tid를 얻습니다.
    3) 카카오페이 approve API를 호출해 결제를 최종 승인합니다.
    4) 승인 성공 시:
       - kakaopay_payments.status = APPROVED
       - users.is_premium = True   
    5) (선택) 딥링크가 설정되어 있으면 앱으로 302 redirect 시킵니다.
       - 예: sonjutoktok://pay/result?status=approved&order_id=...

    📌 프론트 입장에서는 뭐 하면 되나요?
    - 보통은 앱에서 결제 후, 서버가 딥링크로 앱을 열어주게 하면 편함.
    - 딥링크 안 쓰면: 웹뷰 화면에 "결제 완료" HTML이 남아있게 됨.
    """
    try:
        result = await kakaopay_approve(
            db=db,
            user=current_user,
            order_id=order_id,
            pg_token=pg_token,
        )

        # ✅ 딥링크로 앱 복귀 옵션
        if kakaopay_settings.kakaopay_app_return_scheme:
            url = f"{kakaopay_settings.kakaopay_app_return_scheme}?status=approved&order_id={order_id}"
            return RedirectResponse(url=url, status_code=302)

        # 딥링크 없으면 브라우저에 간단 페이지 표시
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
    order_id: str = Query(..., description="ready 때 서버가 만든 주문ID"),
    db: Session = Depends(get_db),
):
    """
    ✅ 결제 취소 리다이렉트 (Kakao → Server)

    ⚠️ 프론트가 직접 호출하는 엔드포인트가 아닙니다.
    - 사용자가 결제창에서 '취소'를 누르면 카카오가 이 URL로 이동시킵니다.

    📌 서버 내부 동작
    - DB에서 해당 결제의 status를 CANCELED로 기록합니다.
    - (필요하면) 프론트는 이후 /me 같은 API로 premium 여부를 확인하면 됨.
    """
    mark_canceled(db, order_id)
    return HTMLResponse("<html><body><h3>결제가 취소되었습니다.</h3></body></html>")


@router.get("/fail", status_code=200)
def payment_fail(
    order_id: str = Query(..., description="ready 때 서버가 만든 주문ID"),
    db: Session = Depends(get_db),
):
    """
    ✅ 결제 실패 리다이렉트 (Kakao → Server)

    ⚠️ 프론트가 직접 호출하는 엔드포인트가 아닙니다.
    - 결제 실패/시간초과 등 상황에서 카카오가 이 URL로 이동시킵니다.

    📌 서버 내부 동작
    - DB에서 해당 결제의 status를 FAILED로 기록합니다.
    """
    mark_failed(db, order_id)
    return HTMLResponse("<html><body><h3>결제가 실패했습니다.</h3></body></html>")
