# src/db/database.py
#aws RDS MySQL 연결 설정
import os                                                   
from sqlalchemy import create_engine                        
from sqlalchemy.orm import sessionmaker, declarative_base   
from sqlalchemy.engine import URL                           
from dotenv import load_dotenv

load_dotenv()

# 환경 변수에서 데이터베이스 연결 정보 로드
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost") 

DB_PORT_RAW = os.getenv("DB_PORT")
DB_PORT = int(DB_PORT_RAW) if DB_PORT_RAW else None

DB_NAME = os.getenv("DB_NAME")

# SQLAlchemy 데이터베이스 URL 구성
url = URL.create(
    "mysql+pymysql",
    username=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

engine = create_engine(
    url,
    pool_pre_ping=True,     # 끊긴 커넥션 자동 감지 
    pool_recycle=1800,      # 30분마다 커넥션 새로고침
    pool_size=5,            # 기본 커넥션 풀 크기 
    max_overflow=10         # 초과 시 임시로 늘릴 수 있는 연결 수
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 의존성 주입을 위한 데이터베이스 세션 생성기
def get_db():
    db = SessionLocal()
    try:
        yield db # 이 db가 FastAPI의 엔드포인트 함수 안으로 전달됨
    finally:
        db.close() # 요청 끝나면 세션 닫음  