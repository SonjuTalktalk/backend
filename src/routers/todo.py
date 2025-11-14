# src/routers/todos.py
from __future__ import annotations

from datetime import date, time as time_t
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.auth.dependencies import get_current_user
from src.models.users import User
from src.services.todos import (
    create_todo_compact,
    delete_todo_by_num,
    update_todo,
    list_past_incomplete,
    list_today_incomplete,
    list_future_incomplete,
    list_completed,
    toggle_complete
)

router = APIRouter(prefix="/todos", tags=["투두"])

# ---------- 스키마 ----------
class CreateTodoReq(BaseModel):
    task: str = Field(min_length=1, description="할 일 내용")
    due_date: date
    due_time: Optional[time_t] = None

class UpdateTodoReq(BaseModel):
    task: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[time_t] = None

class TodoItem(BaseModel):
    owner_cognito_id: str
    todo_num: int
    task: str
    is_completed: bool
    due_date: date
    due_time: Optional[time_t] = None

    @field_serializer("due_time")
    def serialize_due_time(self, v: Optional[time_t], _info):
        if v is None:
            return None
        return v.strftime("%H:%M")

class ToggleCompleteReq(BaseModel):
    # 프론트가 완료/미완료를 바꾸고 싶은 todo_num들을 배열로 보냄
    # 예: [3]  → 3번 하나만 토글
    # 예: [1, 2, 5] → 1,2,5번을 한 번에 토글
    todo_nums: List[int] = Field(..., min_length=1, description="완료 토글할 todo_num 목록")


# ---------- 삽입 ----------
@router.post("", response_model=TodoItem, status_code=201)
def create_todo(
    req: CreateTodoReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    row = create_todo_compact(db, uid, req.task, req.due_date, req.due_time)
    return TodoItem(
        owner_cognito_id=row.owner_cognito_id,
        todo_num=row.todo_num,
        task=row.task,
        is_completed=row.is_completed,
        due_date=row.due_date,
        due_time=row.due_time,
    )


# ---------- 삭제 (번호로) ----------
@router.delete("/{todo_num}", status_code=204)
def delete_todo(
    todo_num: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    ok = delete_todo_by_num(db, uid, todo_num)
    if not ok:
        raise HTTPException(status_code=404, detail="Todo not found")



# ---------- 수정 (완료/미완료) ----------
@router.patch("/complete", response_model=List[TodoItem])
def toggle_todo_complete(
    req: ToggleCompleteReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    ✔ 프론트에서 여러 개의 todo_num을 한 번에 토글할 수 있는 엔드포인트
    - todo_nums에 하나만 넣으면 단일 토글
    - todo_nums에 여러 개 넣으면 여러 개 일괄 토글
    - 토글 = is_completed True ↔ False 반전
    
    PATCH /todos/complete{
    - "todo_nums": [1, 2, 5] 여러개
    - "todo_nums": [3] 단일 }
    
    """
    uid = current_user.cognito_id
    updated_rows = []

    for num in req.todo_nums:
        row = toggle_complete(db, uid, num)
        if row:
            updated_rows.append(row)

    if not updated_rows:
        # 전부 못 찾았으면 404
        raise HTTPException(status_code=404, detail="Todo not found")

    return [
        TodoItem(
            owner_cognito_id=r.owner_cognito_id,
            todo_num=r.todo_num,
            task=r.task,
            is_completed=r.is_completed,
            due_date=r.due_date,
            due_time=r.due_time,
        )
        for r in updated_rows
    ]


# ---------- 수정 (날짜/시간/task) ----------
@router.patch("/{todo_num}", response_model=TodoItem)
def patch_todo(
    todo_num: int,
    req: UpdateTodoReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    row = update_todo(
        db,
        uid,
        todo_num,
        task=req.task,
        due_date=req.due_date,
        due_time=req.due_time,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoItem(
        owner_cognito_id=row.owner_cognito_id,
        todo_num=row.todo_num,
        task=row.task,
        is_completed=row.is_completed,
        due_date=row.due_date,
        due_time=row.due_time,
    )



# ---------- GET 4가지 뷰 ----------
@router.get("/past", response_model=List[TodoItem])
def get_past_incomplete(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    rows = list_past_incomplete(db, uid)
    return [
        TodoItem(
            owner_cognito_id=r.owner_cognito_id,
            todo_num=r.todo_num,
            task=r.task,
            is_completed=r.is_completed,
            due_date=r.due_date,
            due_time=r.due_time,
        )
        for r in rows
    ]


@router.get("/today", response_model=List[TodoItem])
def get_today_incomplete(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    rows = list_today_incomplete(db, uid)
    return [
        TodoItem(
            owner_cognito_id=r.owner_cognito_id, todo_num=r.todo_num,
            task=r.task, is_completed=r.is_completed,
            due_date=r.due_date, due_time=r.due_time,
        )
        for r in rows
    ]


@router.get("/future", response_model=List[TodoItem])
def get_future_incomplete(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    rows = list_future_incomplete(db, uid)
    return [
        TodoItem(
            owner_cognito_id=r.owner_cognito_id, todo_num=r.todo_num,
            task=r.task, is_completed=r.is_completed,
            due_date=r.due_date, due_time=r.due_time,
        )
        for r in rows
    ]


@router.get("/completed", response_model=List[TodoItem])
def get_completed(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.cognito_id
    rows = list_completed(db, uid)
    return [
        TodoItem(
            owner_cognito_id=r.owner_cognito_id, todo_num=r.todo_num,
            task=r.task, is_completed=r.is_completed,
            due_date=r.due_date, due_time=r.due_time,
        )
        for r in rows
    ]
