import hashlib
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import DATABASE_URL, Base, SessionLocal, engine
from models import utcnow

Base.metadata.create_all(bind=engine)

IS_LOCAL = DATABASE_URL.startswith("sqlite")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or ("dev-admin-token" if IS_LOCAL else "")
if not ADMIN_TOKEN:
    raise RuntimeError("운영 환경에서는 ADMIN_TOKEN 환경변수를 반드시 설정해야 합니다.")

# 방문자를 구분하되 IP 원문은 저장하지 않기 위해, 솔트를 섞어 해시한 값만 보관한다.
HASH_SALT = os.getenv("VISITOR_HASH_SALT", "local-dev-salt")
COOLDOWN_SECONDS = int(os.getenv("GUESTBOOK_COOLDOWN_SECONDS", "60"))
DAILY_LIMIT = int(os.getenv("GUESTBOOK_DAILY_LIMIT", "10"))

app = FastAPI(
    title="양정모 자기소개 페이지 API",
    version="1.0.0",
    description=(
        "자기소개 페이지의 방명록·반응·방문 통계를 제공하는 API입니다.\n\n"
        "관리자 기능은 우측 상단 **Authorize** 버튼에 `X-Admin-Token` 값을 넣으면 테스트할 수 있습니다."
    ),
    openapi_tags=[
        {"name": "방명록", "description": "방문자가 남기는 글. 작성에는 도배 방지 제한이 걸려 있습니다."},
        {"name": "반응", "description": "섹션별 공감. 한 방문자당 섹션마다 한 번만 누를 수 있습니다."},
        {"name": "통계", "description": "방문 기록과 집계."},
        {"name": "관리자", "description": "X-Admin-Token 헤더가 필요한 운영용 엔드포인트."},
        {"name": "시스템", "description": "상태 확인."},
    ],
)

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

admin_scheme = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(token: str | None = Security(admin_scheme)) -> bool:
    if not token or not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 토큰이 필요합니다.",
        )
    return True


def visitor_hash(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    raw = f"{client_ip}|{request.headers.get('user-agent', '')}|{HASH_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def enforce_write_limits(db: Session, author_hash: str) -> None:
    now = utcnow()
    latest = (
        db.query(models.GuestbookEntry.created_at)
        .filter(models.GuestbookEntry.author_hash == author_hash)
        .order_by(models.GuestbookEntry.created_at.desc())
        .first()
    )
    if latest:
        elapsed = (now - latest[0]).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"{int(COOLDOWN_SECONDS - elapsed)}초 후에 다시 남겨주세요.",
            )

    today_count = (
        db.query(func.count(models.GuestbookEntry.id))
        .filter(
            models.GuestbookEntry.author_hash == author_hash,
            models.GuestbookEntry.created_at >= now - timedelta(days=1),
        )
        .scalar()
    )
    if today_count >= DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"하루에 최대 {DAILY_LIMIT}개까지 남길 수 있습니다.",
        )


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["시스템"], summary="상태 확인")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected", "time": utcnow()}


@app.get("/guestbook", response_model=schemas.GuestbookPage, tags=["방명록"], summary="방명록 목록")
def list_guestbook(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    base = db.query(models.GuestbookEntry).filter(
        models.GuestbookEntry.status == schemas.EntryStatus.published.value
    )
    total = base.with_entities(func.count(models.GuestbookEntry.id)).scalar()
    items = (
        base.order_by(models.GuestbookEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return schemas.GuestbookPage(total=total, limit=limit, offset=offset, items=items)


@app.post(
    "/guestbook",
    response_model=schemas.GuestbookOut,
    status_code=status.HTTP_201_CREATED,
    tags=["방명록"],
    summary="방명록 작성",
    responses={429: {"description": "연속 작성 또는 하루 작성 한도 초과"}},
)
def create_guestbook_entry(
    payload: schemas.GuestbookCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    author_hash = visitor_hash(request)
    enforce_write_limits(db, author_hash)

    entry = models.GuestbookEntry(
        nickname=payload.nickname,
        message=payload.message,
        relation=payload.relation.value,
        author_hash=author_hash,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get(
    "/guestbook/{entry_id}",
    response_model=schemas.GuestbookOut,
    tags=["방명록"],
    summary="방명록 단건 조회",
    responses={404: {"description": "없거나 숨김 처리된 글"}},
)
def get_guestbook_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(models.GuestbookEntry, entry_id)
    if not entry or entry.status != schemas.EntryStatus.published.value:
        raise HTTPException(status_code=404, detail="방명록을 찾을 수 없습니다.")
    return entry


@app.get(
    "/reactions",
    response_model=list[schemas.ReactionCount],
    tags=["반응"],
    summary="섹션별 공감 수",
)
def list_reactions(request: Request, db: Session = Depends(get_db)):
    me = visitor_hash(request)
    counts = dict(
        db.query(models.Reaction.section, func.count(models.Reaction.id))
        .group_by(models.Reaction.section)
        .all()
    )
    mine = {
        section
        for (section,) in db.query(models.Reaction.section)
        .filter(models.Reaction.visitor_hash == me)
        .all()
    }
    return [
        schemas.ReactionCount(
            section=section,
            count=counts.get(section.value, 0),
            reacted_by_me=section.value in mine,
        )
        for section in schemas.Section
    ]


@app.post(
    "/reactions/{section}",
    response_model=schemas.ReactionCount,
    status_code=status.HTTP_201_CREATED,
    tags=["반응"],
    summary="공감 누르기",
    responses={409: {"description": "이미 공감한 섹션"}},
)
def add_reaction(
    section: schemas.Section,
    request: Request,
    db: Session = Depends(get_db),
):
    me = visitor_hash(request)
    db.add(models.Reaction(section=section.value, visitor_hash=me))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 공감한 섹션입니다.")

    count = (
        db.query(func.count(models.Reaction.id))
        .filter(models.Reaction.section == section.value)
        .scalar()
    )
    return schemas.ReactionCount(section=section, count=count, reacted_by_me=True)


@app.delete(
    "/reactions/{section}",
    response_model=schemas.ReactionCount,
    tags=["반응"],
    summary="공감 취소",
    responses={404: {"description": "공감한 적 없는 섹션"}},
)
def remove_reaction(
    section: schemas.Section,
    request: Request,
    db: Session = Depends(get_db),
):
    me = visitor_hash(request)
    reaction = (
        db.query(models.Reaction)
        .filter(
            models.Reaction.section == section.value,
            models.Reaction.visitor_hash == me,
        )
        .first()
    )
    if not reaction:
        raise HTTPException(status_code=404, detail="공감한 기록이 없습니다.")

    db.delete(reaction)
    db.commit()
    count = (
        db.query(func.count(models.Reaction.id))
        .filter(models.Reaction.section == section.value)
        .scalar()
    )
    return schemas.ReactionCount(section=section, count=count, reacted_by_me=False)


@app.post(
    "/visits",
    response_model=schemas.VisitOut,
    status_code=status.HTTP_201_CREATED,
    tags=["통계"],
    summary="방문 기록",
)
def record_visit(
    request: Request,
    path: str = Query("/", max_length=120),
    db: Session = Depends(get_db),
):
    db.add(models.Visit(visitor_hash=visitor_hash(request), path=path))
    db.commit()
    total = db.query(func.count(models.Visit.id)).scalar()
    return schemas.VisitOut(recorded=True, total_visits=total)


@app.get("/stats", response_model=schemas.StatsOut, tags=["통계"], summary="집계 통계")
def get_stats(
    days: int = Query(7, ge=1, le=30, description="최근 며칠 치 추이를 볼지"),
    db: Session = Depends(get_db),
):
    today = utcnow().date()
    window_start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())

    visits_by_day = dict(
        db.query(func.date(models.Visit.created_at), func.count(models.Visit.id))
        .filter(models.Visit.created_at >= window_start)
        .group_by(func.date(models.Visit.created_at))
        .all()
    )
    entries_by_day = dict(
        db.query(
            func.date(models.GuestbookEntry.created_at),
            func.count(models.GuestbookEntry.id),
        )
        .filter(models.GuestbookEntry.created_at >= window_start)
        .group_by(func.date(models.GuestbookEntry.created_at))
        .all()
    )

    daily = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        daily.append(
            schemas.DailyActivity(
                date=key,
                # SQLite는 func.date()가 문자열을, Postgres는 date 객체를 돌려준다.
                visits=visits_by_day.get(key, visits_by_day.get(day, 0)),
                entries=entries_by_day.get(key, entries_by_day.get(day, 0)),
            )
        )

    status_counts = dict(
        db.query(models.GuestbookEntry.status, func.count(models.GuestbookEntry.id))
        .group_by(models.GuestbookEntry.status)
        .all()
    )
    reactions = dict(
        db.query(models.Reaction.section, func.count(models.Reaction.id))
        .group_by(models.Reaction.section)
        .all()
    )

    return schemas.StatsOut(
        total_visits=db.query(func.count(models.Visit.id)).scalar(),
        unique_visitors=db.query(
            func.count(func.distinct(models.Visit.visitor_hash))
        ).scalar(),
        visits_today=db.query(func.count(models.Visit.id))
        .filter(models.Visit.created_at >= datetime.combine(today, datetime.min.time()))
        .scalar(),
        guestbook_published=status_counts.get(schemas.EntryStatus.published.value, 0),
        guestbook_hidden=status_counts.get(schemas.EntryStatus.hidden.value, 0),
        guestbook_replied=db.query(func.count(models.GuestbookEntry.id))
        .filter(models.GuestbookEntry.reply.isnot(None))
        .scalar(),
        reactions={section.value: reactions.get(section.value, 0) for section in schemas.Section},
        daily=daily,
    )


@app.get(
    "/admin/guestbook",
    response_model=list[schemas.GuestbookAdminOut],
    tags=["관리자"],
    summary="숨김 글 포함 전체 목록",
    dependencies=[Depends(require_admin)],
)
def admin_list_guestbook(
    entry_status: schemas.EntryStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(models.GuestbookEntry)
    if entry_status:
        query = query.filter(models.GuestbookEntry.status == entry_status.value)
    return query.order_by(models.GuestbookEntry.created_at.desc()).limit(limit).all()


@app.patch(
    "/admin/guestbook/{entry_id}/status",
    response_model=schemas.GuestbookAdminOut,
    tags=["관리자"],
    summary="공개 / 숨김 전환",
    dependencies=[Depends(require_admin)],
)
def admin_update_status(
    entry_id: int,
    payload: schemas.StatusIn,
    db: Session = Depends(get_db),
):
    entry = db.get(models.GuestbookEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="방명록을 찾을 수 없습니다.")

    entry.status = payload.status.value
    db.commit()
    db.refresh(entry)
    return entry


@app.post(
    "/admin/guestbook/{entry_id}/reply",
    response_model=schemas.GuestbookAdminOut,
    tags=["관리자"],
    summary="방명록에 답글 달기",
    dependencies=[Depends(require_admin)],
)
def admin_reply(entry_id: int, payload: schemas.ReplyIn, db: Session = Depends(get_db)):
    entry = db.get(models.GuestbookEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="방명록을 찾을 수 없습니다.")

    entry.reply = " ".join(payload.reply.split())
    entry.replied_at = utcnow()
    db.commit()
    db.refresh(entry)
    return entry


@app.delete(
    "/admin/guestbook/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["관리자"],
    summary="방명록 삭제",
    dependencies=[Depends(require_admin)],
)
def admin_delete(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(models.GuestbookEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="방명록을 찾을 수 없습니다.")

    db.delete(entry)
    db.commit()
