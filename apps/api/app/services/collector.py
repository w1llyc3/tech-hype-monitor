from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import NormalizedRawEvent, get_adapter_for_source
from app.core.logging import get_collector_logger
from app.core.timeutil import utcnow
from app.db.models import RawEvent, Source

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


def _find_existing(db: Session, event: NormalizedRawEvent) -> RawEvent | None:
    if event.external_id:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.platform == event.platform,
                RawEvent.external_id == event.external_id,
            )
        )
        if found:
            return found
    if event.canonical_url and event.content_hash:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.canonical_url == event.canonical_url,
                RawEvent.content_hash == event.content_hash,
            )
        )
        if found:
            return found
    # Fallback: same platform + url without external id
    if event.canonical_url and not event.external_id:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.platform == event.platform,
                RawEvent.canonical_url == event.canonical_url,
                RawEvent.external_id.is_(None),
            )
        )
        if found:
            return found
    return None


def persist_events(db: Session, source: Source, events: list[NormalizedRawEvent]) -> tuple[int, int, int]:
    inserted = duplicates = updated = 0
    now = utcnow()
    for event in events:
        existing = _find_existing(db, event)
        if existing:
            duplicates += 1
            # Update HN score/comment metadata for recently seen stories.
            if event.metadata and existing.platform == "hn":
                meta = dict(existing.metadata_json or {})
                changed = False
                for key in ("score", "descendants"):
                    if key in event.metadata and meta.get(key) != event.metadata.get(key):
                        meta[key] = event.metadata.get(key)
                        changed = True
                if changed:
                    existing.metadata_json = meta
                    existing.retrieved_at = now
                    updated += 1
            continue

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
            raise NotImplementedError(f"{adapter.name} is disabled/stub in Phase 1")

        events = await adapter.fetch(source)
        result.fetched = len(events)
        inserted, duplicates, updated = persist_events(db, source, events)
        result.inserted = inserted
        result.duplicates = duplicates
        result.updated = updated

        pending_cursor = getattr(source, "_pending_cursor", None)
        if pending_cursor is not None:
            source.cursor_json = pending_cursor
            if hasattr(source, "_pending_cursor"):
                delattr(source, "_pending_cursor")

        now = utcnow()
        source.last_success_at = now
        source.last_error = None
        source.updated_at = now
        db.commit()
    except Exception as exc:  # noqa: BLE001 — isolate adapter failures
        db.rollback()
        # Re-load source after rollback
        source = db.get(Source, result.source_id) or source
        now = utcnow()
        source.last_error_at = now
        source.last_error = str(exc)[:2000]
        source.updated_at = now
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
            # Run both feeds for the single HN source row.
            results.append(await poll_source(db, source, feed="newstories"))
            db.refresh(source)
            results.append(await poll_source(db, source, feed="topstories"))
        else:
            results.append(await poll_source(db, source))
            db.refresh(source)
    return results
