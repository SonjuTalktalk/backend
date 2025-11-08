from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# from sqlalchemy import text : db.execute(text("DELETE FROM daily_challenge_picks"))실행시 필요

from src.routers import auth, profile, ai_profile, challenge
from src.db.database import engine, Base, SessionLocal




# 데이터베이스 테이블 생성 (처음 실행 시)
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    - 앱 시작 시 스케줄러 등록
    - 매일 00:00 KST마다 챌린지 자동생성
    - 앱 종료 시 스케줄러 종료
    """
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Seoul"))

    # def _job():
        
    #     db = SessionLocal()
    #     try:
            
            
    #          # 테이블 4개로 고정 코드
    #         # db.execute(text("DELETE FROM daily_challenge_picks"))
        
        
    #         # 테이블 7일동안 저장해놓기
    #         '''
    #         db.execute(text("""
    #             DELETE FROM daily_challenge_picks
    #             WHERE date_for < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
    #         """)) 
    #         db.commit()
    #         '''
            
            
    #         # challenge 모듈의 함수 직접 호출
    #         challenge.pick_and_store_today(db)
    #         print("[스케줄러] 오늘의 챌린지 자동 생성 완료")
    #     except Exception as e:
    #         print(f"[스케줄러 오류] {e}")
    #     finally:
    #         db.close()
    

    
    
    
    # 재뽑기 테스트용 작업
    def _job():
        db = SessionLocal()
        try:
            
            # 테이블 4개로 고정 코드
            # db.execute(text("DELETE FROM daily_challenge_picks"))
        
        
            # 테이블 7일동안 저장해놓기
            '''
            db.execute(text("""
                DELETE FROM daily_challenge_picks
                WHERE date_for < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            """)) 
            db.commit()
            '''
            
            rows = challenge.pick_and_store_today(db, replace=True)  # 테스트 중에는 True
            print("[스케줄러] 재뽑기 완료:", [r.id for r in rows])
        except Exception as e:
            print("[스케줄러 오류]", e)
        finally:
             db.close()




    # 매일 00:00에 실행(원문)
    scheduler.add_job(_job, CronTrigger(hour=0, minute=0))
       
    scheduler.start()  

    try:
        yield  
    finally:
        scheduler.shutdown(wait=False)
        print("스케줄러 종료됨")

app = FastAPI(lifespan=lifespan)

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

# 확인용 엔드포인트
@app.get("/")   
async def root():   
    return {
        "message": "COOP Team7 API가 정상 작동 중입니다",
        "version": "1.0.0"
    }