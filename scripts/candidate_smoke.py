"""Synthetic Phase 3 candidate smoke — no external X access."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.timeutil import utcnow  # noqa: E402
from app.db.models import Account, AccountEvent, CandidateSignal  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.x_ingest import ensure_x_manual_source, manual_ingest  # noqa: E402


def _ensure_account(db, handle: str, primary_bucket: str, priority: str = "P0") -> Account:
    existing = db.scalar(
        select(Account).where(Account.platform == "x", Account.handle == handle)
    )
    now = utcnow()
    if existing:
        existing.primary_bucket = primary_bucket
        existing.monitor_priority = priority
        existing.universe_tier = "CORE"
        existing.enabled = True
        existing.updated_at = now
        return existing
    row = Account(
        platform="x",
        handle=handle,
        display_name=handle,
        primary_bucket=primary_bucket,
        secondary_role=None,
        universe_tier="CORE",
        monitor_priority=priority,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def main() -> None:
    init_db()
    stamp = int(utcnow().timestamp())
    with SessionLocal() as db:
        ensure_x_manual_source(db)
        namer = _ensure_account(db, "karpathy_like", "NARRATIVE_NAMER")
        scout = _ensure_account(db, "object_scout", "MODEL_ANOMALY_OBJECT_SCOUT")
        neutral = _ensure_account(db, "weather_bot", "EXPERT_VALIDATOR")
        db.commit()

        print("=== Vibe Coding-like ===")
        r1 = manual_ingest(
            db,
            url=f"https://x.com/karpathy_like/status/{stamp}001",
            handle="@karpathy_like",
            text="There's a new kind of coding I call vibe coding where you fully give in to the vibes.",
            posted_at=datetime.now(timezone.utc),
            post_type="original",
        )
        sigs1 = db.scalars(
            select(CandidateSignal).where(CandidateSignal.id.in_(r1.candidate_signal_ids or [-1]))
        ).all()
        if not sigs1:
            sigs1 = db.scalars(
                select(CandidateSignal).where(CandidateSignal.raw_event_id == r1.raw_event_id)
            ).all()
        print(f"known_account={r1.known_account} signals={len(sigs1)}")
        for s in sigs1:
            print(f"  - {s.signal_type}: {s.candidate_text!r} ({s.extraction_method})")
        assert any(s.signal_type == "NEW_TERM" and "vibe coding" in s.normalized_text for s in sigs1), "expected NEW_TERM"

        print("=== ZZZ-like ===")
        r2 = manual_ingest(
            db,
            url=f"https://x.com/object_scout/status/{stamp}002",
            handle="@object_scout",
            text="...the agents prefix the page with ZZZ so it is deleted last...",
            posted_at=datetime.now(timezone.utc),
        )
        sigs2 = db.scalars(
            select(CandidateSignal).where(CandidateSignal.raw_event_id == r2.raw_event_id)
        ).all()
        print(f"known_account={r2.known_account} signals={len(sigs2)}")
        for s in sigs2:
            print(f"  - {s.signal_type}: {s.candidate_text!r} ({s.extraction_method})")
        assert any(
            s.signal_type == "EMBEDDED_OBJECT" and s.normalized_text == "zzz" for s in sigs2
        ), "expected EMBEDDED_OBJECT ZZZ"

        print("=== No-candidate post ===")
        r3 = manual_ingest(
            db,
            url=f"https://x.com/weather_bot/status/{stamp}003",
            handle="@weather_bot",
            text="Great weather today.",
        )
        ae = db.get(AccountEvent, r3.account_event_id)
        print(
            f"signals={len(r3.candidate_signal_ids)} "
            f"trigger={ae.trigger_type if ae else None} "
            f"state={ae.candidate_state if ae else None}"
        )
        assert r3.candidate_signal_ids == []
        assert ae is not None
        assert ae.trigger_type == "NO_CANDIDATE"
        assert ae.candidate_state == "CLOSED"

        print("candidate_smoke OK")
        print(f"accounts used: {namer.handle}, {scout.handle}, {neutral.handle}")


if __name__ == "__main__":
    main()
