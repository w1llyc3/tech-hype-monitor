from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import NormalizedRawEvent, get_adapter_for_source
from app.core.logging import get_collector_logger
from app.core.timeutil import utcnow
from app.db.models import RawEvent, Source
from app.services.metrics import mark_hn_left_top_n, record_metrics, upsert_tracked_entity

log = get_collector_logger()


@dataclass
class PollResult:
    source_id: int
    source_name: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    updated: int = 0
    error: str | None = None
    duration_ms: int = 0


def _find_existing(db: Session, source: Source, event: NormalizedRawEvent) -> RawEvent | None:
    """Dedupe within a single source (source-aware)."""
    if event.external_id:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.source_id == source.id,
                RawEvent.external_id == event.external_id,
            )
        )
        if found:
            return found
    if event.canonical_url and event.content_hash:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.source_id == source.id,
                RawEvent.canonical_url == event.canonical_url,
                RawEvent.content_hash == event.content_hash,
            )
        )
        if found:
            return found
    if event.canonical_url and not event.external_id:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.source_id == source.id,
                RawEvent.canonical_url == event.canonical_url,
                RawEvent.external_id.is_(None),
            )
        )
        if found:
            return found
    return None


def _merge_hn_raw_metadata(existing_meta: dict, incoming: dict) -> dict:
    meta = dict(existing_meta or {})
    for key in ("score", "descendants", "hn_id", "type", "latest_top_rank", "rank"):
        if key in incoming and incoming[key] is not None:
            meta[key] = incoming[key]
    feeds = list(meta.get("feeds_seen") or [])
    for f in incoming.get("feeds_seen") or []:
        if f not in feeds:
            feeds.append(f)
    if feeds:
        meta["feeds_seen"] = feeds
    # Never store exclusive `feed` that would erase membership.
    meta.pop("feed", None)
    return meta


def _record_github_entity_metrics(
    db: Session, source: Source, event: NormalizedRawEvent
) -> None:
    meta = dict(event.metadata or {})
    entity = upsert_tracked_entity(
        db,
        platform="github",
        entity_type="github_repo",
        external_id=str(event.external_id),
        canonical_url=event.canonical_url,
        display_name=event.title,
        source_id=source.id,
        metadata=meta,
        merge_metadata=True,
    )
    metrics = {
        "stars": float(meta["stars"]) if meta.get("stars") is not None else None,
        "forks": float(meta["forks"]) if meta.get("forks") is not None else None,
        "watchers": float(meta["watchers"]) if meta.get("watchers") is not None else None,
        "open_issues": float(meta["open_issues"]) if meta.get("open_issues") is not None else None,
    }
    record_metrics(db, entity, metrics)


def _record_hf_entity_metrics(db: Session, source: Source, event: NormalizedRawEvent) -> None:
    meta = dict(event.metadata or {})
    entity_type = event.event_type or "hf_model"
    entity = upsert_tracked_entity(
        db,
        platform="huggingface",
        entity_type=entity_type,
        external_id=str(event.external_id),
        canonical_url=event.canonical_url,
        display_name=event.title,
        source_id=source.id,
        metadata=meta,
        merge_metadata=True,
    )
    metrics: dict[str, float | None] = {
        "likes": float(meta["likes"]) if meta.get("likes") is not None else None,
    }
    if entity_type in {"hf_model", "hf_dataset"}:
        # Preserve NULL downloads; do not coerce missing to 0.
        metrics["downloads"] = (
            float(meta["downloads"]) if meta.get("downloads") is not None else None
        )
    record_metrics(db, entity, metrics)


def _record_hn_entity_metrics(
    db: Session, source: Source, event: NormalizedRawEvent, feed: str | None
) -> None:
    if not event.external_id:
        return
    meta_in = dict(event.metadata or {})
    entity_meta = {
        "feeds_seen": meta_in.get("feeds_seen") or ([feed] if feed else []),
    }
    if "latest_top_rank" in meta_in:
        entity_meta["latest_top_rank"] = meta_in["latest_top_rank"]
    entity = upsert_tracked_entity(
        db,
        platform="hn",
        entity_type="hn_story",
        external_id=str(event.external_id),
        canonical_url=event.canonical_url
        or f"https://news.ycombinator.com/item?id={event.external_id}",
        display_name=event.title,
        source_id=source.id,
        metadata=entity_meta,
        merge_metadata=True,
    )
    metrics: dict[str, float | None] = {
        "score": float(meta_in["score"]) if meta_in.get("score") is not None else None,
        "comments": float(meta_in["descendants"])
        if meta_in.get("descendants") is not None
        else None,
    }
    # Only write rank for topstories observations.
    if feed == "topstories" and meta_in.get("rank") is not None:
        metrics["rank"] = float(meta_in["rank"])
    record_metrics(db, entity, metrics)


def persist_events(
    db: Session,
    source: Source,
    events: list[NormalizedRawEvent],
    *,
    feed: str | None = None,
) -> tuple[int, int, int]:
    inserted = duplicates = updated = 0
    now = utcnow()
    top_ids: set[str] = set()
    for event in events:
        existing = _find_existing(db, source, event)
        if existing:
            duplicates += 1
            if event.metadata and existing.platform == "hn":
                new_meta = _merge_hn_raw_metadata(existing.metadata_json or {}, event.metadata)
                if new_meta != (existing.metadata_json or {}):
                    existing.metadata_json = new_meta
                    existing.retrieved_at = now
                    updated += 1
            elif event.metadata and existing.platform in {"github", "huggingface"}:
                meta = dict(existing.metadata_json or {})
                meta.update(event.metadata)
                if meta != (existing.metadata_json or {}):
                    existing.metadata_json = meta
                    existing.retrieved_at = now
                    updated += 1
        else:
            db.add(
                RawEvent(
                    source_id=source.id,
                    platform=event.platform,
                    external_id=event.external_id,
                    author=event.author,
                    published_at=event.published_at,
                    retrieved_at=now,
                    canonical_url=event.canonical_url,
                    title=event.title,
                    raw_text=event.raw_text,
                    content_hash=event.content_hash,
                    event_type=event.event_type,
                    metadata_json=event.metadata or None,
                    created_at=now,
                )
            )
            inserted += 1

        if event.platform == "hn":
            _record_hn_entity_metrics(db, source, event, feed)
            if feed == "topstories" and event.external_id:
                top_ids.add(str(event.external_id))
        elif event.platform == "github" and event.external_id:
            _record_github_entity_metrics(db, source, event)
        elif event.platform == "huggingface" and event.external_id:
            _record_hf_entity_metrics(db, source, event)

    if feed == "topstories" and source.source_type in {"hacker_news", "hn"}:
        mark_hn_left_top_n(db, top_ids)

    return inserted, duplicates, updated


async def poll_source(db: Session, source: Source, feed: str | None = None) -> PollResult:
    start = time.perf_counter()
    result = PollResult(source_id=source.id, source_name=source.name)
    log.info(
        "poll start source=%s id=%s feed=%s",
        source.name,
        source.id,
        feed,
    )
    try:
        adapter = get_adapter_for_source(source, feed=feed)
        if not adapter.is_enabled():
            raise NotImplementedError(f"{adapter.name} is disabled/stub")

        events = await adapter.fetch(source)
        result.fetched = len(events)
        inserted, duplicates, updated = persist_events(db, source, events, feed=feed)
        result.inserted = inserted
        result.duplicates = duplicates
        result.updated = updated

        pending_cursor = getattr(source, "_pending_cursor", None)
        if pending_cursor is not None:
            # Merge into existing cursor_json to preserve rate_limit runtime etc.
            current = dict(source.cursor_json or {})
            if isinstance(pending_cursor, dict):
                for k, v in pending_cursor.items():
                    if k == "runtime" and isinstance(v, dict):
                        runtime = dict(current.get("runtime") or {})
                        runtime.update(v)
                        current["runtime"] = runtime
                    else:
                        current[k] = v
            source.cursor_json = current
            if hasattr(source, "_pending_cursor"):
                delattr(source, "_pending_cursor")

        now = utcnow()
        source.last_success_at = now
        source.last_error = None
        source.updated_at = now
        db.commit()
    except Exception as exc:  # noqa: BLE001 — isolate adapter failures
        db.rollback()
        source = db.get(Source, result.source_id) or source
        now = utcnow()
        source.last_error_at = now
        source.last_error = str(exc)[:2000]
        source.updated_at = now
        # Capture rate-limit cursor updates if adapter attached them before raise.
        pending_cursor = getattr(source, "_pending_cursor", None)
        if pending_cursor is not None:
            current = dict(source.cursor_json or {})
            if isinstance(pending_cursor, dict):
                runtime = dict(current.get("runtime") or {})
                runtime.update(pending_cursor.get("runtime") or {})
                current["runtime"] = runtime
            source.cursor_json = current
        db.commit()
        result.error = str(exc) or repr(exc)
        log.exception(
            "poll error source=%s error=%s",
            source.name,
            result.error,
        )

    result.duration_ms = int((time.perf_counter() - start) * 1000)
    log.info(
        "poll finish source=%s fetched=%s inserted=%s duplicates=%s updated=%s error=%s duration_ms=%s",
        result.source_name,
        result.fetched,
        result.inserted,
        result.duplicates,
        result.updated,
        result.error,
        result.duration_ms,
    )
    return result


async def poll_all_enabled(db: Session) -> list[PollResult]:
    sources = db.scalars(select(Source).where(Source.enabled.is_(True))).all()
    results: list[PollResult] = []
    for source in sources:
        st = (source.source_type or "").lower()
        if st in {"hacker_news", "hn"}:
            results.append(await poll_source(db, source, feed="newstories"))
            db.refresh(source)
            results.append(await poll_source(db, source, feed="topstories"))
        else:
            results.append(await poll_source(db, source))
            db.refresh(source)
    return results
