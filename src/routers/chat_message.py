# src/routers/chat_messages.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, logger, status, Query
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
from sonju_ai.core.todo_processor import TodoProcessor

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


class TodoSuggestion(BaseModel):
    task: str
    time: Optional[str] = None  # "내일 오전 10시", "오늘 저녁" 같은 자연어 그대로

class TurnResponse(BaseModel):
    ai: MessageItem
    todos: List[TodoSuggestion] = []

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
    

    # chat → todo 처리 흐름

    1. **프론트가 `/chats/messages` 로 메시지를 보냄**
    - 백엔드에서 user 메시지를 DB에 저장하고
    - 그 직후 AI가 메시지를 분석함

    2. **AI 메시지를 분석해 '할일 후보'가 있다고 판단되면**
    - *요약된 할일(task)* 과 *날짜(time, 기본값 오늘)* 을 함께 반환함

    ---

    ### 반환 형태 (총 2개의 요소):
    - ai → AI가 생성한 MessageItem
    - todos → 분석된 할일 목록 (0개 이상)

     
       - 할일이 없으면 `todos: []`  
       - 할일이 있으면 `[ { task, time }, ... ]

    ---

    ### 프론트 처리 흐름

    3. **프론트는 응답에서 `todos` 리스트를 확인하여**
        - **1개 이상이면** 사용자에게 팝업 표시  
        > “이 내용을 할일에 추가하시겠습니까?”

    4. 사용자가 **예**를 선택하면  
        - /todos POST API를 호출해 일정으로 저장함

    5. 이후 계속 채팅을 이어가면 됨.
    
    ---
    
    ## 프론트 처리 가이드

    ### 1) 이 API 응답 구조

    ```json
    {
      "ai": { ... MessageItem ... },
      "todos": [
        { "task": "병원 가기", "time": "내일 오전 10시" },
        ...
      ]
    }
    ```

    - `ai`: AI가 생성한 채팅 메시지 (항상 존재)
    - `todos`: 대화에서 추출한 "할일 후보" 목록 (0개 이상)

    ---

    ### 2) 프론트 기본 처리 순서

    1. **AI 메시지 출력**
       - 항상 `response.ai.message` 를 채팅창에 "AI 말풍선"으로 추가한다.
       - 예시: `addChatBubble({ type: "assistant", text: res.ai.message })`

    2. **todos 배열 길이 확인**
       - `const todos = res.todos || [];`
       - `todos.length === 0` 이면 → 할일 후보가 없으므로 여기서 추가 작업 없이 종료한다.

    3. **todos.length > 0 인 경우 (할일 후보 존재)**  
       - 사용자가 선택/확인할 수 있도록 팝업/모달을 띄운다.
       - 예시 (첫 번째 항목 기준):

         - `const todo = todos[0];`
         - 제목: `"할일을 추가할까요?"`
         - 내용: ``${todo.task} (${todo.time ?? "시간 미정"})``
         - 버튼: `[취소]`, `[할일에 추가]`

    4. **사용자가 "할일에 추가"를 눌렀을 때**

       - `todo.time` (예: `"내일 10시"`)를 이용해서 `due_date`, `due_time` 값을 추정한다.
       - 단순 규칙 예시:
         - `"오늘"` → 오늘 날짜
         - `"내일"` → 오늘 + 1일
         - `"모레"` → 오늘 + 2일
         - `/(\d{1,2})시/` 패턴으로 시(hour) 추출
         - `"오후"` 가 포함되어 있고 `hour < 12` 이면 `hour += 12`
       - 이렇게 계산한 값으로 date/time 입력칸의 **기본값을 채워주고**,  
         사용자가 최종 날짜/시간을 수정·확정할 수 있게 한다.

    5. **최종 확정된 값으로 `/todos` POST 호출**

       - 요청 바디 예시:

       ```json
       {
         "task": "병원 가기",
         "due_date": "YYYY-MM-DD",   // 프론트에서 파싱/선택한 날짜
         "due_time": "HH:MM"         // 선택된 시간 (없으면 null)
       }
       ```

    6. **/todos POST 성공 시**
       - `"할일이 추가되었습니다"` 같은 토스트/알림을 보여주고
       - 팝업을 닫은 뒤, 기존 채팅 흐름을 계속 이어가면 된다.

    ---

    요약:
    - 백엔드는 `todos`에 "할일 후보"만 넘겨준다.
    - 프론트는 `todos.length`를 보고 팝업 여부를 결정하고,
      `time` 문자열을 힌트로 삼아 날짜/시간을 제안한 뒤,
      사용자가 확정한 값으로 `/todos`에 최종 저장하면 된다.
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


    
    #----------------------------------------------------------------------- 비정상 접근 부분
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
            ai=MessageItem(
                chat_list_num=list_no,
                chat_num=ai_row.chat_num,
                message=ai_row.message,
                tts_path=ai_row.tts_path,
                chat_date=str(ai_row.chat_date),
                chat_time=str(ai_row.chat_time),
            ),
        )

    #--------------------------------------------------------------------------------------

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

    # 5) TodoProcessor 사용 
    
    todo_suggestions: List[TodoSuggestion] = []

    try:
        processor = TodoProcessor()  # 네가 만든 일정 추출기
        extraction_result = processor.extract_todos_from_conversation(req.message, uid)
        tasks = processor.get_tasks_list(extraction_result)

        todo_suggestions = [
            TodoSuggestion(task=t["task"], time=t.get("time"))
            for t in tasks
        ]

    except Exception as e:
        logger.exception(f"할일 추출 중 에러 발생: {e}")

    
    # 6) TurnResponse 반환 
    return TurnResponse(
        ai=MessageItem(
            chat_list_num=ai_row.chat_list_num,
            chat_num=ai_row.chat_num,
            message=ai_row.message,
            tts_path=ai_row.tts_path,
            chat_date=str(ai_row.chat_date),
            chat_time=str(ai_row.chat_time),
        ),
        todos=todo_suggestions,  # ← 프론트로 일정 후보 제공
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