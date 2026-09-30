from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.schemas import (
    AccountOut,
    DashboardOut,
    EntityMetricsOut,
    HypeCandidateOut,
    MetricPointOut,
    PollResultOut,
    RawEventOut,
    SourceHealthOut,
    SourceOut,
    TrackedEntityOut,
    VelocityOut,
)
from app.db.models import Account, HypeCandidate, MetricObservation, RawEvent, Source, TrackedEntity
from app.db.session import get_db
from app.services.collector import poll_all_enabled, poll_source
from app.services.discovery import persist_github_discovery, persist_hf_discovery
from app.services.health import (
    events_24h_by_group,
    list_source_health,
    recent_derivative_activity,
    recent_events,
    status_counts,
    tracked_entity_counts,
)
from app.services.metrics import compute_velocity

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
        healthy=counts.get("Healthy", 0),
        stale=counts.get("Stale", 0),
        error=counts.get("Error", 0),
        disabled=counts.get("Disabled", 0),
        rate_limited=counts.get("Rate Limited", 0),
        events_24h_by_group=events_24h_by_group(db),
        recent_events=[_event_out(e) for e in recent_events(db, 30)],
        tracked_entities=tracked_entity_counts(db),
        recent_derivative_activity=recent_derivative_activity(db),
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


def _entity_out(entity: TrackedEntity) -> TrackedEntityOut:
    return TrackedEntityOut.model_validate(entity)


@router.get("/entities", response_model=list[TrackedEntityOut])
def list_entities(
    platform: Optional[str] = None,
    entity_type: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TrackedEntityOut]:
    stmt = select(TrackedEntity)
    if platform:
        stmt = stmt.where(TrackedEntity.platform == platform)
    if entity_type:
        stmt = stmt.where(TrackedEntity.entity_type == entity_type)
    if since:
        stmt = stmt.where(TrackedEntity.last_seen_at >= since)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (TrackedEntity.display_name.ilike(like))
            | (TrackedEntity.external_id.ilike(like))
        )
    stmt = stmt.order_by(TrackedEntity.last_seen_at.desc()).offset(offset).limit(limit)
    return [_entity_out(e) for e in db.scalars(stmt).all()]


@router.get("/entities/{entity_id}", response_model=TrackedEntityOut)
def get_entity(entity_id: int, db: Session = Depends(get_db)) -> TrackedEntityOut:
    entity = db.get(TrackedEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _entity_out(entity)


@router.get("/entities/{entity_id}/metrics", response_model=EntityMetricsOut)
def get_entity_metrics(entity_id: int, db: Session = Depends(get_db)) -> EntityMetricsOut:
    entity = db.get(TrackedEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    rows = db.scalars(
        select(MetricObservation)
        .where(MetricObservation.tracked_entity_id == entity_id)
        .order_by(MetricObservation.observed_at.asc(), MetricObservation.id.asc())
    ).all()
    series: dict[str, list[MetricPointOut]] = {}
    for row in rows:
        series.setdefault(row.metric_name, []).append(
            MetricPointOut(
                observed_at=row.observed_at,
                value=row.metric_value,
                text=row.metric_text,
                metadata=row.metadata_json,
            )
        )
    return EntityMetricsOut(entity=_entity_out(entity), series=series)


@router.get("/entities/{entity_id}/velocity", response_model=VelocityOut)
def get_entity_velocity(
    entity_id: int,
    metric: str = Query(...),
    window_hours: int = Query(default=24, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
) -> VelocityOut:
    entity = db.get(TrackedEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return VelocityOut(**compute_velocity(db, entity_id, metric, window_hours))


@router.get("/discovery/github")
async def discovery_github(
    q: str = Query(...),
    limit: int = Query(default=30, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.adapters.github import GitHubRateLimitError, search_github_repos

    gh_source = db.scalar(
        select(Source).where(Source.platform == "github").order_by(Source.id).limit(1)
    )
    try:
        items = await search_github_repos(q, limit=limit, source=gh_source)
    except GitHubRateLimitError as exc:
        if gh_source is not None:
            pending = getattr(gh_source, "_pending_cursor", None)
            if pending:
                gh_source.cursor_json = pending
            gh_source.last_error = str(exc)
            from app.core.timeutil import utcnow

            gh_source.last_error_at = utcnow()
            db.commit()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    items = persist_github_discovery(db, items)
    if gh_source is not None:
        pending = getattr(gh_source, "_pending_cursor", None)
        if pending:
            gh_source.cursor_json = pending
            db.commit()
    return items


@router.get("/discovery/huggingface/models")
def discovery_hf_models(
    q: str = Query(...),
    limit: int = Query(default=30, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.adapters.huggingface import search_hf

    items = search_hf("model", q, limit=limit)
    return persist_hf_discovery(db, items)


@router.get("/discovery/huggingface/datasets")
def discovery_hf_datasets(
    q: str = Query(...),
    limit: int = Query(default=30, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.adapters.huggingface import search_hf

    items = search_hf("dataset", q, limit=limit)
    return persist_hf_discovery(db, items)


@router.get("/discovery/huggingface/spaces")
def discovery_hf_spaces(
    q: str = Query(...),
    limit: int = Query(default=30, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.adapters.huggingface import search_hf

    items = search_hf("space", q, limit=limit)
    return persist_hf_discovery(db, items)
