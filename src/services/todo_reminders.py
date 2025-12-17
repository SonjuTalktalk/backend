# src/services/todo_reminders.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from src.models.todo_list import ToDoList
from src.services.fcm_push import send_push_to_user  # (success, fail, deactivated) 리턴하는 함수

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def _mask_uid(uid: str) -> str:
    if not uid:
        return ""
    if len(uid) <= 10:
        return uid[:3] + "..."
    return uid[:6] + "..." + uid[-4:]


def process_due_todo_reminders(db: Session, minutes_before: int = 30) -> int:
    """
    매 1분마다 실행된다고 가정하고,
    '지금으로부터 minutes_before분 뒤'가 due_time인 투두를 찾아 푸시 발송.

    ✅ 중복 방지:
      - ToDoList.reminder_sent_at IS NULL 인 것만 대상
      - 발송 성공(success>0)이면 reminder_sent_at = now 로 마킹

    ✅ 디버그 로그:
      - now/target/window, 후보 개수, 각 투두 발송 결과를 출력
    """
    now = datetime.now(KST).replace(microsecond=0)
    target = now + timedelta(minutes=minutes_before)

    # 1분 단위 윈도우 (target이 14:12:34면 window_start=14:12:00 ~ 14:13:00)
    window_start = target.replace(second=0, microsecond=0)
    window_end = window_start + timedelta(minutes=1)

    # ✅ 디버그 로그: 이번 턴 기준 정보
    logger.info(
        "[todo_reminders] now=%s target(now+%dm)=%s window=[%s, %s)",
        now, minutes_before, target, window_start, window_end
    )

    base_conditions = [
        ToDoList.is_completed.is_(False),
        ToDoList.reminder_sent_at.is_(None),
        ToDoList.due_time.is_not(None),
    ]

    # ✅ 자정 넘어가는 1분 윈도우 케이스 방어
    # 예: window_start=23:59, window_end=00:00(next day) → time 비교만 하면 누락될 수 있음
    if window_end.date() == window_start.date():
        time_condition = and_(
            ToDoList.due_date == window_start.date(),
            ToDoList.due_time >= window_start.time(),
            ToDoList.due_time < window_end.time(),
        )
    else:
        # 자정 넘김: (start 날짜의 start.time 이상) OR (end 날짜의 end.time 미만)
        time_condition = or_(
            and_(
                ToDoList.due_date == window_start.date(),
                ToDoList.due_time >= window_start.time(),
            ),
            and_(
                ToDoList.due_date == window_end.date(),
                ToDoList.due_time < window_end.time(),
            ),
        )

    stmt = select(ToDoList).where(and_(*base_conditions, time_condition))

    rows = db.execute(stmt).scalars().all()

    # ✅ 디버그 로그: 후보 개수
    logger.info("[todo_reminders] candidates=%d", len(rows))

    sent_count = 0

    for todo in rows:
        # 투두 하나당 어떤 걸 보내는지 로그
        logger.info(
            "[todo_reminders] try_send todo_num=%s task=%s due=%s %s owner=%s",
            todo.todo_num,
            todo.task,
            todo.due_date,
            todo.due_time,
            _mask_uid(todo.owner_cognito_id),
        )

        title = "할 일 알림"
        body = f"{todo.task}가 {minutes_before}분 남았습니다"
        data = {
            "type": "todo",
            "todo_num": todo.todo_num,
            "due_date": str(todo.due_date),
            "due_time": str(todo.due_time) if todo.due_time else "",
        }

        try:
            success, fail, deactivated = send_push_to_user(
                db=db,
                owner_cognito_id=todo.owner_cognito_id,
                title=title,
                body=body,
                data=data,
            )

            logger.info(
                "[todo_reminders] result todo_num=%s success=%d fail=%d deactivated=%d",
                todo.todo_num, success, fail, deactivated
            )

            # ✅ 한 번이라도 성공하면 “이 투두는 알림 보냈다” 마킹
            if success > 0:
                todo.reminder_sent_at = now
                sent_count += 1
                logger.info(
                    "[todo_reminders] marked reminder_sent_at todo_num=%s at %s",
                    todo.todo_num, now
                )
            else:
                # 토큰이 없거나 전부 실패면 reminder_sent_at은 안 찍힘 → 다음 기회에 다시 시도 가능
                logger.warning(
                    "[todo_reminders] no success -> NOT marked (will retry next run) todo_num=%s",
                    todo.todo_num
                )

            db.commit()

        except Exception as e:
            db.rollback()
            logger.exception(
                "[todo_reminders] ERROR while sending todo_num=%s err=%s",
                todo.todo_num, e
            )
            # 다른 투두도 계속 처리

    logger.info("[todo_reminders] done sent_count=%d", sent_count)
    return sent_count
