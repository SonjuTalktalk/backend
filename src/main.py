# src/main.py
import datetime as dt

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from src.routers import todo
from src.routers import auth, profile, ai_profile, challenge, chat_lists, chat_message, health, item, background
from src.db.database import engine, Base, SessionLocal
from src.routers import notifications
from src.routers.kakaopay import router as kakaopay_router

# ✅ 추가: FCM 토큰 라우터
from src.routers import fcm

# ✅ 추가: 투두 30분 전 알림 처리 서비스
from src.services.todo_reminders import process_due_todo_reminders

import os
import firebase_admin
from firebase_admin import credentials


# ✅ 추가: create_all이 fcm_tokens 테이블을 인식하도록 모델 import (중요)
# (create_all은 "테이블 생성"만 하고 기존 테이블 컬럼 추가는 못함)
import src.models.fcm_token  # noqa: F401

import logging

logging.basicConfig( level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s" )
Base.metadata.create_all(bind=engine) # <- 이거 지우지 마세요 SQLAlchemy로 정의한 DB 테이블 DBMS에 생성해주는 코드입니다

@asynccontextmanager
async def lifespan(app: FastAPI):

    key_path = "firebase-key.json"  # backend 폴더 바로 아래에 있어야 합니다.

    # 1. 파일 존재 여부 확인 (안전장치)
    if os.path.exists(key_path):
        # 키 파일이 있으면 연결 시도
        cred = credentials.Certificate(key_path)

        # 2. 이미 연결된 상태인지 확인 (FastAPI 재시작 시 에러 방지)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            print("✅ [성공] Firebase(FCM) 서버와 연결되었습니다!")
            logging.info("✅ [성공] Firebase(FCM) 서버와 연결되었습니다!")
        else:
            print("ℹ️ [정보] Firebase가 이미 실행 중입니다.")
            logging.info("ℹ️ [정보] Firebase가 이미 실행 중입니다. \n")
    else:
        # 키 파일이 없으면 경고만 출력 (서버 다운 방지)
        print(f"⚠️ [경고] '{key_path}' 파일을 찾을 수 없습니다.")
        print("👉 로컬 개발 시 루트 폴더에 키 파일을 넣어주세요. (알림 기능 제한됨)")

    """
    - 앱 시작 시 스케줄러 등록
    - 매일 00:00 KST마다 '어제 이전 daily 기록' 삭제
      (daily_challenge_picks, daily_challenge_user_states)
    - 매일 00:00 KST마다 '3일 지난 notifications' 삭제
    - ✅ 매 1분마다 '투두 due_time 30분 전' 푸시 발송
    - 앱 종료 시 스케줄러 종료
    """
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Seoul"))

    def _cleanup_job():
        db = SessionLocal()
        try:
            # 🔹 하루 지난 daily 기록 삭제
            db.execute(text("""
                DELETE FROM daily_challenge_picks
                WHERE date_for < CURDATE()
            """))

            db.execute(text("""
                DELETE FROM daily_challenge_user_states
                WHERE date_for < CURDATE()
            """))

            # ✅ 🔔 3일 지난 알림 삭제 (noti_date, noti_time 기준)
            #    (KST 기준으로 계산하되, DB에는 tz 없는 date/time 저장이라 tzinfo 제거)
            now_kst = dt.datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None, microsecond=0)
            cutoff = now_kst - dt.timedelta(days=3)

            db.execute(
                text("""
                    DELETE FROM notifications
                    WHERE (noti_date < :cutoff_date)
                       OR (noti_date = :cutoff_date AND noti_time < :cutoff_time)
                """),
                {
                    "cutoff_date": cutoff.date(),
                    "cutoff_time": cutoff.time(),
                }
            )

            db.commit()
            print("[스케줄러] 오래된 daily 기록 + 오래된 notifications 정리 완료")

        except Exception as e:
            db.rollback()
            print(f"[스케줄러 오류][cleanup] {e}")
        finally:
            db.close()

    def _todo_reminder_job():
        """
        ✅ 매 1분마다 실행:
        - 'due_time이 있는 투두' 중에서
        - '현재 + 30분'에 해당하는 것들을 찾아
        - FCM 푸시 발송
        - 중복 방지를 위해 todo_lists.reminder_sent_at을 사용
        """
        db = SessionLocal()
        try:
            sent = process_due_todo_reminders(db, minutes_before=30)
            if sent:
                print(f"[스케줄러] todo 30분전 푸시 발송 sent={sent}")
        except Exception as e:
            # 서비스 내부에서 rollback/continue를 하더라도, 안전하게 여기서도 한번 더 방어
            db.rollback()
            print(f"[스케줄러 오류][todo_reminder] {e}")
        finally:
            db.close()

    # ✅ 매일 00:00에 정리 실행
    scheduler.add_job(_cleanup_job, CronTrigger(hour=0, minute=0))

    # ✅ 매 1분마다(매 분 0초) 투두 리마인더 실행
    scheduler.add_job(_todo_reminder_job, CronTrigger(second=0))

    # 테스트용으로 빠르게 돌려보고 싶으면 아래 라인 잠깐 쓰면 됨
    # scheduler.add_job(_todo_reminder_job, CronTrigger(second="*/10"))

    scheduler.start()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        print("스케줄러 종료됨")


os.makedirs("outputs/tts", exist_ok=True)

app = FastAPI(lifespan=lifespan)

# 🔽 TTS 등 outputs 폴더 정적 서빙
app.mount("/static", StaticFiles(directory="outputs"), name="static")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용하도록 수정 필요
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(ai_profile.router)
app.include_router(challenge.router)
app.include_router(chat_lists.router)
app.include_router(chat_message.router)
app.include_router(todo.router)
app.include_router(health.router)
app.include_router(item.router)
app.include_router(background.router)
app.include_router(notifications.router)
app.include_router(kakaopay_router)

# ✅ 추가: FCM 토큰 등록/해제 라우터
app.include_router(fcm.router)

# 확인용 엔드포인트
@app.get("/")
async def root():
    return {
        "message": "COOP Team7 API가 정상 작동 중입니다",
        "version": "1.0.0"
    }
