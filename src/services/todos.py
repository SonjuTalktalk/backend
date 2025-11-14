# src/services/todos.py
from __future__ import annotations

from datetime import date, time as time_t, datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy import select, and_, or_, case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.todo_list import ToDoList

MAX_RETRY = 5
KST = timezone(timedelta(hours=9))  # Asia/Seoul


def _next_compact_todo_num(db: Session, owner_id: str) -> int:
    """
    해당 유저에서 사용 중인 todo_num을 오름차순 조회하고,
    1부터 시작해 가장 작은 빈 번호를 찾아 반환.
    """
    used_nums = (
        db.execute(
            select(ToDoList.todo_num)
            .where(ToDoList.owner_cognito_id == owner_id)
            .order_by(ToDoList.todo_num.asc())
        )
        .scalars()
        .all()
    )
    expect = 1
    for n in used_nums:
        if n is None:
            continue
        if n > expect:
            break
        if n == expect:
            expect += 1
    return expect


def create_todo_compact(
    db: Session,
    owner_id: str,
    task: str,
    due_date: date,
    due_time: Optional[time_t] = None,
) -> ToDoList:
    """
    '빈 번호 메우기' 전략으로 todo_num을 부여해 생성.
    동시성으로 유니크 충돌이 나면 번호를 다시 계산해 재시도.
    (복합 PK이므로 유니크 충돌 시 IntegrityError 발생)
    """
    for _ in range(MAX_RETRY):
        new_num = _next_compact_todo_num(db, owner_id)
        row = ToDoList(
            owner_cognito_id=owner_id,
            todo_num=new_num,
            task=task,
            due_date=due_date,
            due_time=due_time,
        )
        db.add(row)
        try:
            db.commit()
            # refresh 불필요(모든 필드 채움)하지만 습관적으로 유지 가능
            # db.refresh(row)
            return row
        except IntegrityError:
            db.rollback()
            continue
    raise RuntimeError("동시성으로 todo_num 할당 실패 (재시도 초과)")


def _base_sorted_query(owner_id: str):
    """
    정렬 규칙:
      1) due_time 있는 항목 먼저 (time_null_flag = 0)
      2) due_date 오름차순
      3) due_time 오름차순 (NULL은 뒤로)
    """
    time_null_flag = case((ToDoList.due_time.is_(None), 1), else_=0).label("time_null_flag")
    return (
        select(ToDoList)
        .where(ToDoList.owner_cognito_id == owner_id)
        .order_by(time_null_flag.asc(), ToDoList.due_date.asc(), ToDoList.due_time.asc())
    )


def list_past_incomplete(db: Session, owner_id: str) -> List[ToDoList]:
    """
    오늘(Asia/Seoul) 기준 지난 것들 & 미완료:
      - due_date < today
      - OR (due_date = today AND due_time NOT NULL AND due_time < now)
    """
    now = datetime.now(KST)
    today = now.date()
    current_time = now.time()

    stmt = _base_sorted_query(owner_id).where(
        and_(
            ToDoList.is_completed.is_(False),
            or_(
                ToDoList.due_date < today,
                and_(
                    ToDoList.due_date == today,
                    ToDoList.due_time.is_not(None),
                    ToDoList.due_time < current_time,
                ),
            ),
        )
    )
    return db.execute(stmt).scalars().all()


def list_today_incomplete(db: Session, owner_id: str) -> List[ToDoList]:
    """
    오늘 날짜 & 미완료 (시간 유무 무관)
    """
    today = datetime.now(KST).date()
    stmt = _base_sorted_query(owner_id).where(
        and_(ToDoList.is_completed.is_(False), ToDoList.due_date == today)
    )
    return db.execute(stmt).scalars().all()


def list_future_incomplete(db: Session, owner_id: str) -> List[ToDoList]:
    """
    오늘 이후 & 미완료
    """
    today = datetime.now(KST).date()
    stmt = _base_sorted_query(owner_id).where(
        and_(ToDoList.is_completed.is_(False), ToDoList.due_date > today)
    )
    return db.execute(stmt).scalars().all()


def list_completed(db: Session, owner_id: str) -> List[ToDoList]:
    """
    완료된 것들
    """
    stmt = _base_sorted_query(owner_id).where(ToDoList.is_completed.is_(True))
    return db.execute(stmt).scalars().all()


def get_todo_by_num(db: Session, owner_id: str, todo_num: int) -> Optional[ToDoList]:
    """
    (owner_id, todo_num)로 특정 투두 조회
    """
    return (
        db.execute(
            select(ToDoList).where(
                ToDoList.owner_cognito_id == owner_id,
                ToDoList.todo_num == todo_num,
            )
        )
        .scalars()
        .first()
    )


def delete_todo_by_num(db: Session, owner_id: str, todo_num: int) -> bool:
    """
    (owner_id, todo_num)로 삭제
    """
    row = get_todo_by_num(db, owner_id, todo_num)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def toggle_complete(db: Session, owner_id: str, todo_num: int) -> Optional[ToDoList]:
    """
    완료/미완료 토글
    """
    row = get_todo_by_num(db, owner_id, todo_num)
    if not row:
        return None
    row.is_completed = not row.is_completed
    db.commit()
    return row


def update_todo(
    db: Session,
    owner_id: str,
    todo_num: int,
    *,
    task: Optional[str] = None,
    due_date: Optional[date] = None,
    due_time: Optional[time_t] = None,
) -> Optional[ToDoList]:
    """
    날짜/시간/task 부분 수정
    """
    row = get_todo_by_num(db, owner_id, todo_num)
    if not row:
        return None

    if task is not None:
        row.task = task
    if due_date is not None:
        row.due_date = due_date
    if due_time is not None:
        row.due_time = due_time

    db.commit()
    return row
