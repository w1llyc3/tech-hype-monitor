"""Confirmation snapshot engine for Hype Candidates."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import ensure_aware, utcnow
from app.db.models import (
    Account,
    AccountEvent,
    CandidateSnapshot,
    CandidateSnapshotSchedule,
    HypeAlias,
    HypeCandidate,
    RawEvent,
)
from app.services.candidate_extraction import normalize_candidate_text
from app.services.discovery import persist_github_discovery, persist_hf_discovery
from app.services.metrics import compute_velocity

log = logging.getLogger(__name__)


def _aliases_for(db: Session, hype: HypeCandidate) -> list[str]:
    aliases = [hype.canonical_name]
    for row in db.scalars(select(HypeAlias).where(HypeAlias.hype_id == hype.id)).all():
        aliases.append(row.alias)
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for a in aliases:
        n = normalize_candidate_text(a)
        if n and n not in seen:
            seen.add(n)
            out.append(a)
    return out


def _text_matches(haystack: str, aliases: list[str]) -> bool:
    if not haystack:
        return False
    low = haystack.lower()
    for a in aliases:
        n = normalize_candidate_text(a)
        if not n:
            continue
        if n in low:
            return True
        # word-ish boundary for short tokens
        if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", low):
            return True
    return False


def _collect_x_account_stats(
    db: Session, hype: HypeCandidate, aliases: list[str]
) -> dict[str, Any]:
    account_events = db.scalars(select(AccountEvent)).all()
    matching_ae: list[AccountEvent] = []
    for ae in account_events:
        blob = " ".join(
            filter(
                None,
                [ae.candidate_phrase, ae.candidate_object],
            )
        )
        raw = db.get(RawEvent, ae.raw_event_id) if ae.raw_event_id else None
        text = " ".join(filter(None, [blob, raw.raw_text if raw else None, raw.title if raw else None]))
        if _text_matches(text or "", aliases):
            matching_ae.append(ae)

    x_events = db.scalars(select(RawEvent).where(RawEvent.platform == "x")).all()
    matching_x = [e for e in x_events if _text_matches((e.raw_text or "") + " " + (e.title or ""), aliases)]

    account_ids = {ae.account_id for ae in matching_ae}
    high_quality = 0
    for aid in account_ids:
        acc = db.get(Account, aid)
        if not acc:
            continue
        if (acc.universe_tier or "").upper() == "CORE" or (acc.monitor_priority or "").upper() == "P0":
            high_quality += 1

    mention_count = len(matching_ae) + len(matching_x)
    return {
        "mention_count": mention_count,
        "independent_account_count": len(account_ids),
        "high_quality_amplifier_count": high_quality,
        "x_raw_match_count": len(matching_x),
        "account_event_match_count": len(matching_ae),
    }


def _collect_hn_stats(db: Session, aliases: list[str]) -> dict[str, Any]:
    events = db.scalars(select(RawEvent).where(RawEvent.platform.in_(["hn", "hacker_news"]))).all()
    matched = []
    total_score = 0
    total_comments = 0
    best_rank: Optional[int] = None
    for e in events:
        text = f"{e.title or ''} {e.raw_text or ''}"
        if not _text_matches(text, aliases):
            continue
        matched.append(e)
        meta = e.metadata_json or {}
        if isinstance(meta.get("score"), (int, float)):
            total_score += int(meta["score"])
        if isinstance(meta.get("descendants"), (int, float)):
            total_comments += int(meta["descendants"])
        rank = meta.get("latest_top_rank") or meta.get("rank")
        if isinstance(rank, int):
            best_rank = rank if best_rank is None else min(best_rank, rank)
    return {
        "hn_matching_story_count": len(matched),
        "hn_total_score": total_score if matched else 0,
        "hn_total_comments": total_comments if matched else 0,
        "best_hn_rank": best_rank,
    }


async def _collect_github_stats(db: Session, aliases: list[str]) -> dict[str, Any]:
    from app.adapters.github import GitHubRateLimitError, search_github_repos

    queries = [normalize_candidate_text(a) for a in aliases[:3]]
    queries = [q for q in queries if q]
    all_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for q in queries:
        try:
            items = await search_github_repos(q, limit=10)
        except GitHubRateLimitError as exc:
            log.warning("GitHub rate limited during snapshot: %s", exc)
            break
        except Exception:  # noqa: BLE001
            log.exception("GitHub search failed for %s", q)
            continue
        for item in items:
            eid = str(item.get("external_id") or "")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                all_items.append(item)
    if all_items:
        persist_github_discovery(db, all_items)

    owners = {i.get("owner") for i in all_items if i.get("owner")}
    total_stars = sum(int(i.get("stars") or 0) for i in all_items)
    max_vel = None
    for i in all_items:
        eid = i.get("entity_id")
        if not eid:
            continue
        try:
            vel = compute_velocity(db, int(eid), "stars", 24)
            d = vel.get("delta")
            if d is None:
                continue
            max_vel = float(d) if max_vel is None else max(max_vel, float(d))
        except Exception:  # noqa: BLE001
            continue
    return {
        "github_repo_count": len(all_items),
        "github_independent_owner_count": len(owners),
        "github_total_stars": total_stars,
        "github_max_star_velocity_24h": max_vel,
    }


def _collect_hf_stats(db: Session, aliases: list[str]) -> dict[str, Any]:
    from app.adapters.huggingface import search_hf

    q = normalize_candidate_text(aliases[0]) if aliases else ""
    models = datasets = spaces = []
    if q:
        try:
            models = search_hf("model", q, limit=10)
            persist_hf_discovery(db, models)
        except Exception:  # noqa: BLE001
            log.exception("HF model search failed")
            models = []
        try:
            spaces = search_hf("space", q, limit=10)
            persist_hf_discovery(db, spaces)
        except Exception:  # noqa: BLE001
            log.exception("HF space search failed")
            spaces = []
        try:
            datasets = search_hf("dataset", q, limit=10)
            persist_hf_discovery(db, datasets)
        except Exception:  # noqa: BLE001
            log.exception("HF dataset search failed")
            datasets = []

    authors: set[str] = set()
    for items in (models, spaces, datasets):
        for i in items:
            if i.get("author"):
                authors.add(str(i["author"]))
    return {
        "hf_model_count": len(models),
        "hf_space_count": len(spaces),
        "hf_dataset_count": len(datasets),
        "hf_independent_author_count": len(authors),
    }


def _collect_rss_stats(db: Session, aliases: list[str]) -> dict[str, Any]:
    events = db.scalars(
        select(RawEvent).where(RawEvent.platform.in_(["official_rss", "rss"]))
    ).all()
    matched = [
        e
        for e in events
        if _text_matches(f"{e.title or ''} {e.raw_text or ''}", aliases)
    ]
    return {"rss_matching_count": len(matched)}


def _source_detachment_level(
    *,
    independent_accounts: int,
    high_quality: int,
    platform_count: int,
) -> str:
    if independent_accounts <= 0 and platform_count <= 1:
        return "NONE"
    if independent_accounts <= 1 and platform_count <= 1:
        return "WEAK"
    if high_quality >= 3 and platform_count >= 3:
        return "STRONG"
    if independent_accounts >= 2 or platform_count >= 2:
        return "EMERGING"
    return "UNKNOWN"


async def run_checkpoint(db: Session, schedule: CandidateSnapshotSchedule) -> CandidateSnapshot:
    now = utcnow()
    hype = db.get(HypeCandidate, schedule.hype_id)
    if not hype:
        raise ValueError("hype candidate missing")

    # Never duplicate a completed checkpoint snapshot
    existing = db.scalar(
        select(CandidateSnapshot).where(
            CandidateSnapshot.hype_id == hype.id,
            CandidateSnapshot.checkpoint == schedule.checkpoint,
        )
    )
    if existing:
        schedule.status = "COMPLETED"
        schedule.completed_at = ensure_aware(existing.snapshot_at) or now
        schedule.updated_at = now
        db.commit()
        return existing

    schedule.status = "RUNNING"
    schedule.attempts = int(schedule.attempts or 0) + 1
    schedule.updated_at = now
    db.commit()

    aliases = _aliases_for(db, hype)
    x_stats = _collect_x_account_stats(db, hype, aliases)
    hn_stats = _collect_hn_stats(db, aliases)
    gh_stats = await _collect_github_stats(db, aliases)
    hf_stats = _collect_hf_stats(db, aliases)
    rss_stats = _collect_rss_stats(db, aliases)

    platforms = []
    if x_stats["mention_count"] > 0:
        platforms.append("X")
    if hn_stats["hn_matching_story_count"] > 0:
        platforms.append("HN")
    if gh_stats["github_repo_count"] > 0:
        platforms.append("GitHub")
    if (hf_stats["hf_model_count"] + hf_stats["hf_space_count"] + hf_stats["hf_dataset_count"]) > 0:
        platforms.append("Hugging Face")
    if rss_stats["rss_matching_count"] > 0:
        platforms.append("Official/RSS")

    detachment = _source_detachment_level(
        independent_accounts=x_stats["independent_account_count"],
        high_quality=x_stats["high_quality_amplifier_count"],
        platform_count=len(platforms),
    )

    meta = {
        **x_stats,
        **hn_stats,
        **gh_stats,
        **hf_stats,
        **rss_stats,
        "platforms_active": platforms,
        "source_detachment_level": detachment,
        "aliases_used": [normalize_candidate_text(a) for a in aliases],
    }

    snap = CandidateSnapshot(
        hype_id=hype.id,
        snapshot_at=now,
        mention_count=x_stats["mention_count"],
        independent_account_count=x_stats["independent_account_count"],
        high_quality_amplifier_count=x_stats["high_quality_amplifier_count"],
        platform_count=len(platforms),
        cross_cluster_count=None,
        dominant_keyword=normalize_candidate_text(hype.canonical_name),
        keyword_variant_count=len(aliases),
        keyword_convergence=None,
        derivative_count=None,
        source_detachment=None,  # categorical lives in metadata
        token_exists=None,
        token_count=None,
        canonical_state=hype.candidate_status,
        checkpoint=schedule.checkpoint,
        metadata_json=meta,
        created_at=now,
    )
    db.add(snap)

    schedule.status = "COMPLETED"
    schedule.completed_at = now
    schedule.last_error = None
    schedule.updated_at = now
    hype.last_activity_at = now
    hype.updated_at = now
    # Suggest WATCHING once any confirmation evidence appears
    if hype.candidate_status == "OPEN" and len(platforms) >= 2:
        hype.candidate_status = "WATCHING"
    db.commit()
    db.refresh(snap)
    return snap


async def process_due_candidate_snapshots(db: Session, limit: int = 10) -> int:
    now = utcnow()
    due = db.scalars(
        select(CandidateSnapshotSchedule)
        .where(
            CandidateSnapshotSchedule.status.in_(["PENDING", "FAILED"]),
            CandidateSnapshotSchedule.due_at <= now,
        )
        .order_by(CandidateSnapshotSchedule.due_at.asc())
        .limit(limit)
    ).all()

    processed = 0
    for row in due:
        try:
            await run_checkpoint(db, row)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("Checkpoint failed for schedule %s", row.id)
            row.status = "FAILED"
            row.last_error = str(exc)[:2000]
            row.updated_at = utcnow()
            db.commit()
    return processed
