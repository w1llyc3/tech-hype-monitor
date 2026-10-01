"""Phase 3 tests: accounts, X ingest, denominator, extraction, review, snapshots."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import API_ROOT
from app.db.models import (
    Account,
    AccountEvent,
    Base,
    CandidateSignal,
    CandidateSnapshot,
    CandidateSnapshotSchedule,
    HypeAlias,
    HypeCandidate,
    RawEvent,
    Source,
)
from app.core.timeutil import ensure_aware
from app.services.candidate_extraction import extract_candidates, normalize_candidate_text
from app.services.candidate_review import (
    accept_as_new_hype,
    attach_to_hype,
    merge_signal,
    reject_signal,
)
from app.services.candidate_snapshots import process_due_candidate_snapshots, run_checkpoint
from app.services.x_ingest import manual_ingest


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "p3.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _account(db, **kw) -> Account:
    now = datetime.now(timezone.utc)
    data = dict(
        platform="x",
        handle="karpathy",
        display_name="Andrej Karpathy",
        primary_bucket="NARRATIVE_NAMER",
        secondary_role="FRAMER",
        universe_tier="CORE",
        monitor_priority="P0",
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    data.update(kw)
    row = Account(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_migration_0004_chain(tmp_path: Path):
    db_path = tmp_path / "mig.db"
    url = f"sqlite:///{db_path.as_posix()}"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "candidate_signals" in tables
        assert "hype_aliases" in tables
        assert "candidate_snapshot_schedule" in tables
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(candidate_snapshots)"))}
        assert "metadata_json" in cols
        assert "checkpoint" in cols
    engine.dispose()


def test_account_import_upsert(tmp_path: Path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "import_accounts",
        Path(__file__).resolve().parents[3] / "scripts" / "import_accounts.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    db_path = tmp_path / "imp.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr(mod, "SessionLocal", Session)
    monkeypatch.setattr(mod, "init_db", lambda: None)

    csv_path = tmp_path / "acc.csv"
    csv_path.write_text(
        "platform,handle,display_name,primary_bucket,secondary_role,universe_tier,"
        "monitor_priority,preferred_trigger,economic_exposure,conflict_risk,"
        "reverse_test_status,tech_to_crypto_relevance,enabled\n"
        "x,@alice,Alice,NARRATIVE_NAMER,FRAMER,CORE,P1,x,LOW,LOW,ok,LOW,true\n",
        encoding="utf-8",
    )
    ins, upd = mod.import_accounts(csv_path)
    assert ins == 1 and upd == 0
    csv_path.write_text(
        "platform,handle,display_name,primary_bucket,secondary_role,universe_tier,"
        "monitor_priority,preferred_trigger,economic_exposure,conflict_risk,"
        "reverse_test_status,tech_to_crypto_relevance,enabled\n"
        "x,@alice,Alice,NARRATIVE_NAMER,FRAMER,CORE,P0,x,LOW,LOW,ok,LOW,true\n",
        encoding="utf-8",
    )
    ins2, upd2 = mod.import_accounts(csv_path)
    assert ins2 == 0 and upd2 == 1
    with Session() as db:
        rows = db.scalars(select(Account)).all()
        assert len(rows) == 1
        assert rows[0].handle == "alice"
        assert rows[0].monitor_priority == "P0"
    engine.dispose()


def test_x_ingest_known_unknown_dedupe_text(db_session):
    _account(db_session)
    r1 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/111",
        handle="@karpathy",
        text="I call this vibe coding",
        posted_at=datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc),
    )
    assert r1.known_account is True
    assert r1.account_id is not None
    event = db_session.get(RawEvent, r1.raw_event_id)
    assert event is not None
    assert event.raw_text == "I call this vibe coding"
    assert event.external_id == "111"

    r2 = manual_ingest(
        db_session,
        url="https://x.com/nobody/status/222",
        handle="@unknown_user",
        text="hello world",
    )
    assert r2.known_account is False
    assert r2.account_id is None
    assert db_session.get(RawEvent, r2.raw_event_id) is not None

    r3 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/111",
        handle="karpathy",
        text="EDITED should not overwrite",
    )
    assert r3.raw_event_id == r1.raw_event_id
    assert r3.created_raw is False
    event2 = db_session.get(RawEvent, r3.raw_event_id)
    assert event2.raw_text == "I call this vibe coding"


def test_denominator_no_candidate(db_session):
    _account(db_session, handle="weatherbot", primary_bucket="EXPERT_VALIDATOR")
    result = manual_ingest(
        db_session,
        url="https://x.com/weatherbot/status/333",
        handle="@weatherbot",
        text="Great weather today.",
    )
    assert result.candidate_signal_ids == []
    ae = db_session.get(AccountEvent, result.account_event_id)
    assert ae is not None
    assert ae.trigger_type == "NO_CANDIDATE"
    assert ae.candidate_state == "CLOSED"


def test_extraction_examples(db_session):
    namer = _account(db_session)
    c1 = extract_candidates("There's a new kind of coding I call vibe coding...", namer)
    assert any(c.signal_type == "NEW_TERM" and "vibe coding" in c.normalized_text for c in c1)

    scout = _account(
        db_session,
        handle="objectscout",
        primary_bucket="MODEL_ANOMALY_OBJECT_SCOUT",
        monitor_priority="P0",
    )
    c2 = extract_candidates(
        "...the agents prefix the page with ZZZ so it is deleted last...", scout
    )
    assert any(c.signal_type == "EMBEDDED_OBJECT" and c.normalized_text == "zzz" for c in c2)

    assert normalize_candidate_text("$ZZZ") == "zzz"
    assert normalize_candidate_text("Vibe Coding") == "vibe coding"
    assert normalize_candidate_text("DeepResearch") == "deepresearch"

    c3 = extract_candidates(
        'Context Engineering is a better term than prompt engineering', namer
    )
    assert any(c.signal_type == "REFRAME" for c in c3)

    c4 = extract_candidates('He said "operator mode" is coming', namer)
    assert any("operator mode" in c.normalized_text for c in c4)

    c5 = extract_candidates("Check out DeepResearch today", scout)
    assert any(c.extraction_method == "CAMEL_CASE" for c in c5)

    # no duplicate from same event ingest
    r = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/444",
        handle="karpathy",
        text="I call this vibe coding",
    )
    first = list(r.candidate_signal_ids)
    r2 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/444",
        handle="karpathy",
        text="I call this vibe coding",
    )
    assert r2.candidate_signal_ids == []
    total = db_session.scalars(
        select(CandidateSignal).where(CandidateSignal.raw_event_id == r.raw_event_id)
    ).all()
    # same normalized+type should not duplicate
    keys = {(s.signal_type, s.normalized_text) for s in total}
    assert len(keys) == len(total)
    assert first


def test_candidate_review_flow(db_session):
    _account(db_session)
    r = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/555",
        handle="karpathy",
        text="I call this vibe coding",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    sig_id = r.candidate_signal_ids[0]
    hype = accept_as_new_hype(db_session, sig_id)
    assert hype.candidate_status == "OPEN"
    assert hype.public_disclosure_t0 is not None
    aliases = db_session.scalars(select(HypeAlias).where(HypeAlias.hype_id == hype.id)).all()
    assert aliases
    schedule = db_session.scalars(
        select(CandidateSnapshotSchedule).where(CandidateSnapshotSchedule.hype_id == hype.id)
    ).all()
    assert {s.checkpoint for s in schedule} == {"1H", "6H", "24H", "72H", "7D", "30D"}
    # historical overdue checkpoints are SKIPPED — no fake snapshots
    overdue = [
        s
        for s in schedule
        if ensure_aware(s.due_at) and ensure_aware(s.due_at) < datetime.now(timezone.utc)
    ]
    assert overdue
    assert all(s.status == "SKIPPED" for s in overdue)
    assert all(s.skip_reason == "MISSED_BEFORE_TRACKING" for s in overdue)

    # same-name second cycle allowed
    r2 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/556",
        handle="karpathy",
        text="I call this vibe coding again",
    )
    hype2 = accept_as_new_hype(db_session, r2.candidate_signal_ids[0])
    assert hype2.id != hype.id

    # reject remains stored
    r3 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/557",
        handle="karpathy",
        text="I call this throwaway term",
    )
    rejected = reject_signal(db_session, r3.candidate_signal_ids[0], reason="TOO_GENERIC")
    assert rejected.state == "REJECTED"
    assert db_session.get(CandidateSignal, rejected.id) is not None

    # attach
    r4 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/558",
        handle="karpathy",
        text="I call this vibe coding remix",
    )
    attached = attach_to_hype(db_session, r4.candidate_signal_ids[0], hype.id)
    assert attached.linked_hype_id == hype.id
    assert attached.state == "ACCEPTED"

    # merge
    r5 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/559",
        handle="karpathy",
        text="I call this mergeable phrase",
    )
    r6 = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/560",
        handle="karpathy",
        text="I call this mergeable phrase v2",
    )
    merged = merge_signal(db_session, r6.candidate_signal_ids[0], r5.candidate_signal_ids[0])
    assert merged.state == "MERGED"
    assert merged.merged_into_signal_id == r5.candidate_signal_ids[0]


def test_snapshots_once_and_isolation(db_session, monkeypatch):
    _account(db_session)
    # Recent T0 so checkpoints stay PENDING (not historical SKIPPED)
    r = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/777",
        handle="karpathy",
        text="I call this SnapshotTerm",
        posted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    hype = accept_as_new_hype(db_session, r.candidate_signal_ids[0])

    async def fake_gh(db, aliases):
        return {
            "github_search_result_count_raw": 0,
            "github_repo_count_relevant": 0,
            "github_repo_count": 0,
            "github_independent_owner_count": 0,
            "github_total_stars": 0,
            "github_max_star_velocity_24h": None,
        }

    def fake_hf(db, aliases):
        return {
            "hf_model_count_raw": 0,
            "hf_model_count_relevant": 0,
            "hf_space_count_raw": 0,
            "hf_space_count_relevant": 0,
            "hf_dataset_count_raw": 0,
            "hf_dataset_count_relevant": 0,
            "hf_model_count": 0,
            "hf_space_count": 0,
            "hf_dataset_count": 0,
            "hf_independent_author_count": 0,
        }

    monkeypatch.setattr(
        "app.services.candidate_snapshots._collect_github_stats", fake_gh
    )
    monkeypatch.setattr("app.services.candidate_snapshots._collect_hf_stats", fake_hf)

    due = db_session.scalars(
        select(CandidateSnapshotSchedule).where(
            CandidateSnapshotSchedule.hype_id == hype.id,
            CandidateSnapshotSchedule.checkpoint == "1H",
        )
    ).one()
    assert due.status == "PENDING"
    # Make it due now (late processing allowed)
    due.due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    snap = asyncio.run(run_checkpoint(db_session, due))
    assert snap.checkpoint == "1H"
    assert snap.metadata_json is not None
    assert "late_by_seconds" in snap.metadata_json
    assert "timing_quality" in snap.metadata_json
    # unknown metrics remain NULL where not computed
    assert snap.cross_cluster_count is None
    assert snap.source_detachment is None

    # process again — no duplicate completion
    due2 = db_session.get(CandidateSnapshotSchedule, due.id)
    snap2 = asyncio.run(run_checkpoint(db_session, due2))
    assert snap2.id == snap.id
    count = db_session.scalars(
        select(CandidateSnapshot).where(
            CandidateSnapshot.hype_id == hype.id,
            CandidateSnapshot.checkpoint == "1H",
        )
    ).all()
    assert len(count) == 1

    # failed checkpoint isolated
    bad = db_session.scalars(
        select(CandidateSnapshotSchedule).where(
            CandidateSnapshotSchedule.hype_id == hype.id,
            CandidateSnapshotSchedule.checkpoint == "6H",
        )
    ).one()
    bad.due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    async def boom(db, aliases):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.services.candidate_snapshots._collect_github_stats", boom
    )
    n = asyncio.run(process_due_candidate_snapshots(db_session, limit=5))
    db_session.refresh(bad)
    assert bad.status == "FAILED"
    assert "boom" in (bad.last_error or "")
    # other pending remain
    still = db_session.scalars(
        select(CandidateSnapshotSchedule).where(
            CandidateSnapshotSchedule.hype_id == hype.id,
            CandidateSnapshotSchedule.checkpoint == "24H",
        )
    ).one()
    assert still.status == "PENDING"
    assert n >= 0
