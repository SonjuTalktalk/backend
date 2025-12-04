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

import os
import firebase_admin
from firebase_admin import credentials

from fastapi.staticfiles import StaticFiles

# 테이블 생성 (알렘빅 쓰면 이 줄은 빼도 됨)
Base.metadata.create_all(bind=engine)


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
        else:
            print("ℹ️ [정보] Firebase가 이미 실행 중입니다.")
    else:
        # 키 파일이 없으면 경고만 출력 (서버 다운 방지)
        print(f"⚠️ [경고] '{key_path}' 파일을 찾을 수 없습니다.")
        print("👉 로컬 개발 시 루트 폴더에 키 파일을 넣어주세요. (알림 기능 제한됨)")
        
        
    """
    - 앱 시작 시 스케줄러 등록
    - 매일 00:00 KST마다 '어제 이전 daily 기록' 삭제
      (daily_challenge_picks, daily_challenge_user_states)
    - 앱 종료 시 스케줄러 종료
    """
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Seoul"))

    def _job():
        db = SessionLocal()
        try:
            # 🔹 하루 지난 daily 기록 삭제
            #   - date_for < CURDATE() 인 것들 전부 삭제
            #   - 오늘(예: 2025-11-27) 기준, 26일 이전 데이터 다 날림
            db.execute(text("""
                DELETE FROM daily_challenge_picks
                WHERE date_for < CURDATE()
            """))

            db.execute(text("""
                DELETE FROM daily_challenge_user_states
                WHERE date_for < CURDATE()
            """))

            db.commit()
            print("[스케줄러] 오래된 daily 기록 정리 완료")
        except Exception as e:
            print(f"[스케줄러 오류] {e}")
        finally:
            db.close()

    # 매일 00:00에 실행
    scheduler.add_job(_job, CronTrigger(hour=0, minute=0))
    # 테스트용으로 30초마다 돌려보고 싶으면 아래 라인 잠깐 쓰면 됨
    # scheduler.add_job(_job, CronTrigger(second="*/30"))

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

# 확인용 엔드포인트
@app.get("/")
async def root():
    return {
        "message": "COOP Team7 API가 정상 작동 중입니다",
        "version": "1.0.0"
    }
