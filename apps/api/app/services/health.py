from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import ensure_aware, utcnow
from app.db.models import RawEvent, Source


def compute_source_status(source: Source, *, stale_after_seconds: int | None = None) -> str:
    if not source.enabled:
        return "Disabled"

    interval = stale_after_seconds or max(source.poll_interval_seconds * 3, 1800)
    now = utcnow()
    last_success = ensure_aware(source.last_success_at)
    last_error = ensure_aware(source.last_error_at)

    # Error wins only if newer than last success (or no success yet).
    if last_error and (last_success is None or last_error >= last_success):
        return "Error"

    if last_success is None:
        return "Stale"

    age = (now - last_success).total_seconds()
    if age > interval:
        return "Stale"
    return "Healthy"


def events_24h_count(db: Session, source_id: int | None = None) -> int:
    since = utcnow() - timedelta(hours=24)
    stmt = select(func.count(RawEvent.id)).where(RawEvent.retrieved_at >= since)
    if source_id is not None:
        stmt = stmt.where(RawEvent.source_id == source_id)
    return int(db.scalar(stmt) or 0)


def events_24h_by_group(db: Session) -> dict[str, int]:
    since = utcnow() - timedelta(hours=24)
    rows = db.execute(
        select(Source.platform, func.count(RawEvent.id))
        .join(RawEvent, RawEvent.source_id == Source.id)
        .where(RawEvent.retrieved_at >= since)
        .group_by(Source.platform)
    ).all()
    grouped = {"HN": 0, "Official/RSS": 0}
    for platform, count in rows:
        if platform == "hn":
            grouped["HN"] += int(count)
        elif platform in {"official_rss", "rss"}:
            grouped["Official/RSS"] += int(count)
        else:
            grouped[platform] = grouped.get(platform, 0) + int(count)
    return grouped


def list_source_health(db: Session) -> list[dict]:
    sources = db.scalars(select(Source).order_by(Source.id)).all()
    out = []
    for s in sources:
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "platform": s.platform,
                "source_type": s.source_type,
                "enabled": s.enabled,
                "last_success_at": s.last_success_at,
                "last_error_at": s.last_error_at,
                "last_error": s.last_error,
                "events_24h": events_24h_count(db, s.id),
                "status": compute_source_status(s),
            }
        )
    return out


def recent_events(db: Session, limit: int = 30) -> list[RawEvent]:
    return list(
        db.scalars(
            select(RawEvent)
            .options(joinedload(RawEvent.source))
            .order_by(RawEvent.retrieved_at.desc())
            .limit(limit)
        ).unique().all()
    )


def status_counts(db: Session) -> dict[str, int]:
    counts = {"Healthy": 0, "Stale": 0, "Error": 0, "Disabled": 0}
    for s in db.scalars(select(Source)).all():
        counts[compute_source_status(s)] += 1
    return counts
