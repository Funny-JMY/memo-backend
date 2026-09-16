import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ★ 환경변수 DATABASE_URL이 있으면 그것을, 없으면 로컬 SQLite 파일 사용.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./memo.db")

# SQLite는 한 스레드만 허용하므로 FastAPI에서 쓰려면 이 옵션이 필요.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
# 모델 클래스들이 상속할 기반 클래스 (SQLAlchemy 2.0 방식)
class Base(DeclarativeBase):
    pass