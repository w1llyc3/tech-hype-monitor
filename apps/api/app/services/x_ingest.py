"""Manual X ingest: raw event + account_event denominator + candidate extraction."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import ensure_aware, utcnow
from app.db.models import Account, AccountEvent, CandidateSignal, HypeAlias, HypeCandidate, RawEvent, Source
from app.services.candidate_extraction import extract_candidates, normalize_candidate_text, normalize_handle

ALLOWED_POST_TYPES = {"original", "reply", "quote", "repost", "unknown"}
STATUS_RE = re.compile(r"/status(?:es)?/(\d+)", re.I)


@dataclass
class ManualIngestResult:
    raw_event_id: int
    account_id: Optional[int]
    account_event_id: Optional[int]
    known_account: bool
    created_raw: bool
    candidate_signal_ids: list[int]
    suggested_hype_ids: list[int]


def ensure_x_manual_source(db: Session) -> Source:
    now = utcnow()
    source = db.scalar(select(Source).where(Source.name == "X Manual Ingest"))
    if source:
        source.platform = "x"
        source.source_type = "x_manual"
        source.enabled = True
        source.updated_at = now
        return source
    source = Source(
        name="X Manual Ingest",
        platform="x",
        source_type="x_manual",
        base_url="https://x.com",
        feed_url=None,
        poll_interval_seconds=86400,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db.add(source)
    db.flush()
    return source


def parse_status_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = STATUS_RE.search(url)
    return m.group(1) if m else None


def find_account(db: Session, handle: str, platform: str = "x") -> Optional[Account]:
    canon = normalize_handle(handle)
    # Match both stored forms: karpathy and @karpathy
    rows = db.scalars(select(Account).where(Account.platform == platform)).all()
    for row in rows:
        if normalize_handle(row.handle) == canon:
            return row
    return None


def _content_hash(url: str, text: str) -> str:
    return hashlib.sha256(f"{url.strip()}\n{text}".encode("utf-8")).hexdigest()


def _find_existing_raw(db: Session, source: Source, url: str, status_id: Optional[str]) -> Optional[RawEvent]:
    if status_id:
        found = db.scalar(
            select(RawEvent).where(
                RawEvent.source_id == source.id,
                RawEvent.external_id == status_id,
            )
        )
        if found:
            return found
    found = db.scalar(
        select(RawEvent).where(
            RawEvent.source_id == source.id,
            RawEvent.canonical_url == url,
        )
    )
    return found


def _upsert_account_event(
    db: Session,
    *,
    account: Account,
    raw_event: RawEvent,
    post_type: str,
    parent_url: Optional[str],
    trigger_type: str,
    candidate_state: str,
    candidate_phrase: Optional[str],
    candidate_object: Optional[str],
) -> AccountEvent:
    now = utcnow()
    existing = db.scalar(
        select(AccountEvent).where(
            AccountEvent.account_id == account.id,
            AccountEvent.raw_event_id == raw_event.id,
        )
    )
    is_original = post_type == "original"
    is_reply = post_type == "reply"
    is_quote = post_type == "quote"
    observed = ensure_aware(raw_event.published_at) or ensure_aware(raw_event.retrieved_at) or now

    if existing:
        existing.trigger_type = trigger_type
        existing.candidate_state = candidate_state
        existing.candidate_phrase = candidate_phrase
        existing.candidate_object = candidate_object
        existing.is_original = is_original
        existing.is_reply = is_reply
        existing.is_quote = is_quote
        existing.parent_url = parent_url
        existing.observed_at = observed
        existing.economic_exposure_at_time = account.economic_exposure
        existing.updated_at = now
        return existing

    row = AccountEvent(
        account_id=account.id,
        raw_event_id=raw_event.id,
        observed_at=observed,
        trigger_type=trigger_type,
        is_original=is_original,
        is_reply=is_reply,
        is_quote=is_quote,
        parent_url=parent_url,
        candidate_phrase=candidate_phrase,
        candidate_object=candidate_object,
        economic_exposure_at_time=account.economic_exposure,
        candidate_state=candidate_state,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _suggested_hype_ids(db: Session, normalized_text: str) -> list[int]:
    ids: list[int] = []
    for h in db.scalars(
        select(HypeCandidate).where(HypeCandidate.canonical_name.is_not(None))
    ).all():
        if normalize_candidate_text(h.canonical_name) == normalized_text:
            ids.append(h.id)
    for alias in db.scalars(
        select(HypeAlias).where(HypeAlias.normalized_alias == normalized_text)
    ).all():
        if alias.hype_id not in ids:
            ids.append(alias.hype_id)
    return ids


def persist_extracted_signals(
    db: Session,
    *,
    raw_event: RawEvent,
    account_event: Optional[AccountEvent],
    account: Optional[Account],
) -> list[CandidateSignal]:
    text = raw_event.raw_text or ""
    extracted = extract_candidates(text, account)
    now = utcnow()
    created: list[CandidateSignal] = []

    for item in extracted:
        existing = db.scalar(
            select(CandidateSignal).where(
                CandidateSignal.raw_event_id == raw_event.id,
                CandidateSignal.normalized_text == item.normalized_text,
                CandidateSignal.signal_type == item.signal_type,
            )
        )
        if existing:
            # Exact duplicate on same event — mark IGNORED_DUPLICATE if somehow recreated
            if existing.state == "OPEN":
                pass
            continue

        # Check if an identical open/accepted already exists from prior ingest of same event
        dup = db.scalar(
            select(CandidateSignal).where(
                CandidateSignal.raw_event_id == raw_event.id,
                CandidateSignal.normalized_text == item.normalized_text,
                CandidateSignal.signal_type == item.signal_type,
            )
        )
        if dup:
            continue

        suggestions = _suggested_hype_ids(db, item.normalized_text)
        note = None
        if suggestions:
            note = f"Suggested existing candidate ids: {suggestions}"

        signal = CandidateSignal(
            raw_event_id=raw_event.id,
            account_event_id=account_event.id if account_event else None,
            signal_type=item.signal_type,
            candidate_text=item.candidate_text,
            normalized_text=item.normalized_text,
            extraction_method=item.extraction_method,
            source_role=item.source_role,
            trigger_reason=item.trigger_reason,
            initial_priority=item.initial_priority,
            state="OPEN",
            created_at=now,
            review_note=note,
        )
        db.add(signal)
        db.flush()
        created.append(signal)

    return created


def manual_ingest(
    db: Session,
    *,
    url: str,
    handle: str,
    text: str,
    posted_at: Optional[datetime] = None,
    post_type: str = "original",
    parent_url: Optional[str] = None,
    quoted_url: Optional[str] = None,
    visible_metrics: Optional[dict[str, Any]] = None,
) -> ManualIngestResult:
    if not url or not handle or text is None or text == "":
        raise ValueError("url, handle, and text are required")

    post_type = (post_type or "original").lower()
    if post_type not in ALLOWED_POST_TYPES:
        raise ValueError(f"post_type must be one of {sorted(ALLOWED_POST_TYPES)}")

    # Soft URL validation
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("url must be http(s)")

    source = ensure_x_manual_source(db)
    status_id = parse_status_id(url)
    canon_handle = normalize_handle(handle)
    now = utcnow()
    content_hash = _content_hash(url, text)

    existing = _find_existing_raw(db, source, url, status_id)
    created_raw = False
    if existing:
        # Do not overwrite original text; refresh metadata/metrics only
        meta = dict(existing.metadata_json or {})
        meta["post_type"] = post_type
        if parent_url is not None:
            meta["parent_url"] = parent_url
        if quoted_url is not None:
            meta["quoted_url"] = quoted_url
        if visible_metrics is not None:
            meta["visible_metrics"] = visible_metrics
        meta["ingest_method"] = "manual"
        existing.metadata_json = meta
        if posted_at and not existing.published_at:
            existing.published_at = ensure_aware(posted_at)
        existing.retrieved_at = now
        raw_event = existing
    else:
        created_raw = True
        raw_event = RawEvent(
            source_id=source.id,
            platform="x",
            external_id=status_id,
            author=canon_handle,
            published_at=ensure_aware(posted_at),
            retrieved_at=now,
            canonical_url=url,
            title=None,
            raw_text=text,  # exact pasted text — never normalize away
            content_hash=content_hash,
            event_type="x_post",
            metadata_json={
                "post_type": post_type,
                "parent_url": parent_url,
                "quoted_url": quoted_url,
                "visible_metrics": visible_metrics,
                "ingest_method": "manual",
            },
            created_at=now,
        )
        db.add(raw_event)
        db.flush()

    account = find_account(db, canon_handle, platform="x")
    account_event: Optional[AccountEvent] = None
    signals: list[CandidateSignal] = []

    if account:
        # Extract first so we know NO_CANDIDATE vs CANDIDATE
        extracted = extract_candidates(raw_event.raw_text or "", account)
        if extracted:
            phrase = extracted[0].candidate_text
            obj = extracted[0].candidate_text if extracted[0].signal_type == "EMBEDDED_OBJECT" else None
            trigger = extracted[0].signal_type
            state = "OPEN"
        else:
            phrase = None
            obj = None
            trigger = "NO_CANDIDATE"
            state = "CLOSED"

        account_event = _upsert_account_event(
            db,
            account=account,
            raw_event=raw_event,
            post_type=post_type,
            parent_url=parent_url,
            trigger_type=trigger,
            candidate_state=state,
            candidate_phrase=phrase,
            candidate_object=obj,
        )
        signals = persist_extracted_signals(
            db, raw_event=raw_event, account_event=account_event, account=account
        )
        # If we ended with zero persisted OPEN signals (all dupes / filtered), keep NO_CANDIDATE
        openish = [s for s in signals if s.state == "OPEN"]
        existing_open = db.scalars(
            select(CandidateSignal).where(
                CandidateSignal.raw_event_id == raw_event.id,
                CandidateSignal.state == "OPEN",
            )
        ).all()
        if not openish and not existing_open:
            account_event.trigger_type = "NO_CANDIDATE"
            account_event.candidate_state = "CLOSED"
            account_event.candidate_phrase = None
            account_event.candidate_object = None
            account_event.updated_at = now
    else:
        # Unknown account: still save RawEvent; optionally extract without role boost
        signals = persist_extracted_signals(
            db, raw_event=raw_event, account_event=None, account=None
        )

    suggested: list[int] = []
    for s in signals:
        suggested.extend(_suggested_hype_ids(db, s.normalized_text))
    suggested = list(dict.fromkeys(suggested))

    db.commit()
    db.refresh(raw_event)

    return ManualIngestResult(
        raw_event_id=raw_event.id,
        account_id=account.id if account else None,
        account_event_id=account_event.id if account_event else None,
        known_account=account is not None,
        created_raw=created_raw,
        candidate_signal_ids=[s.id for s in signals],
        suggested_hype_ids=suggested,
    )
