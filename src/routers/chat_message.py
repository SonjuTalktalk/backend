# src/routers/chat_messages.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.user.users import User
from src.models.list.chat_history import ChatHistory
from src.services.chat_lists import next_chat_list_num
from sonju_ai.core.chat_service import ChatService
from src.models.user.ai import AiProfile, Personality


router = APIRouter(prefix="/chats", tags=["채팅-메시지"])

# -----------------------
# 공용 스키마
# -----------------------
class CreateMessageReq(BaseModel):
    message: str
    chat_list_num: Optional[int] = None      # 비우면 새 방 자동
    enable_tts: bool = False                 # AI 응답 TTS 생성 여부

class MessageItem(BaseModel):
    chat_list_num: int
    chat_num: int
    message: str
    tts_path: Optional[str]
    chat_date: str
    chat_time: str

class TurnResponse(BaseModel):
    user: MessageItem
    ai: MessageItem


# 사용자별 개인화 설정 로딩
def get_personalized_chat_service(user: User, db) -> ChatService:
    """
    유저의 AI 프로필(AiProfile) 기반으로 ChatService 인스턴스를 생성한다.
    - nickname → ChatService.ai_name
    - personality → ChatService.model_type
    없으면 기본값("손주", "friendly")
    """
    profile = db.query(AiProfile).filter(AiProfile.owner_cognito_id == user.cognito_id).first()
    if not profile:
        ai_name = "손주"
        model_type = "friendly"
    else:
        ai_name = profile.nickname or "손주"
        model_type = profile.personality.name if profile.personality else "friendly"

    return ChatService(ai_name=ai_name, model_type=model_type)

# 합쳐진 메시지+AI 생성
@router.post("/messages", response_model=TurnResponse)
def append_message_with_ai(
    req: CreateMessageReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    흐름:
    A) 마지막 chat_num이 홀수(=직전 user만 있고 AI 미생성)면:
       - 그 직전 user 메시지에 대한 AI만 생성/저장(백필)하고 즉시 반환
       - 현재 req.message는 처리하지 않음 (중복 방지, UX: 클라가 다시 전송)

    B) 마지막 chat_num이 짝수면(정상 상태):
       - 이번 요청의 user 메시지 저장 → history 구성 → AI 생성/저장 → 두 레코드 반환
    """
    uid = current_user.cognito_id
    list_no = req.chat_list_num or next_chat_list_num(db, uid)

    # =========================
    # 1) 마지막 번호 잠금 조회
    # =========================
    with db.begin():
        last = (
            db.query(ChatHistory.chat_num)
              .filter(
                  ChatHistory.owner_cognito_id == uid,
                  ChatHistory.chat_list_num == list_no
              )
              .order_by(desc(ChatHistory.chat_num))
              .with_for_update()
              .first()
        )
        last_num = last[0] if last else 0

        # ====================================================
        # A) 백필 루트: 마지막이 홀수면 직전 user에 대한 AI만 생성/저장
        # ====================================================
        if last_num % 2 == 1:
            # 1) 마지막 홀수 user 메시지 조회(잠금)
            dangling_user = (
                db.query(ChatHistory)
                  .filter(
                      ChatHistory.owner_cognito_id == uid,
                      ChatHistory.chat_list_num == list_no,
                      ChatHistory.chat_num == last_num
                  )
                  .with_for_update()
                  .one()
            )

            # 2) 해당 시점까지의 history 구성(마지막 홀수 포함)
            prev_rows = (
                db.query(ChatHistory)
                  .filter(
                      ChatHistory.owner_cognito_id == uid,
                      ChatHistory.chat_list_num == list_no
                  )
                  .order_by(ChatHistory.chat_num.asc())
                  .all()
            )
            history = [
                {"role": ("user" if r.chat_num % 2 == 1 else "assistant"), "content": r.message}
                for r in prev_rows
            ]

            # 3) 개인화된 ChatService로 백필용 AI 생성
            chat_service = get_personalized_chat_service(current_user, db)
            ai_result = chat_service.chat(
                user_id=uid,
                message=dangling_user.message,   # 직전 사용자 발화에 대한 응답 생성
                history=history,
                enable_tts=req.enable_tts,
            )
            ai_text = ai_result["response"]
            ai_tts  = ai_result.get("tts_path")

            # 4) AI 레코드 삽입(짝수 번호로 채움)
            now_ai = datetime.now()
            ai_row = ChatHistory(
                owner_cognito_id=uid,
                chat_list_num=list_no,
                chat_num=last_num + 1,
                message=ai_text,
                tts_path=ai_tts,
                chat_date=now_ai.date(),
                chat_time=now_ai.time(),
            )
            db.add(ai_row)
            # with db.begin() 블록 종료 시 커밋

    # ===== 트랜잭션 종료 후: 백필 즉시 반환 =====
    if last_num % 2 == 1:
        db.refresh(dangling_user)
        db.refresh(ai_row)
        return TurnResponse(
            user=MessageItem(
                chat_list_num=list_no,
                chat_num=dangling_user.chat_num,
                message=dangling_user.message,
                tts_path=dangling_user.tts_path,
                chat_date=str(dangling_user.chat_date),
                chat_time=str(dangling_user.chat_time),
            ),
            ai=MessageItem(
                chat_list_num=list_no,
                chat_num=ai_row.chat_num,
                message=ai_row.message,
                tts_path=ai_row.tts_path,
                chat_date=str(ai_row.chat_date),
                chat_time=str(ai_row.chat_time),
            ),
        )

    # ====================================================
    # B) 정상 루트: 새 사용자 발화 + 새 AI 발화 생성/저장
    # ====================================================
    with db.begin():
        user_num = last_num + 1          # 홀수
        ai_num   = user_num + 1          # 짝수

        # 1) 사용자 메시지 insert
        now1 = datetime.now()
        user_row = ChatHistory(
            owner_cognito_id=uid,
            chat_list_num=list_no,
            chat_num=user_num,
            message=req.message,
            tts_path=None,
            chat_date=now1.date(),
            chat_time=now1.time(),
        )
        db.add(user_row)
        db.flush()  # user_row.chat_num 등 채워짐

        # 2) 이 방 전체 이력(history) 구성
        prev_rows = (
            db.query(ChatHistory)
              .filter(
                  ChatHistory.owner_cognito_id == uid,
                  ChatHistory.chat_list_num == list_no
              )
              .order_by(ChatHistory.chat_num.asc())
              .all()
        )
        history = [
            {"role": ("user" if r.chat_num % 2 == 1 else "assistant"), "content": r.message}
            for r in prev_rows
        ]

        # 3) ChatService로 AI 호출(개인화 적용)
        chat_service = get_personalized_chat_service(current_user, db)
        ai_result = chat_service.chat(
            user_id=uid,
            message=req.message,
            history=history,
            enable_tts=req.enable_tts,
        )
        ai_text = ai_result["response"]
        ai_tts  = ai_result.get("tts_path")

        # 4) AI 메시지 insert
        now2 = datetime.now()
        ai_row = ChatHistory(
            owner_cognito_id=uid,
            chat_list_num=list_no,
            chat_num=ai_num,
            message=ai_text,
            tts_path=ai_tts,
            chat_date=now2.date(),
            chat_time=now2.time(),
        )
        db.add(ai_row)
        # with db.begin() 블록 종료 시 커밋

    # ===== 커밋 이후 최신화 & 응답 =====
    db.refresh(user_row)
    db.refresh(ai_row)
    return TurnResponse(
        user=MessageItem(
            chat_list_num=list_no,
            chat_num=user_row.chat_num,
            message=user_row.message,
            tts_path=user_row.tts_path,
            chat_date=str(user_row.chat_date),
            chat_time=str(user_row.chat_time),
        ),
        ai=MessageItem(
            chat_list_num=list_no,
            chat_num=ai_row.chat_num,
            message=ai_row.message,
            tts_path=ai_row.tts_path,
            chat_date=str(ai_row.chat_date),
            chat_time=str(ai_row.chat_time),
        ),
    )
    
    
# 다중 삭제
@router.delete("")  # DELETE /chats?list_no=1&list_no=2&list_no=3
def bulk_delete_chat_lists(
    list_no: List[int] = Query(..., description="삭제할 채팅방 번호들. 반복 파라미터로 전달"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    targets = list(set(list_no))
    if not targets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "삭제할 방번호가 없습니다.")

    q = (
        db.query(ChatHistory)
          .filter(
              ChatHistory.owner_cognito_id == uid,
              ChatHistory.chat_list_num.in_(targets)
          )
    )
    deleted = q.delete(synchronize_session=False)
    db.commit()

    if deleted == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="삭제할 메시지가 없습니다.")
    return {"deleted_count": deleted, "chat_list_nums": targets}
