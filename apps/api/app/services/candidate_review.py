"""Accept / reject / attach / merge candidate signals; create hype + schedules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import ensure_aware, utcnow
from app.db.models import (
    CandidateSignal,
    CandidateSnapshotSchedule,
    HypeAlias,
    HypeCandidate,
    RawEvent,
)
from app.services.candidate_extraction import normalize_candidate_text

CHECKPOINTS: list[tuple[str, timedelta]] = [
    ("1H", timedelta(hours=1)),
    ("6H", timedelta(hours=6)),
    ("24H", timedelta(hours=24)),
    ("72H", timedelta(hours=72)),
    ("7D", timedelta(days=7)),
    ("30D", timedelta(days=30)),
]

REJECT_REASONS = {
    "NO_INDEPENDENT_ADOPTION",
    "TOO_GENERIC",
    "SOURCE_DEPENDENT",
    "EXTERNAL_BAIT",
    "NOT_A_TECH_OBJECT",
    "PURE_REPOST",
    "ALREADY_MAINSTREAM",
    "OTHER",
}


def create_snapshot_schedule(db: Session, hype: HypeCandidate, t0: datetime) -> list[CandidateSnapshotSchedule]:
    now = utcnow()
    t0 = ensure_aware(t0) or now
    rows: list[CandidateSnapshotSchedule] = []
    for name, delta in CHECKPOINTS:
        existing = db.scalar(
            select(CandidateSnapshotSchedule).where(
                CandidateSnapshotSchedule.hype_id == hype.id,
                CandidateSnapshotSchedule.checkpoint == name,
            )
        )
        if existing:
            rows.append(existing)
            continue
        due = t0 + delta
        row = CandidateSnapshotSchedule(
            hype_id=hype.id,
            checkpoint=name,
            due_at=due,
            status="PENDING",
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def add_alias(
    db: Session,
    hype_id: int,
    alias: str,
    alias_type: Optional[str] = "initial",
) -> HypeAlias:
    now = utcnow()
    norm = normalize_candidate_text(alias)
    existing = db.scalar(
        select(HypeAlias).where(
            HypeAlias.hype_id == hype_id,
            HypeAlias.normalized_alias == norm,
        )
    )
    if existing:
        return existing
    row = HypeAlias(
        hype_id=hype_id,
        alias=alias,
        normalized_alias=norm,
        alias_type=alias_type,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def accept_as_new_hype(
    db: Session,
    signal_id: int,
    *,
    plain_english: Optional[str] = None,
    hype_unit_type: Optional[str] = None,
) -> HypeCandidate:
    signal = db.get(CandidateSignal, signal_id)
    if not signal:
        raise ValueError("signal not found")
    if signal.state not in {"OPEN", "IGNORED_DUPLICATE"}:
        raise ValueError(f"signal state {signal.state} cannot be accepted")

    now = utcnow()
    raw = db.get(RawEvent, signal.raw_event_id)
    t0 = ensure_aware(raw.published_at if raw else None) or ensure_aware(
        raw.retrieved_at if raw else None
    ) or now

    hype = HypeCandidate(
        canonical_name=signal.candidate_text,
        plain_english=plain_english,
        hype_unit_type=hype_unit_type,
        public_disclosure_t0=t0,
        breakout_origin_t0=None,
        candidate_status="OPEN",
        created_at=now,
        last_activity_at=now,
        updated_at=now,
    )
    db.add(hype)
    db.flush()

    add_alias(db, hype.id, signal.candidate_text, alias_type="initial")
    create_snapshot_schedule(db, hype, t0)

    signal.state = "ACCEPTED"
    signal.linked_hype_id = hype.id
    signal.reviewed_at = now
    db.commit()
    db.refresh(hype)
    return hype


def attach_to_hype(db: Session, signal_id: int, hype_id: int) -> CandidateSignal:
    signal = db.get(CandidateSignal, signal_id)
    hype = db.get(HypeCandidate, hype_id)
    if not signal:
        raise ValueError("signal not found")
    if not hype:
        raise ValueError("hype candidate not found")
    if signal.state not in {"OPEN", "IGNORED_DUPLICATE"}:
        raise ValueError(f"signal state {signal.state} cannot be attached")

    now = utcnow()
    signal.state = "ACCEPTED"
    signal.linked_hype_id = hype.id
    signal.reviewed_at = now
    add_alias(db, hype.id, signal.candidate_text, alias_type="attached")
    hype.last_activity_at = now
    hype.updated_at = now
    db.commit()
    db.refresh(signal)
    return signal


def reject_signal(
    db: Session,
    signal_id: int,
    reason: Optional[str] = None,
    note: Optional[str] = None,
) -> CandidateSignal:
    signal = db.get(CandidateSignal, signal_id)
    if not signal:
        raise ValueError("signal not found")
    if signal.state not in {"OPEN", "IGNORED_DUPLICATE"}:
        raise ValueError(f"signal state {signal.state} cannot be rejected")
    if reason and reason not in REJECT_REASONS:
        raise ValueError(f"invalid reject reason: {reason}")

    now = utcnow()
    signal.state = "REJECTED"
    signal.reviewed_at = now
    parts = []
    if reason:
        parts.append(reason)
    if note:
        parts.append(note)
    if parts:
        signal.review_note = " | ".join(parts)
    db.commit()
    db.refresh(signal)
    return signal


def merge_signal(db: Session, signal_id: int, into_signal_id: int) -> CandidateSignal:
    signal = db.get(CandidateSignal, signal_id)
    target = db.get(CandidateSignal, into_signal_id)
    if not signal or not target:
        raise ValueError("signal not found")
    if signal.id == target.id:
        raise ValueError("cannot merge signal into itself")
    if signal.state not in {"OPEN", "IGNORED_DUPLICATE"}:
        raise ValueError(f"signal state {signal.state} cannot be merged")

    now = utcnow()
    signal.state = "MERGED"
    signal.merged_into_signal_id = target.id
    signal.linked_hype_id = target.linked_hype_id
    signal.reviewed_at = now
    db.commit()
    db.refresh(signal)
    return signal


def promote_raw_event(
    db: Session,
    event_id: int,
    *,
    candidate_name: str,
    unit_type: Optional[str] = None,
    phrase_or_object: Optional[str] = None,
) -> CandidateSignal:
    event = db.get(RawEvent, event_id)
    if not event:
        raise ValueError("event not found")
    now = utcnow()
    text = phrase_or_object or candidate_name
    signal = CandidateSignal(
        raw_event_id=event.id,
        account_event_id=None,
        signal_type="MANUAL",
        candidate_text=candidate_name,
        normalized_text=normalize_candidate_text(candidate_name),
        extraction_method="MANUAL_PROMOTION",
        source_role=None,
        trigger_reason=f"Manual promotion from raw event {event.id}",
        initial_priority="MEDIUM",
        state="OPEN",
        created_at=now,
        review_note=f"unit_type={unit_type}; phrase={text}" if unit_type or phrase_or_object else None,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal
