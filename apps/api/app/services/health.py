from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import ensure_aware, utcnow
from app.db.models import RawEvent, Source, TrackedEntity


def _rate_limit_info(source: Source) -> dict | None:
    runtime = ((source.cursor_json or {}).get("runtime")) or {}
    if not runtime:
        return None
    return {
        "rate_limit_remaining": runtime.get("rate_limit_remaining"),
        "rate_limit_reset_at": runtime.get("rate_limit_reset_at"),
        "rate_limit_limit": runtime.get("rate_limit_limit"),
        "rate_limited": bool(runtime.get("rate_limited")),
    }


def compute_source_status(source: Source, *, stale_after_seconds: int | None = None) -> str:
    if not source.enabled:
        return "Disabled"

    rate = _rate_limit_info(source) or {}
    remaining = rate.get("rate_limit_remaining")
    if rate.get("rate_limited") or (isinstance(remaining, int) and remaining <= 0):
        # Surface rate-limit distinctly from "no new events".
        last_error = (source.last_error or "").lower()
        if "rate limit" in last_error or rate.get("rate_limited") or remaining == 0:
            return "Rate Limited"

    interval = stale_after_seconds or max(source.poll_interval_seconds * 3, 1800)
    now = utcnow()
    last_success = ensure_aware(source.last_success_at)
    last_error = ensure_aware(source.last_error_at)

    if last_error and (last_success is None or last_error >= last_success):
        err = (source.last_error or "").lower()
        if "rate limit" in err:
            return "Rate Limited"
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
    grouped = {"HN": 0, "Official/RSS": 0, "GitHub": 0, "Hugging Face": 0}
    for platform, count in rows:
        if platform == "hn":
            grouped["HN"] += int(count)
        elif platform in {"official_rss", "rss"}:
            grouped["Official/RSS"] += int(count)
        elif platform == "github":
            grouped["GitHub"] += int(count)
        elif platform == "huggingface":
            grouped["Hugging Face"] += int(count)
        else:
            grouped[platform] = grouped.get(platform, 0) + int(count)
    return grouped


def list_source_health(db: Session) -> list[dict]:
    sources = db.scalars(select(Source).order_by(Source.id)).all()
    out = []
    for s in sources:
        rate = _rate_limit_info(s)
        row = {
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
            "rate_limit_remaining": rate.get("rate_limit_remaining") if rate else None,
            "rate_limit_reset_at": rate.get("rate_limit_reset_at") if rate else None,
        }
        out.append(row)
    return out


def recent_events(db: Session, limit: int = 30) -> list[RawEvent]:
    return list(
        db.scalars(
            select(RawEvent)
            .options(joinedload(RawEvent.source))
            .order_by(RawEvent.retrieved_at.desc())
            .limit(limit)
        )
        .unique()
        .all()
    )


def status_counts(db: Session) -> dict[str, int]:
    counts = {"Healthy": 0, "Stale": 0, "Error": 0, "Disabled": 0, "Rate Limited": 0}
    for s in db.scalars(select(Source)).all():
        status = compute_source_status(s)
        counts[status] = counts.get(status, 0) + 1
    return counts


def tracked_entity_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(TrackedEntity.entity_type, func.count(TrackedEntity.id)).group_by(
            TrackedEntity.entity_type
        )
    ).all()
    mapping = {
        "github_repo": "GitHub repos",
        "hf_model": "HF models",
        "hf_space": "HF spaces",
        "hf_dataset": "HF datasets",
        "hn_story": "HN stories",
    }
    out = {label: 0 for label in mapping.values()}
    for entity_type, count in rows:
        label = mapping.get(entity_type, entity_type)
        out[label] = int(count)
    return out


def recent_derivative_activity(db: Session) -> dict[str, int]:
    since = utcnow() - timedelta(hours=24)
    def _count(entity_type: str) -> int:
        return int(
            db.scalar(
                select(func.count(TrackedEntity.id)).where(
                    TrackedEntity.entity_type == entity_type,
                    TrackedEntity.first_seen_at >= since,
                )
            )
            or 0
        )

    return {
        "new GitHub repos discovered": _count("github_repo"),
        "new HF Spaces discovered": _count("hf_space"),
        "new HF models discovered": _count("hf_model"),
    }
