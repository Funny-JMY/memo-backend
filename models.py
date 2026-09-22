from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from database import Base


def utcnow() -> datetime:
    # SQLite와 Postgres의 동작을 맞추기 위해 타임존을 뗀 UTC로 통일해서 저장한다.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GuestbookEntry(Base):
    __tablename__ = "guestbook_entries"

    id = Column(Integer, primary_key=True, index=True)
    nickname = Column(String(30), nullable=False)
    relation = Column(String(20), nullable=False, default="visitor")
    message = Column(String(500), nullable=False)
    status = Column(String(10), nullable=False, default="published", index=True)
    reply = Column(String(500))
    replied_at = Column(DateTime)
    author_hash = Column(String(32), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("section", "visitor_hash", name="uq_reaction_once"),
    )

    id = Column(Integer, primary_key=True, index=True)
    section = Column(String(20), nullable=False, index=True)
    visitor_hash = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    visitor_hash = Column(String(32), nullable=False, index=True)
    path = Column(String(120), nullable=False, default="/")
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
