from sqlalchemy import Column, Integer, String
from database import Base

class Memo(Base):
    __tablename__ = "memos"          # 실제 테이블 이름
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)