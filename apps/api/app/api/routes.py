from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.schemas import (
    AcceptSignalIn,
    AccountListItemOut,
    AccountOut,
    AccountStatsOut,
    AttachSignalIn,
    CandidateSignalOut,
    CandidateSnapshotOut,
    DashboardOut,
    EntityMetricsOut,
    HypeAliasIn,
    HypeAliasOut,
    HypeCandidateDetailOut,
    HypeCandidateOut,
    HypeCandidatePatchIn,
    ManualXIngestIn,
    ManualXIngestOut,
    MergeSignalIn,
    MetricPointOut,
    PollResultOut,
    PromoteEventIn,
    RawEventOut,
    RejectSignalIn,
    SnapshotScheduleOut,
    SourceHealthOut,
    SourceOut,
    TimelineItemOut,
    TrackedEntityOut,
    VelocityOut,
)
from app.core.timeutil import ensure_aware, utcnow
from app.db.models import (
    Account,
    AccountEvent,
    CandidateSignal,
    CandidateSnapshot,
    CandidateSnapshotSchedule,
    HypeAlias,
    HypeCandidate,
    MetricObservation,
    RawEvent,
    Source,
    TrackedEntity,
)
from app.db.session import get_db
from app.services.candidate_extraction import normalize_candidate_text
from app.services.candidate_review import (
    accept_as_new_hype,
    add_alias,
    attach_to_hype,
    merge_signal,
    promote_raw_event,
    reject_signal,
)
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
from app.services.x_ingest import manual_ingest

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


@router.get("/accounts", response_model=list[AccountListItemOut])
def get_accounts(
    role: Optional[str] = None,
    tier: Optional[str] = None,
    priority: Optional[str] = None,
    enabled: Optional[bool] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[AccountListItemOut]:
    stmt = select(Account)
    if role:
        like = f"%{role}%"
        stmt = stmt.where(
            or_(Account.primary_bucket.ilike(like), Account.secondary_role.ilike(like))
        )
    if tier:
        stmt = stmt.where(Account.universe_tier == tier)
    if priority:
        stmt = stmt.where(Account.monitor_priority == priority)
    if enabled is not None:
        stmt = stmt.where(Account.enabled.is_(enabled))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Account.handle.ilike(like),
                Account.display_name.ilike(like),
                Account.primary_bucket.ilike(like),
            )
        )
    accounts = list(db.scalars(stmt.order_by(Account.handle.asc())).all())
    now = utcnow()
    since_30 = now - timedelta(days=30)
    out: list[AccountListItemOut] = []
    for acc in accounts:
        events = db.scalars(
            select(AccountEvent).where(AccountEvent.account_id == acc.id)
        ).all()
        events_30d = sum(1 for e in events if ensure_aware(e.observed_at) and ensure_aware(e.observed_at) >= since_30)
        last_at = None
        if events:
            last_at = max((ensure_aware(e.observed_at) for e in events if e.observed_at), default=None)
        open_signals = db.scalar(
            select(func.count())
            .select_from(CandidateSignal)
            .join(AccountEvent, CandidateSignal.account_event_id == AccountEvent.id)
            .where(AccountEvent.account_id == acc.id, CandidateSignal.state == "OPEN")
        ) or 0
        out.append(
            AccountListItemOut(
                id=acc.id,
                platform=acc.platform,
                handle=acc.handle,
                display_name=acc.display_name,
                primary_bucket=acc.primary_bucket,
                secondary_role=acc.secondary_role,
                universe_tier=acc.universe_tier,
                monitor_priority=acc.monitor_priority,
                conflict_risk=acc.conflict_risk,
                tech_to_crypto_relevance=acc.tech_to_crypto_relevance,
                enabled=acc.enabled,
                last_ingested_post_at=last_at,
                events_30d=events_30d,
                open_candidate_signals=int(open_signals),
            )
        )
    return out


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_db)) -> Account:
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.get("/accounts/{account_id}/stats", response_model=AccountStatsOut)
def get_account_stats(account_id: int, db: Session = Depends(get_db)) -> AccountStatsOut:
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    now = utcnow()
    since_24 = now - timedelta(hours=24)
    since_30 = now - timedelta(days=30)
    events = db.scalars(select(AccountEvent).where(AccountEvent.account_id == acc.id)).all()
    events_24h = sum(
        1 for e in events if ensure_aware(e.observed_at) and ensure_aware(e.observed_at) >= since_24
    )
    events_30d = sum(
        1 for e in events if ensure_aware(e.observed_at) and ensure_aware(e.observed_at) >= since_30
    )
    last_event_at = None
    if events:
        last_event_at = max(
            (ensure_aware(e.observed_at) for e in events if e.observed_at), default=None
        )

    signals = db.scalars(
        select(CandidateSignal)
        .join(AccountEvent, CandidateSignal.account_event_id == AccountEvent.id)
        .where(AccountEvent.account_id == acc.id)
    ).all()
    sig_30 = [
        s
        for s in signals
        if ensure_aware(s.created_at) and ensure_aware(s.created_at) >= since_30
    ]
    return AccountStatsOut(
        account_id=acc.id,
        events_24h=events_24h,
        events_30d=events_30d,
        candidate_signals_30d=len(sig_30),
        accepted_signals_30d=sum(1 for s in sig_30 if s.state == "ACCEPTED"),
        rejected_signals_30d=sum(1 for s in sig_30 if s.state == "REJECTED"),
        open_signals=sum(1 for s in signals if s.state == "OPEN"),
        last_event_at=last_event_at,
    )


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


# --- Phase 3: X ingest + candidate engine ---


def _signal_out(db: Session, signal: CandidateSignal) -> CandidateSignalOut:
    event = db.get(RawEvent, signal.raw_event_id)
    handle = None
    conflict = None
    if signal.account_event_id:
        ae = db.get(AccountEvent, signal.account_event_id)
        if ae:
            acc = db.get(Account, ae.account_id)
            if acc:
                handle = acc.handle
                conflict = acc.conflict_risk
    preview = None
    url = None
    if event:
        preview = (event.raw_text or event.title or "")[:160]
        url = event.canonical_url
    suggested: list[int] = []
    if signal.state == "OPEN":
        for h in db.scalars(select(HypeCandidate)).all():
            if normalize_candidate_text(h.canonical_name) == signal.normalized_text:
                suggested.append(h.id)
        for alias in db.scalars(
            select(HypeAlias).where(HypeAlias.normalized_alias == signal.normalized_text)
        ).all():
            if alias.hype_id not in suggested:
                suggested.append(alias.hype_id)
    return CandidateSignalOut(
        id=signal.id,
        raw_event_id=signal.raw_event_id,
        account_event_id=signal.account_event_id,
        signal_type=signal.signal_type,
        candidate_text=signal.candidate_text,
        normalized_text=signal.normalized_text,
        extraction_method=signal.extraction_method,
        source_role=signal.source_role,
        trigger_reason=signal.trigger_reason,
        initial_priority=signal.initial_priority,
        state=signal.state,
        linked_hype_id=signal.linked_hype_id,
        merged_into_signal_id=signal.merged_into_signal_id,
        created_at=signal.created_at,
        reviewed_at=signal.reviewed_at,
        review_note=signal.review_note,
        account_handle=handle,
        conflict_risk=conflict,
        post_preview=preview,
        source_url=url,
        suggested_hype_ids=suggested,
    )


def _hype_detail(db: Session, hype: HypeCandidate) -> HypeCandidateDetailOut:
    aliases = list(
        db.scalars(select(HypeAlias).where(HypeAlias.hype_id == hype.id).order_by(HypeAlias.id)).all()
    )
    origin_account = None
    initial_trigger = None
    sig = db.scalar(
        select(CandidateSignal)
        .where(CandidateSignal.linked_hype_id == hype.id)
        .order_by(CandidateSignal.id.asc())
        .limit(1)
    )
    if sig:
        initial_trigger = sig.signal_type
        if sig.account_event_id:
            ae = db.get(AccountEvent, sig.account_event_id)
            if ae:
                acc = db.get(Account, ae.account_id)
                if acc:
                    origin_account = acc.handle

    last_snap = db.scalar(
        select(CandidateSnapshot)
        .where(CandidateSnapshot.hype_id == hype.id)
        .order_by(CandidateSnapshot.snapshot_at.desc())
        .limit(1)
    )
    next_sched = db.scalar(
        select(CandidateSnapshotSchedule)
        .where(
            CandidateSnapshotSchedule.hype_id == hype.id,
            CandidateSnapshotSchedule.status.in_(["PENDING", "FAILED"]),
        )
        .order_by(CandidateSnapshotSchedule.due_at.asc())
        .limit(1)
    )
    meta = (last_snap.metadata_json if last_snap else None) or {}
    return HypeCandidateDetailOut(
        id=hype.id,
        canonical_name=hype.canonical_name,
        plain_english=hype.plain_english,
        hype_unit_type=hype.hype_unit_type,
        formation_pattern=hype.formation_pattern,
        first_known_use_t0=hype.first_known_use_t0,
        event_occurrence_t0=hype.event_occurrence_t0,
        public_disclosure_t0=hype.public_disclosure_t0,
        breakout_origin_t0=hype.breakout_origin_t0,
        category_adoption_t0=hype.category_adoption_t0,
        reactivation_t0=hype.reactivation_t0,
        candidate_status=hype.candidate_status,
        created_at=hype.created_at,
        last_activity_at=hype.last_activity_at,
        updated_at=hype.updated_at,
        aliases=[HypeAliasOut.model_validate(a) for a in aliases],
        origin_account=origin_account,
        initial_trigger=initial_trigger,
        independent_accounts=last_snap.independent_account_count if last_snap else None,
        platforms=last_snap.platform_count if last_snap else None,
        github_repos=meta.get("github_repo_count_post_t0", meta.get("github_repo_count")),
        hf_spaces=meta.get("hf_space_count_post_t0", meta.get("hf_space_count")),
        hn_stories=meta.get("hn_matching_story_count"),
        last_snapshot_at=last_snap.snapshot_at if last_snap else None,
        next_checkpoint=next_sched.checkpoint if next_sched else None,
        next_checkpoint_due_at=next_sched.due_at if next_sched else None,
        github_repos_preexisting=meta.get("github_repo_count_preexisting"),
        hf_spaces_preexisting=meta.get("hf_space_count_preexisting"),
        total_monitored_accounts=meta.get("total_monitored_account_count"),
    )


@router.post("/x/manual-ingest", response_model=ManualXIngestOut)
def post_manual_x_ingest(body: ManualXIngestIn, db: Session = Depends(get_db)) -> ManualXIngestOut:
    try:
        result = manual_ingest(
            db,
            url=body.url,
            handle=body.handle,
            text=body.text,
            posted_at=body.posted_at,
            post_type=body.post_type,
            parent_url=body.parent_url,
            quoted_url=body.quoted_url,
            visible_metrics=body.visible_metrics.model_dump(exclude_none=True)
            if body.visible_metrics
            else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ManualXIngestOut(
        raw_event_id=result.raw_event_id,
        account_id=result.account_id,
        account_event_id=result.account_event_id,
        known_account=result.known_account,
        created_raw=result.created_raw,
        candidate_signal_ids=result.candidate_signal_ids,
        suggested_hype_ids=result.suggested_hype_ids,
        candidate_signals_extracted=len(result.candidate_signal_ids),
    )


@router.get("/candidate-signals", response_model=list[CandidateSignalOut])
def list_candidate_signals(
    state: Optional[str] = "OPEN",
    signal_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[CandidateSignalOut]:
    stmt = select(CandidateSignal)
    if state:
        stmt = stmt.where(CandidateSignal.state == state)
    if signal_type:
        stmt = stmt.where(CandidateSignal.signal_type == signal_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                CandidateSignal.candidate_text.ilike(like),
                CandidateSignal.normalized_text.ilike(like),
            )
        )
    rows = db.scalars(
        stmt.order_by(CandidateSignal.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [_signal_out(db, s) for s in rows]


@router.post("/candidate-signals/{signal_id}/accept", response_model=HypeCandidateDetailOut)
def accept_signal(
    signal_id: int, body: AcceptSignalIn | None = None, db: Session = Depends(get_db)
) -> HypeCandidateDetailOut:
    body = body or AcceptSignalIn()
    try:
        hype = accept_as_new_hype(
            db,
            signal_id,
            plain_english=body.plain_english,
            hype_unit_type=body.hype_unit_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _hype_detail(db, hype)


@router.post("/candidate-signals/{signal_id}/attach", response_model=CandidateSignalOut)
def attach_signal(
    signal_id: int, body: AttachSignalIn, db: Session = Depends(get_db)
) -> CandidateSignalOut:
    try:
        signal = attach_to_hype(db, signal_id, body.hype_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _signal_out(db, signal)


@router.post("/candidate-signals/{signal_id}/reject", response_model=CandidateSignalOut)
def reject_signal_route(
    signal_id: int, body: RejectSignalIn | None = None, db: Session = Depends(get_db)
) -> CandidateSignalOut:
    body = body or RejectSignalIn()
    try:
        signal = reject_signal(db, signal_id, reason=body.reason, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _signal_out(db, signal)


@router.post("/candidate-signals/{signal_id}/merge", response_model=CandidateSignalOut)
def merge_signal_route(
    signal_id: int, body: MergeSignalIn, db: Session = Depends(get_db)
) -> CandidateSignalOut:
    try:
        signal = merge_signal(db, signal_id, body.into_signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _signal_out(db, signal)


@router.get("/hype-candidates", response_model=list[HypeCandidateDetailOut])
def get_hype_candidates(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[HypeCandidateDetailOut]:
    stmt = select(HypeCandidate)
    if status:
        stmt = stmt.where(HypeCandidate.candidate_status == status)
    rows = db.scalars(stmt.order_by(HypeCandidate.id.desc()).limit(limit)).all()
    return [_hype_detail(db, h) for h in rows]


@router.get("/hype-candidates/{hype_id}", response_model=HypeCandidateDetailOut)
def get_hype_candidate(hype_id: int, db: Session = Depends(get_db)) -> HypeCandidateDetailOut:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise HTTPException(status_code=404, detail="Hype candidate not found")
    return _hype_detail(db, hype)


@router.patch("/hype-candidates/{hype_id}", response_model=HypeCandidateDetailOut)
def patch_hype_candidate(
    hype_id: int, body: HypeCandidatePatchIn, db: Session = Depends(get_db)
) -> HypeCandidateDetailOut:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise HTTPException(status_code=404, detail="Hype candidate not found")
    if body.plain_english is not None:
        hype.plain_english = body.plain_english
    if body.candidate_status is not None:
        hype.candidate_status = body.candidate_status
    if body.hype_unit_type is not None:
        hype.hype_unit_type = body.hype_unit_type
    hype.updated_at = utcnow()
    hype.last_activity_at = utcnow()
    db.commit()
    db.refresh(hype)
    return _hype_detail(db, hype)


@router.post("/hype-candidates/{hype_id}/aliases", response_model=HypeAliasOut)
def post_hype_alias(
    hype_id: int, body: HypeAliasIn, db: Session = Depends(get_db)
) -> HypeAliasOut:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise HTTPException(status_code=404, detail="Hype candidate not found")
    alias = add_alias(db, hype_id, body.alias, alias_type=body.alias_type or "manual")
    hype.updated_at = utcnow()
    db.commit()
    db.refresh(alias)
    return HypeAliasOut.model_validate(alias)


@router.get("/hype-candidates/{hype_id}/timeline", response_model=list[TimelineItemOut])
def get_hype_timeline(hype_id: int, db: Session = Depends(get_db)) -> list[TimelineItemOut]:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise HTTPException(status_code=404, detail="Hype candidate not found")
    items: list[TimelineItemOut] = []
    items.append(
        TimelineItemOut(
            kind="hype_created",
            at=hype.created_at,
            title=f"Hype candidate created: {hype.canonical_name}",
            detail=hype.candidate_status,
            ref_id=hype.id,
        )
    )
    for sig in db.scalars(
        select(CandidateSignal).where(CandidateSignal.linked_hype_id == hype_id)
    ).all():
        items.append(
            TimelineItemOut(
                kind="signal",
                at=sig.created_at,
                title=f"{sig.signal_type}: {sig.candidate_text}",
                detail=sig.state,
                ref_id=sig.id,
            )
        )
        event = db.get(RawEvent, sig.raw_event_id)
        if event:
            items.append(
                TimelineItemOut(
                    kind="raw_event",
                    at=event.published_at or event.retrieved_at,
                    title=event.title or (event.raw_text or "")[:80],
                    detail=event.canonical_url,
                    ref_id=event.id,
                )
            )
    for snap in db.scalars(
        select(CandidateSnapshot).where(CandidateSnapshot.hype_id == hype_id)
    ).all():
        items.append(
            TimelineItemOut(
                kind="snapshot",
                at=snap.snapshot_at,
                title=f"Snapshot {snap.checkpoint or ''}".strip(),
                detail=f"platforms={snap.platform_count} mentions={snap.mention_count}",
                ref_id=snap.id,
            )
        )
    items.sort(key=lambda x: ensure_aware(x.at) or utcnow())
    return items


@router.get("/hype-candidates/{hype_id}/snapshots", response_model=list[CandidateSnapshotOut])
def get_hype_snapshots(hype_id: int, db: Session = Depends(get_db)) -> list[CandidateSnapshotOut]:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise HTTPException(status_code=404, detail="Hype candidate not found")
    rows = db.scalars(
        select(CandidateSnapshot)
        .where(CandidateSnapshot.hype_id == hype_id)
        .order_by(CandidateSnapshot.snapshot_at.asc())
    ).all()
    return [CandidateSnapshotOut.model_validate(r) for r in rows]


@router.get("/hype-candidates/{hype_id}/schedule", response_model=list[SnapshotScheduleOut])
def get_hype_schedule(hype_id: int, db: Session = Depends(get_db)) -> list[SnapshotScheduleOut]:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise HTTPException(status_code=404, detail="Hype candidate not found")
    rows = db.scalars(
        select(CandidateSnapshotSchedule)
        .where(CandidateSnapshotSchedule.hype_id == hype_id)
        .order_by(CandidateSnapshotSchedule.due_at.asc())
    ).all()
    out: list[SnapshotScheduleOut] = []
    for row in rows:
        snap = db.scalar(
            select(CandidateSnapshot).where(
                CandidateSnapshot.hype_id == hype_id,
                CandidateSnapshot.checkpoint == row.checkpoint,
            )
        )
        meta = (snap.metadata_json if snap else None) or {}
        out.append(
            SnapshotScheduleOut(
                id=row.id,
                hype_id=row.hype_id,
                checkpoint=row.checkpoint,
                due_at=row.due_at,
                completed_at=row.completed_at,
                status=row.status,
                attempts=row.attempts,
                last_error=row.last_error,
                skip_reason=row.skip_reason,
                created_at=row.created_at,
                updated_at=row.updated_at,
                snapshot_at=snap.snapshot_at if snap else None,
                late_by_seconds=meta.get("late_by_seconds"),
                timing_quality=meta.get("timing_quality"),
                scheduled_due_at=meta.get("scheduled_due_at"),
            )
        )
    return out


@router.post("/events/{event_id}/promote", response_model=CandidateSignalOut)
def promote_event(
    event_id: int, body: PromoteEventIn, db: Session = Depends(get_db)
) -> CandidateSignalOut:
    try:
        signal = promote_raw_event(
            db,
            event_id,
            candidate_name=body.candidate_name,
            unit_type=body.unit_type,
            phrase_or_object=body.phrase_or_object,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _signal_out(db, signal)


@router.post("/system/process-candidate-snapshots")
async def process_snapshots_now(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.candidate_snapshots import process_due_candidate_snapshots

    n = await process_due_candidate_snapshots(db, limit=limit)
    return {"processed": n}
