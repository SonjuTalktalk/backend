from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.models.todo_list import ToDoList
from src.services.fcm_push import send_push_to_user

KST = timezone(timedelta(hours=9))


def process_due_todo_reminders(db: Session, minutes_before: int = 30) -> int:
    """
    매 1분마다 실행된다고 가정하고,
    '지금으로부터 minutes_before분 뒤'가 due_time인 투두를 찾아 푸시 발송.
    중복 방지: reminder_sent_at이 NULL인 것만 대상으로 하고,
              발송 성공하면 reminder_sent_at을 찍는다.
    """
    now = datetime.now(KST).replace(microsecond=0)
    target = now + timedelta(minutes=minutes_before)

    # 1분 단위 윈도우
    window_start = target.replace(second=0, microsecond=0)
    window_end = window_start + timedelta(minutes=1)

    # DB는 due_date(date), due_time(time)라서:
    # target의 날짜/시간에 매칭되는 투두만 조회
    stmt = (
        select(ToDoList)
        .where(
            and_(
                ToDoList.is_completed.is_(False),
                ToDoList.reminder_sent_at.is_(None),
                ToDoList.due_time.is_not(None),
                ToDoList.due_date == window_start.date(),
                ToDoList.due_time >= window_start.time(),
                ToDoList.due_time < window_end.time(),
            )
        )
    )

    rows = db.execute(stmt).scalars().all()
    sent_count = 0

    for todo in rows:
        title = "할 일 알림"
        body = f"{todo.task}가 {minutes_before}분 남았습니다"

        # data는 선택. 프론트가 딥링크/화면이동에 쓰고 싶으면 todo_num 넣어두면 편함.
        data = {
            "type": "todo",
            "todo_num": todo.todo_num,
            "due_date": str(todo.due_date),
        }

        try:
            success, fail, deactivated = send_push_to_user(
                db=db,
                owner_cognito_id=todo.owner_cognito_id,
                title=title,
                body=body,
                data=data,
            )

            # ✅ “한 번이라도 성공”하면 발송 처리(중복방지)
            if success > 0:
                todo.reminder_sent_at = now
                sent_count += 1

            db.commit()

        except Exception:
            db.rollback()
            # 여기서 로그만 찍고 계속 진행 (다른 투두는 처리되게)
            continue

    return sent_count
