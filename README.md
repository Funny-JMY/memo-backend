# 자기소개 페이지 — Backend

클라우드 컴퓨팅 실습 과제로 만든 개인 소개 페이지의 백엔드입니다.
FastAPI로 방명록, 섹션 반응, 방문 통계 API를 제공하며 Swagger UI에서 바로 테스트할 수 있습니다.

## 배포 주소

| 구분 | 주소 |
| --- | --- |
| API 문서 (Swagger UI) | https://memo-backend-sn8m.onrender.com/docs |
| 소개 페이지 (Vercel) | https://memo-frontend-yjm3.vercel.app/ |
| 프론트엔드 저장소 | https://github.com/Funny-JMY/memo-frontend |

## API 목록

| 그룹 | 메서드 | 경로 | 설명 |
| --- | --- | --- | --- |
| 방명록 | GET | `/guestbook` | 공개된 글 목록 (페이지네이션) |
| 방명록 | POST | `/guestbook` | 글 작성 (도배 방지 제한 적용) |
| 방명록 | GET | `/guestbook/{id}` | 단건 조회 |
| 반응 | GET | `/reactions` | 섹션별 공감 수 |
| 반응 | POST | `/reactions/{section}` | 공감 누르기 (중복 시 409) |
| 반응 | DELETE | `/reactions/{section}` | 공감 취소 |
| 통계 | POST | `/visits` | 방문 기록 |
| 통계 | GET | `/stats` | 방문·방명록·공감 집계와 최근 추이 |
| 관리자 | GET | `/admin/guestbook` | 숨김 글 포함 전체 목록 |
| 관리자 | PATCH | `/admin/guestbook/{id}/status` | 공개 / 숨김 전환 |
| 관리자 | POST | `/admin/guestbook/{id}/reply` | 답글 달기 |
| 관리자 | DELETE | `/admin/guestbook/{id}` | 삭제 |
| 시스템 | GET | `/health` | 상태 및 DB 연결 확인 |

관리자 API는 `X-Admin-Token` 헤더가 필요합니다. Swagger UI 우측 상단 **Authorize** 버튼에 토큰을 입력하면 그대로 테스트할 수 있습니다.

## 주요 동작

- **도배 방지** — 같은 방문자는 60초 안에 다시 쓸 수 없고, 하루 10개까지만 남길 수 있습니다 (초과 시 `429`).
- **방문자 식별** — IP 원문을 저장하지 않고 솔트를 섞은 SHA-256 해시만 보관해 중복 공감과 도배를 판별합니다.
- **모더레이션** — 남겨진 글은 기본 공개이며, 관리자가 숨기거나 삭제할 수 있습니다.
- **답글** — 관리자가 방명록에 답글을 달면 소개 페이지에 함께 표시됩니다.

## 구성

```
├── main.py         # FastAPI 앱, 라우트, 관리자 인증, 도배 방지
├── models.py       # SQLAlchemy 테이블 (방명록 / 반응 / 방문)
├── schemas.py      # Pydantic 요청·응답 모델
├── database.py     # DB 엔진과 세션
└── requirements.txt
```

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload       # http://localhost:8000/docs
```

로컬에서는 SQLite(`intro.db`)를 사용하고, 관리자 토큰은 `dev-admin-token`이 기본값으로 설정됩니다.

## 환경 변수

| 이름 | 설명 | 기본값 |
| --- | --- | --- |
| `DATABASE_URL` | DB 접속 주소 | `sqlite:///./intro.db` |
| `ALLOWED_ORIGINS` | CORS 허용 출처 (쉼표 구분) | `http://localhost:5173` |
| `ADMIN_TOKEN` | 관리자 API 토큰 | 로컬은 `dev-admin-token`, **운영은 필수** |
| `VISITOR_HASH_SALT` | 방문자 해시용 솔트 | `local-dev-salt` |
| `GUESTBOOK_COOLDOWN_SECONDS` | 재작성 대기 시간(초) | `60` |
| `GUESTBOOK_DAILY_LIMIT` | 하루 작성 한도 | `10` |

`ADMIN_TOKEN`은 운영 환경(비-SQLite)에서 설정하지 않으면 서버가 시작되지 않습니다. 기본 토큰이 그대로 노출되는 것을 막기 위한 장치입니다.

## 배포 (Render)

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 환경 변수에 `ADMIN_TOKEN`, `VISITOR_HASH_SALT`, `ALLOWED_ORIGINS`(Vercel 주소)를 등록합니다.
- 방명록 데이터를 유지하려면 `DATABASE_URL`에 Render PostgreSQL 주소를 연결합니다. SQLite를 쓰면 재배포 시 데이터가 사라집니다.
