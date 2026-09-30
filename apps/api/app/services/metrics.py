"""Historical metric observation layer with controlled write volume."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import ensure_aware, utcnow
from app.db.models import MetricObservation, TrackedEntity

HEARTBEAT_SECONDS = 60 * 60


def upsert_tracked_entity(
    db: Session,
    *,
    platform: str,
    entity_type: str,
    external_id: str,
    canonical_url: str | None = None,
    display_name: str | None = None,
    source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    merge_metadata: bool = True,
) -> TrackedEntity:
    now = utcnow()
    entity = db.scalar(
        select(TrackedEntity).where(
            TrackedEntity.platform == platform,
            TrackedEntity.entity_type == entity_type,
            TrackedEntity.external_id == external_id,
        )
    )
    if entity is None:
        entity = TrackedEntity(
            source_id=source_id,
            platform=platform,
            entity_type=entity_type,
            external_id=external_id,
            canonical_url=canonical_url,
            display_name=display_name,
            first_seen_at=now,
            last_seen_at=now,
            metadata_json=metadata or None,
            created_at=now,
            updated_at=now,
        )
        db.add(entity)
        db.flush()
        return entity

    entity.last_seen_at = now
    entity.updated_at = now
    if source_id is not None:
        entity.source_id = source_id
    if canonical_url:
        entity.canonical_url = canonical_url
    if display_name:
        entity.display_name = display_name
    if metadata:
        if merge_metadata and entity.metadata_json:
            merged = dict(entity.metadata_json)
            for k, v in metadata.items():
                if k == "feeds_seen" and isinstance(v, list):
                    prev = merged.get("feeds_seen") or []
                    if not isinstance(prev, list):
                        prev = []
                    merged["feeds_seen"] = list(dict.fromkeys([*prev, *v]))
                else:
                    merged[k] = v
            entity.metadata_json = merged
        else:
            entity.metadata_json = metadata
    db.flush()
    return entity


def _latest_observation(
    db: Session, entity_id: int, metric_name: str
) -> MetricObservation | None:
    return db.scalar(
        select(MetricObservation)
        .where(
            MetricObservation.tracked_entity_id == entity_id,
            MetricObservation.metric_name == metric_name,
        )
        .order_by(MetricObservation.observed_at.desc(), MetricObservation.id.desc())
        .limit(1)
    )


def _values_equal(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return float(a) == float(b)


def record_metric(
    db: Session,
    entity: TrackedEntity,
    *,
    metric_name: str,
    metric_value: float | None = None,
    metric_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
    heartbeat_seconds: int = HEARTBEAT_SECONDS,
) -> MetricObservation | None:
    """Write observation on first/change/heartbeat. Returns row if written."""
    now = utcnow()
    latest = _latest_observation(db, entity.id, metric_name)
    should_write = False
    meta = dict(metadata or {})

    if latest is None:
        should_write = True
        meta.setdefault("reason", "first")
    elif force:
        should_write = True
        meta.setdefault("reason", "forced")
    elif not _values_equal(latest.metric_value, metric_value):
        should_write = True
        meta.setdefault("reason", "changed")
    else:
        last_at = ensure_aware(latest.observed_at)
        if last_at is None or (now - last_at).total_seconds() >= heartbeat_seconds:
            should_write = True
            meta.setdefault("reason", "heartbeat")

    if not should_write:
        return None

    obs = MetricObservation(
        tracked_entity_id=entity.id,
        observed_at=now,
        metric_name=metric_name,
        metric_value=metric_value,
        metric_text=metric_text,
        metadata_json=meta or None,
        created_at=now,
    )
    db.add(obs)
    db.flush()
    return obs


def record_metrics(
    db: Session,
    entity: TrackedEntity,
    metrics: dict[str, float | None],
    *,
    metadata: dict[str, Any] | None = None,
) -> list[MetricObservation]:
    written: list[MetricObservation] = []
    for name, value in metrics.items():
        row = record_metric(
            db,
            entity,
            metric_name=name,
            metric_value=value,
            metadata=metadata,
        )
        if row:
            written.append(row)
    return written


def mark_hn_left_top_n(db: Session, current_top_external_ids: set[str]) -> int:
    """For tracked HN stories previously ranked, write one null rank when leaving top-N."""
    now = utcnow()
    entities = db.scalars(
        select(TrackedEntity).where(
            TrackedEntity.platform == "hn",
            TrackedEntity.entity_type == "hn_story",
        )
    ).all()
    written = 0
    for entity in entities:
        if entity.external_id in current_top_external_ids:
            continue
        latest = _latest_observation(db, entity.id, "rank")
        if latest is None:
            continue
        if latest.metric_value is None:
            # Already recorded left_top_n (or never ranked); skip repeats.
            meta = latest.metadata_json or {}
            if meta.get("state") == "left_top_n":
                continue
            # null without left_top_n — still skip repeats of null
            continue
        record_metric(
            db,
            entity,
            metric_name="rank",
            metric_value=None,
            metadata={"state": "left_top_n", "reason": "left_top_n"},
            force=True,
        )
        written += 1
        # touch last_seen only via observation; entity itself stays
        entity.updated_at = now
    return written


def compute_velocity(
    db: Session,
    entity_id: int,
    metric: str,
    window_hours: int = 24,
) -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(hours=window_hours)
    rows = list(
        db.scalars(
            select(MetricObservation)
            .where(
                MetricObservation.tracked_entity_id == entity_id,
                MetricObservation.metric_name == metric,
                MetricObservation.observed_at >= since,
            )
            .order_by(MetricObservation.observed_at.asc(), MetricObservation.id.asc())
        ).all()
    )
    # Also include the last observation before window as start anchor if present.
    before = db.scalar(
        select(MetricObservation)
        .where(
            MetricObservation.tracked_entity_id == entity_id,
            MetricObservation.metric_name == metric,
            MetricObservation.observed_at < since,
        )
        .order_by(MetricObservation.observed_at.desc(), MetricObservation.id.desc())
        .limit(1)
    )
    series = ([before] if before else []) + rows
    usable = [r for r in series if r.metric_value is not None]
    if len(usable) < 2:
        return {
            "metric": metric,
            "window_hours": window_hours,
            "start_value": None,
            "end_value": None,
            "delta": None,
            "delta_per_hour": None,
        }
    start = usable[0]
    end = usable[-1]
    start_v = float(start.metric_value)  # type: ignore[arg-type]
    end_v = float(end.metric_value)  # type: ignore[arg-type]
    delta = end_v - start_v
    t0 = ensure_aware(start.observed_at)
    t1 = ensure_aware(end.observed_at)
    hours = max((t1 - t0).total_seconds() / 3600.0, 1e-9) if t0 and t1 else None
    return {
        "metric": metric,
        "window_hours": window_hours,
        "start_value": start_v,
        "end_value": end_v,
        "delta": delta,
        "delta_per_hour": (delta / hours) if hours else None,
    }
