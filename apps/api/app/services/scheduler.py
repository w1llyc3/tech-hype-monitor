from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.timeutil import ensure_aware, utcnow
from app.db.models import Source
from app.db.session import SessionLocal
from app.services.collector import poll_source

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def last_activity_at(source: Source):
    """Most recent of last_success_at / last_error_at (aware UTC)."""
    success = ensure_aware(source.last_success_at)
    error = ensure_aware(source.last_error_at)
    stamped = [t for t in (success, error) if t is not None]
    return max(stamped) if stamped else None


async def poll_hn_feed(feed: str) -> None:
    with SessionLocal() as db:
        source = db.scalar(
            select(Source).where(
                Source.enabled.is_(True),
                Source.source_type.in_(["hacker_news", "hn"]),
            )
        )
        if not source:
            return
        await poll_source(db, source, feed=feed)


async def poll_rss_due() -> None:
    with SessionLocal() as db:
        sources = db.scalars(
            select(Source).where(
                Source.enabled.is_(True),
                Source.source_type.in_(["official_rss", "rss"]),
            )
        ).all()
        now = utcnow()
        for source in sources:
            interval = source.poll_interval_seconds or settings.rss_default_interval_seconds
            last = last_activity_at(source)
            if last and (now - last).total_seconds() < interval:
                continue
            try:
                await poll_source(db, source)
            except Exception:  # noqa: BLE001
                log.exception("RSS scheduled poll failed for %s", source.name)
            db.refresh(source)


async def poll_watch_sources() -> None:
    """Poll enabled GitHub / Hugging Face watch sources (low frequency)."""
    with SessionLocal() as db:
        sources = db.scalars(
            select(Source).where(
                Source.enabled.is_(True),
                Source.source_type.in_(
                    [
                        "github_org",
                        "github_repo",
                        "hf_org_models",
                        "hf_org_datasets",
                        "hf_org_spaces",
                    ]
                ),
            )
        ).all()
        now = utcnow()
        for source in sources:
            interval = source.poll_interval_seconds or 3600
            last = last_activity_at(source)
            if last and (now - last).total_seconds() < interval:
                continue
            if source.platform == "github":
                runtime = ((source.cursor_json or {}).get("runtime")) or {}
                remaining = runtime.get("rate_limit_remaining")
                if isinstance(remaining, int) and remaining < 10:
                    log.warning(
                        "Skipping %s due to low GitHub rate limit (%s)",
                        source.name,
                        remaining,
                    )
                    continue
            try:
                await poll_source(db, source)
            except Exception:  # noqa: BLE001
                log.exception("Watch source poll failed for %s", source.name)
            db.refresh(source)


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        log.info("Scheduler disabled")
        return
    if scheduler.running:
        return

    scheduler.add_job(
        poll_hn_feed,
        IntervalTrigger(seconds=settings.hn_newstories_interval_seconds),
        args=["newstories"],
        id="hn_newstories",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        poll_hn_feed,
        IntervalTrigger(seconds=settings.hn_topstories_interval_seconds),
        args=["topstories"],
        id="hn_topstories",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        poll_rss_due,
        IntervalTrigger(seconds=60),
        id="rss_due",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        poll_watch_sources,
        IntervalTrigger(seconds=300),
        id="watch_sources",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        poll_hn_feed,
        DateTrigger(run_date=utcnow()),
        args=["newstories"],
        id="hn_newstories_boot",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_rss_due,
        DateTrigger(run_date=utcnow()),
        id="rss_boot",
        replace_existing=True,
    )
    scheduler.start()
    log.info("Scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
