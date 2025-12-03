# src/routers/chat_messages.py

from datetime import datetime, date as date_t, time as time_t, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, logger, status, Query
from pydantic import BaseModel
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.users import User
from src.models.chat_history import ChatHistory
from src.services.chat_lists import next_chat_list_num
from src.services.todos import create_todo_compact
from src.models.todo_list import ToDoList
from sonju_ai.core.chat_service import ChatService
from src.models.ai import AiProfile

router = APIRouter(prefix="/chats", tags=["채팅-메시지"])

KST = ZoneInfo("Asia/Seoul")


# --------------------- 공용 스키마 ---------------------


class CreateMessageReq(BaseModel):
    message: str
    chat_list_num: Optional[int] = None  # 비우면 새 방 자동
    enable_tts: bool = False  # AI 응답 TTS 생성 여부


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


class TodoMeta(BaseModel):
    """
    이번 턴에서의 '할일 관련 상태' 메타 정보.

    - has_todo=True & step="saved" 이면,
      서버에서 이미 todo_lists 에 할일을 생성해 둔 상태.
    - todo_num 이 None 이 아니면, 방금 생성된 할일의 번호.
    """
    has_todo: bool
    step: str  # "none" | "suggest" | "ask_confirm" | "ask_date" | "saved" | "cancelled"
    task: Optional[str] = None
    date: Optional[str] = None  # 자연어 날짜 (예: "내일")
    time: Optional[str] = None  # 자연어 시간 (예: "오전 10시")
    todo_num: Optional[int] = None  # 서버에서 생성한 todo_lists.todo_num


class TurnResponse(BaseModel):
    ai: MessageItem
    todo: TodoMeta


# --------------------- ChatService 생성 ---------------------


def get_personalized_chat_service(user: User, db: Session) -> ChatService:
    """
    유저의 AI 프로필(AiProfile) 기반으로 ChatService 인스턴스를 생성
    - nickname → ChatService.ai_name
    - personality → ChatService.model_type
    없으면 기본값("손주", "friendly")
    """
    profile = (
        db.query(AiProfile)
        .filter(AiProfile.owner_cognito_id == user.cognito_id)
        .first()
    )
    if not profile:
        ai_name = "손주"
        model_type = "friendly"
    else:
        ai_name = profile.nickname or "손주"
        model_type = profile.personality.name if profile.personality else "friendly"

    return ChatService(ai_name=ai_name, model_type=model_type)


# --------------------- 날짜/시간 파싱 & Todo 생성 헬퍼 ---------------------


def _parse_korean_natural_datetime(
    date_text: Optional[str],
    time_text: Optional[str],
) -> tuple[date_t, Optional[time_t]]:
    """
    TodoProcessor 가 넘겨준 한국어 날짜/시간(자연어)을
    실제 date / time 객체로 변환한다.

    - date_text: "오늘", "내일", "모레", "11월 25일", "2025-11-25" 등
    - time_text: "오전 10시", "오후 3시", "15:30" 등 (없을 수 있음)
    """
    from datetime import datetime as dt
    import re

    now = dt.now(KST)
    today = now.date()

    s_date = (date_text or "").strip()
    s_time = (time_text or "").strip()

    # ---- 날짜 ----
    target_date = today

    if s_date:
        # 1) 상대 표현
        if s_date.startswith("오늘"):
            target_date = today
        elif s_date.startswith("내일"):
            target_date = today + timedelta(days=1)
        elif s_date.startswith("모레"):
            target_date = today + timedelta(days=2)
        else:
            # 2) yyyy-mm-dd
            m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s_date)
            if m:
                y, mth, d = map(int, m.groups())
                target_date = date_t(y, mth, d)
            else:
                # 3) "11월 25일", "11/25", "11-25"
                m2 = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", s_date)
                if not m2:
                    m2 = re.search(r"(\d{1,2})[/-](\d{1,2})", s_date)
                if m2:
                    mth, d = map(int, m2.groups())
                    target_date = date_t(today.year, mth, d)

    # ---- 시간 ----
    # time_text 가 없어도 date_text 안에 시간이 섞여 있을 수 있으므로 둘 다 살펴본다.
    t_source = s_time or s_date

    if not t_source:
        return target_date, None

    # 1) HH:MM
    m = re.search(r"(\d{1,2}):(\d{2})", t_source)
    if m:
        h, mn = map(int, m.groups())
        return target_date, time_t(hour=h, minute=mn)

    # 2) "오전/오후/저녁/밤 HH시" 형태
    ampm = None
    if any(x in t_source for x in ["오전", "아침", "새벽"]):
        ampm = "am"
    elif any(x in t_source for x in ["오후", "저녁", "밤"]):
        ampm = "pm"

    m2 = re.search(r"(\d{1,2})\s*시", t_source)
    if m2:
        h = int(m2.group(1))
        if ampm == "am":
            if h == 12:
                h = 0
        elif ampm == "pm":
            if h < 12:
                h += 12
        return target_date, time_t(hour=h, minute=0)

    # 시간 파싱 실패 → 날짜만 설정
    return target_date, None


def _maybe_create_todo_from_ai(
    db: Session,
    owner_id: str,
    ai_result: Dict,
) -> Optional[ToDoList]:
    """
    ChatService.chat() 의 반환값을 보고,
    이번 턴에 확정된 할일(step == "saved")이 있으면
    todo_lists 에 바로 insert 한다.

    - create_todo_compact 안에서 commit 이 수행된다.
    - 실패해도 채팅 기록은 이미 commit 되어 있기 때문에
      대화 흐름에는 영향을 주지 않는다.
    """
    if not (ai_result.get("has_todo") and ai_result.get("step") == "saved"):
        return None

    task = ai_result.get("task")
    nat_date = ai_result.get("date")
    nat_time = ai_result.get("time")

    if not task or not nat_date:
        # date 가 없는 saved 는 원래 나오지 않지만, 방어적으로 한 번 더 체크
        return None

    due_date, due_time = _parse_korean_natural_datetime(nat_date, nat_time)
    row = create_todo_compact(db, owner_id, task, due_date, due_time)
    return row


# --------------------- 채팅 생성 (유저+AI) ---------------------


@router.post("/messages", response_model=TurnResponse)
def append_message_with_ai(
    req: CreateMessageReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    1) 유저 메시지를 DB에 저장
    2) ChatService.chat() 호출 → AI 응답 + 할일 메타 정보 획득
    3) AI 응답을 DB에 저장
    4) 할일이 확정된 경우(todo step == "saved") 서버에서 todo_lists 에 바로 insert
    5) 프론트에는 (ai 메시지 + todo 메타) 반환

    프론트 사용 가이드 (요약):
      - 항상 res.ai.message 를 채팅창 "AI 말풍선"으로 추가
      - res.todo.step / res.todo.todo_num 에 따라:
        - "suggest":
            같은 말풍선 안에서 들여쓰기 등으로
            "할일로 등록할까요?" 부분을 살짝 강조
        - "ask_confirm": 예/아니요 재질문
        - "ask_date": 날짜/시간 재질문
        - "saved" & has_todo=True:
            → 서버에서 이미 할일이 생성되어 있음
            → res.todo.todo_num 을 사용해 "방금 추가된 할일" 표시 가능
        - "cancelled" / "none":
            → 별도 처리 없이 다음 대화 진행
    """
    uid = current_user.cognito_id
    list_no = req.chat_list_num or next_chat_list_num(db, uid)

    # 1) 마지막 chat_num 조회(+잠금)
    last = (
        db.query(ChatHistory.chat_num)
        .filter(
            ChatHistory.owner_cognito_id == uid,
            ChatHistory.chat_list_num == list_no,
        )
        .order_by(desc(ChatHistory.chat_num))
        .with_for_update()
        .first()
    )
    last_num = last[0] if last else 0

    # ---------------- 백필 루트: 마지막이 홀수면 AI만 생성 ----------------
    if last_num % 2 == 1:
        # 마지막 홀수 user 메시지 조회
        dangling_user = (
            db.query(ChatHistory)
            .filter(
                ChatHistory.owner_cognito_id == uid,
                ChatHistory.chat_list_num == list_no,
                ChatHistory.chat_num == last_num,
            )
            .with_for_update()
            .one()
        )

        # 이력(history) 구성
        prev_rows = (
            db.query(ChatHistory)
            .filter(
                ChatHistory.owner_cognito_id == uid,
                ChatHistory.chat_list_num == list_no,
            )
            .order_by(ChatHistory.chat_num.asc())
            .all()
        )
        history = [
            {
                "role": ("user" if r.chat_num % 2 == 1 else "assistant"),
                "content": r.message,
            }
            for r in prev_rows
        ]

        chat_service = get_personalized_chat_service(current_user, db)
        ai_result = chat_service.chat(
            user_id=uid,
            message=dangling_user.message,
            history=history,
            enable_tts=req.enable_tts,
            chat_list_num=list_no,  # ✅ 방 번호까지 TodoProcessor 로 넘김
        )
        ai_text = ai_result["response"]
        ai_tts = ai_result.get("tts_path")

        # AI 레코드 삽입 (짝수 번호로 채움)
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
        db.refresh(ai_row)

        # ✅ 채팅 기록이 저장된 후, 이번 턴에서 확정된 할일이 있으면 서버에서 바로 Todo 생성
        created_todo = _maybe_create_todo_from_ai(db, uid, ai_result)

        todo_meta = TodoMeta(
            has_todo=ai_result.get("has_todo", False),
            step=ai_result.get("step", "none"),
            task=ai_result.get("task"),
            date=ai_result.get("date"),
            time=ai_result.get("time"),
            todo_num=(created_todo.todo_num if created_todo else None),
        )

        return TurnResponse(
            ai=MessageItem(
                chat_list_num=list_no,
                chat_num=ai_row.chat_num,
                message=ai_row.message,
                tts_path=ai_row.tts_path,
                chat_date=str(ai_row.chat_date),
                chat_time=str(ai_row.chat_time),
            ),
            todo=todo_meta,
        )

    # ---------------- 정상 루트: 새 user + 새 AI ----------------
    user_num = last_num + 1  # 홀수
    ai_num = user_num + 1  # 짝수

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
            ChatHistory.chat_list_num == list_no,
        )
        .order_by(ChatHistory.chat_num.asc())
        .all()
    )
    history = [
        {
            "role": ("user" if r.chat_num % 2 == 1 else "assistant"),
            "content": r.message,
        }
        for r in prev_rows
    ]

    # 3) ChatService 호출 (메인 답변 + 할일 대화)
    chat_service = get_personalized_chat_service(current_user, db)
    ai_result = chat_service.chat(
        user_id=uid,
        message=req.message,
        history=history,
        enable_tts=req.enable_tts,
        chat_list_num=list_no,  # ✅ 방 번호까지 TodoProcessor 로 넘김
    )
    ai_text = ai_result["response"]
    ai_tts = ai_result.get("tts_path")

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

    # ✅ 채팅 기록이 저장된 후, 이번 턴에서 확정된 할일이 있으면 서버에서 바로 Todo 생성
    created_todo = _maybe_create_todo_from_ai(db, uid, ai_result)

    # 5) Todo 메타 구성
    todo_meta = TodoMeta(
        has_todo=ai_result.get("has_todo", False),
        step=ai_result.get("step", "none"),
        task=ai_result.get("task"),
        date=ai_result.get("date"),
        time=ai_result.get("time"),
        todo_num=(created_todo.todo_num if created_todo else None),
    )

    return TurnResponse(
        ai=MessageItem(
            chat_list_num=ai_row.chat_list_num,
            chat_num=ai_row.chat_num,
            message=ai_row.message,
            tts_path=ai_row.tts_path,
            chat_date=str(ai_row.chat_date),
            chat_time=str(ai_row.chat_time),
        ),
        todo=todo_meta,
    )


# --------------------- 특정 방의 전체 메시지 조회 ---------------------


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
        )
        for r in rows
    ]
