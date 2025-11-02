from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routers import auth, profile, ai_profile
from src.db.database import engine, Base

# 데이터베이스 테이블 생성 (처음 실행 시)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS 설정 (모바일 앱에서 API 호출 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용하도록 수정 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)      # /auth 경로의 엔드포인트들
app.include_router(profile.router)   # /profile 경로의 엔드포인트들
app.include_router(ai_profile.router)  # /ai 경로의 엔드포인트들

@app.get("/")   # 확인용 엔드포인트
async def root():   
    return {
        "message": "COOP Team7 API가 정상 작동 중입니다",
        "version": "1.0.0"
    }


@app.get("/health")     # 서버 상태 확인 (모니터링용)
async def health_check():
    return {"status": "healthy"}