from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.schemas import (
    AccountOut,
    DashboardOut,
    HypeCandidateOut,
    PollResultOut,
    RawEventOut,
    SourceHealthOut,
    SourceOut,
)
from app.db.models import Account, HypeCandidate, RawEvent, Source
from app.db.session import get_db
from app.services.collector import poll_all_enabled, poll_source
from app.services.health import (
    events_24h_by_group,
    list_source_health,
    recent_events,
    status_counts,
)

router = APIRouter(prefix="/api")


def _event_out(event: RawEvent) -> RawEventOut:
    return RawEventOut(
        id=event.id,
        source_id=event.source_id,
        platform=event.platform,
        external_id=event.external_id,
        author=event.author,
        published_at=event.published_at,
        retrieved_at=event.retrieved_at,
        canonical_url=event.canonical_url,
        title=event.title,
        raw_text=event.raw_text,
        content_hash=event.content_hash,
        event_type=event.event_type,
        metadata_json=event.metadata_json,
        created_at=event.created_at,
        source_name=event.source.name if event.source else None,
    )


@router.get("/sources", response_model=list[SourceOut])
def get_sources(db: Session = Depends(get_db)) -> list[Source]:
    return list(db.scalars(select(Source).order_by(Source.id)).all())


@router.get("/sources/health", response_model=list[SourceHealthOut])
def get_sources_health(db: Session = Depends(get_db)) -> list[dict]:
    return list_source_health(db)


@router.get("/events", response_model=list[RawEventOut])
def get_events(
    platform: Optional[str] = None,
    source: Optional[str] = None,
    source_id: Optional[int] = None,
    q: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[RawEventOut]:
    stmt = select(RawEvent).options(joinedload(RawEvent.source))
    if platform:
        stmt = stmt.where(RawEvent.platform == platform)
    if source_id is not None:
        stmt = stmt.where(RawEvent.source_id == source_id)
    if source:
        stmt = stmt.join(Source).where(Source.name == source)
    if since:
        stmt = stmt.where(RawEvent.retrieved_at >= since)
    if until:
        stmt = stmt.where(RawEvent.retrieved_at <= until)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (RawEvent.title.ilike(like))
            | (RawEvent.raw_text.ilike(like))
            | (RawEvent.author.ilike(like))
        )
    stmt = stmt.order_by(RawEvent.retrieved_at.desc()).offset(offset).limit(limit)
    rows = db.scalars(stmt).unique().all()
    return [_event_out(e) for e in rows]


@router.get("/events/{event_id}", response_model=RawEventOut)
def get_event(event_id: int, db: Session = Depends(get_db)) -> RawEventOut:
    event = db.scalar(
        select(RawEvent)
        .options(joinedload(RawEvent.source))
        .where(RawEvent.id == event_id)
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_out(event)


@router.get("/accounts", response_model=list[AccountOut])
def get_accounts(db: Session = Depends(get_db)) -> list[Account]:
    return list(db.scalars(select(Account).order_by(Account.id)).all())


@router.get("/hype-candidates", response_model=list[HypeCandidateOut])
def get_hype_candidates(db: Session = Depends(get_db)) -> list[HypeCandidate]:
    return list(db.scalars(select(HypeCandidate).order_by(HypeCandidate.id)).all())


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardOut:
    counts = status_counts(db)
    return DashboardOut(
        healthy=counts["Healthy"],
        stale=counts["Stale"],
        error=counts["Error"],
        disabled=counts["Disabled"],
        events_24h_by_group=events_24h_by_group(db),
        recent_events=[_event_out(e) for e in recent_events(db, 30)],
    )


@router.post("/sources/{source_id}/poll", response_model=list[PollResultOut])
async def poll_one(source_id: int, db: Session = Depends(get_db)) -> list[PollResultOut]:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    results = []
    st = (source.source_type or "").lower()
    if st in {"hacker_news", "hn"}:
        results.append(await poll_source(db, source, feed="newstories"))
        db.refresh(source)
        results.append(await poll_source(db, source, feed="topstories"))
    else:
        results.append(await poll_source(db, source))
    return [
        PollResultOut(
            source_id=r.source_id,
            source_name=r.source_name,
            fetched=r.fetched,
            inserted=r.inserted,
            duplicates=r.duplicates,
            updated=r.updated,
            error=r.error,
            duration_ms=r.duration_ms,
        )
        for r in results
    ]


@router.post("/system/poll-all", response_model=list[PollResultOut])
async def poll_all(db: Session = Depends(get_db)) -> list[PollResultOut]:
    results = await poll_all_enabled(db)
    return [
        PollResultOut(
            source_id=r.source_id,
            source_name=r.source_name,
            fetched=r.fetched,
            inserted=r.inserted,
            duplicates=r.duplicates,
            updated=r.updated,
            error=r.error,
            duration_ms=r.duration_ms,
        )
        for r in results
    ]
