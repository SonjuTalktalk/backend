# src/routers/chat_messages.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.users import User
from src.models.chat_history import ChatHistory
from src.services.chat_lists import next_chat_list_num
from sonju_ai.core.chat_service import ChatService
from src.models.ai import AiProfile


router = APIRouter(prefix="/chats", tags=["채팅-메시지"])


# 공용 스키마

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
    
class MessageItem_List(BaseModel):
    chat_list_num: int
    chat_num: int
    message: str
    

class TurnResponse(BaseModel):
    #user: MessageItem
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
       - 현재 req.message는 처리하지 않음

    B) 마지막 chat_num이 짝수면(정상):
       - 이번 요청의 user 메시지 저장 → history 구성 → AI 생성/저장 → 두 레코드 반환
    """
    uid = current_user.cognito_id
    list_no = req.chat_list_num or next_chat_list_num(db, uid)

    # 1) 마지막 번호 조회(+잠금). 세션은 autocommit=False라 이미 암묵 트랜잭션 상태
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

    
    # 백필 루트: 마지막이 홀수면 AI만 생성
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

        # 2) 이력(history) 구성
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

        # 3) 개인화된 ChatService로 AI 생성
        chat_service = get_personalized_chat_service(current_user, db)
        ai_result = chat_service.chat(
            user_id=uid,
            message=dangling_user.message,
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
        db.commit()          
        db.refresh(dangling_user)
        db.refresh(ai_row)

        return TurnResponse(
            # user=MessageItem(
            #     chat_list_num=list_no,
            #     chat_num=dangling_user.chat_num,
            #     message=dangling_user.message,
            #     tts_path=dangling_user.tts_path,
            #     chat_date=str(dangling_user.chat_date),
            #     chat_time=str(dangling_user.chat_time),
            # ),
            ai=MessageItem(
                chat_list_num=list_no,
                chat_num=ai_row.chat_num,
                message=ai_row.message,
                tts_path=ai_row.tts_path,
                chat_date=str(ai_row.chat_date),
                chat_time=str(ai_row.chat_time),
            ),
        )


    # 정상 루트: 새 user + 새 AI 저장
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
    db.flush()  # user_row PK/필드 확보

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

    # 3) ChatService 호출(개인화 적용)
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

    db.commit()              
    db.refresh(user_row)
    db.refresh(ai_row)

    return TurnResponse(
        # user=MessageItem(
        #     chat_list_num=list_no,
        #     chat_num=user_row.chat_num,
        #     message=user_row.message,
        #     tts_path=user_row.tts_path,
        #     chat_date=str(user_row.chat_date),
        #     chat_time=str(user_row.chat_time),
        # ),
        ai=MessageItem(
            chat_list_num=list_no,
            chat_num=ai_row.chat_num,
            message=ai_row.message,
            tts_path=ai_row.tts_path,
            chat_date=str(ai_row.chat_date),
            chat_time=str(ai_row.chat_time),
        ),
    )

@router.get("/messages/{list_no}", response_model=List[MessageItem_List])
def get_messages_of_room(
    list_no: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    특정 방 번호의 '모든 대화' 반환
    정렬: chat_date ASC → chat_time ASC → chat_num ASC (오래된 → 최신)
    """
    uid = current_user.cognito_id

    rows = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.owner_cognito_id == uid,
            ChatHistory.chat_list_num == list_no,
        )
        .order_by(
            ChatHistory.chat_date.asc(),
            ChatHistory.chat_time.asc(),
            ChatHistory.chat_num.asc(),
        )
        .all()
    )

    return [
        MessageItem_List(
            chat_list_num=r.chat_list_num,
            chat_num=r.chat_num,
            message=r.message,
            #tts_path=r.tts_path,
            #chat_date=str(r.chat_date),
            #chat_time=str(r.chat_time),
        )
        for r in rows
    ]