from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Relation(str, Enum):
    colleague = "colleague"
    classmate = "classmate"
    friend = "friend"
    recruiter = "recruiter"
    visitor = "visitor"


class EntryStatus(str, Enum):
    published = "published"
    hidden = "hidden"


class Section(str, Enum):
    about = "about"
    career = "career"
    interests = "interests"


class GuestbookCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=30, examples=["같은 팀 동료"])
    message: str = Field(
        min_length=2,
        max_length=500,
        examples=["시스템 이야기 재미있게 읽었습니다. 다음에 커피 한잔 하시죠."],
    )
    relation: Relation = Relation.visitor

    @field_validator("nickname", "message")
    @classmethod
    def strip_and_require_content(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("공백만으로는 남길 수 없습니다.")
        return cleaned


class GuestbookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str
    relation: Relation
    message: str
    reply: str | None = None
    replied_at: datetime | None = None
    created_at: datetime


class GuestbookAdminOut(GuestbookOut):
    status: EntryStatus
    author_hash: str


class GuestbookPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[GuestbookOut]


class ReplyIn(BaseModel):
    reply: str = Field(
        min_length=1,
        max_length=500,
        examples=["들러주셔서 감사합니다. 곧 연락드릴게요."],
    )


class StatusIn(BaseModel):
    status: EntryStatus


class ReactionCount(BaseModel):
    section: Section
    count: int
    reacted_by_me: bool


class VisitOut(BaseModel):
    recorded: bool
    total_visits: int


class DailyActivity(BaseModel):
    date: str
    visits: int
    entries: int


class StatsOut(BaseModel):
    total_visits: int
    unique_visitors: int
    visits_today: int
    guestbook_published: int
    guestbook_hidden: int
    guestbook_replied: int
    reactions: dict[str, int]
    daily: list[DailyActivity]
