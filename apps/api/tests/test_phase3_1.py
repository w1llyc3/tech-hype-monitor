"""Phase 3.1 integrity: no double-count, evidence window, SKIPPED, GH/HF relevance."""

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
from app.core.timeutil import utcnow
from app.db.models import (
    Account,
    Base,
    CandidateSnapshot,
    CandidateSnapshotSchedule,
    HypeCandidate,
    RawEvent,
    Source,
    TrackedEntity,
)
from app.services.candidate_extraction import extract_candidates
from app.services.candidate_review import accept_as_new_hype
from app.services.candidate_snapshots import (
    _collect_hn_stats,
    _collect_rss_stats,
    _collect_x_account_stats,
    _github_item_relevant,
    _hf_item_relevant,
    _text_matches,
    run_checkpoint,
)
from app.services.x_ingest import manual_ingest


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "p31.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _account(db, handle="karpathy", **kw) -> Account:
    now = datetime.now(timezone.utc)
    data = dict(
        platform="x",
        handle=handle,
        display_name=handle,
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


def _accept_live(db, handle="karpathy", text="I call this WindowTerm", status_id="8001"):
    _account(db, handle=handle)
    r = manual_ingest(
        db,
        url=f"https://x.com/{handle}/status/{status_id}",
        handle=handle,
        text=text,
        posted_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    return accept_as_new_hype(db, r.candidate_signal_ids[0])


def test_migration_0001_to_0005(tmp_path: Path):
    db_path = tmp_path / "mig5.db"
    url = f"sqlite:///{db_path.as_posix()}"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(candidate_snapshot_schedule)"))}
        assert "skip_reason" in cols
        # existing phase tables still present
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "candidate_signals" in tables
        assert "tracked_entities" in tables
    engine.dispose()


def test_x_mention_not_double_counted(db_session):
    hype = _accept_live(db_session, text="I call this UniqueTerm", status_id="8101")
    now = utcnow()
    ws = hype.public_disclosure_t0 or hype.created_at
    stats = _collect_x_account_stats(db_session, hype, ["UniqueTerm"], ws, now)
    assert stats["mention_count"] == 1
    assert stats["independent_account_count"] == 1


def test_two_monitored_posts_count_two(db_session):
    _account(db_session, handle="alice")
    _account(db_session, handle="bob", primary_bucket="MODEL_ANOMALY_OBJECT_SCOUT")
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    manual_ingest(
        db_session,
        url="https://x.com/alice/status/8201",
        handle="alice",
        text="I call this DuoTerm",
        posted_at=t0 + timedelta(minutes=1),
    )
    manual_ingest(
        db_session,
        url="https://x.com/bob/status/8202",
        handle="bob",
        text="Look at DuoTerm in the wild",
        posted_at=t0 + timedelta(minutes=2),
    )
    hype = HypeCandidate(
        canonical_name="DuoTerm",
        public_disclosure_t0=t0,
        candidate_status="OPEN",
        created_at=utcnow(),
        updated_at=utcnow(),
        last_activity_at=utcnow(),
    )
    db_session.add(hype)
    db_session.commit()
    stats = _collect_x_account_stats(db_session, hype, ["DuoTerm"], t0, utcnow())
    assert stats["mention_count"] == 2
    assert stats["independent_account_count"] == 2


def test_pre_t0_x_excluded(db_session):
    now = utcnow()
    t0 = now - timedelta(hours=1)
    src = Source(
        name="X Manual Ingest",
        platform="x",
        source_type="x_manual",
        base_url="https://x.com",
        poll_interval_seconds=86400,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(src)
    db_session.flush()
    db_session.add(
        RawEvent(
            source_id=src.id,
            platform="x",
            external_id="8301",
            author="karpathy",
            published_at=t0 - timedelta(hours=5),
            retrieved_at=t0 - timedelta(hours=5),
            canonical_url="https://x.com/karpathy/status/8301",
            raw_text="I call this PreTerm",
            content_hash="pre1",
            event_type="x_post",
            created_at=now,
        )
    )
    hype = HypeCandidate(
        canonical_name="PreTerm",
        public_disclosure_t0=t0,
        candidate_status="OPEN",
        created_at=now,
        updated_at=now,
    )
    db_session.add(hype)
    db_session.commit()
    stats = _collect_x_account_stats(db_session, hype, ["PreTerm"], t0, now)
    assert stats["mention_count"] == 0

    db_session.add(
        RawEvent(
            source_id=src.id,
            platform="x",
            external_id="8302",
            author="karpathy",
            published_at=t0 + timedelta(minutes=1),
            retrieved_at=t0 + timedelta(minutes=1),
            canonical_url="https://x.com/karpathy/status/8302",
            raw_text="I call this PreTerm again after T0",
            content_hash="pre2",
            event_type="x_post",
            created_at=now,
        )
    )
    db_session.commit()
    stats2 = _collect_x_account_stats(db_session, hype, ["PreTerm"], t0, utcnow())
    assert stats2["mention_count"] == 1


def test_pre_t0_hn_and_rss_excluded(db_session):
    now = utcnow()
    t0 = now - timedelta(hours=1)
    src = Source(
        name="HN",
        platform="hn",
        source_type="hacker_news",
        base_url="https://example.com",
        poll_interval_seconds=120,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(src)
    db_session.flush()
    db_session.add(
        RawEvent(
            source_id=src.id,
            platform="hn",
            external_id="1",
            published_at=t0 - timedelta(hours=2),
            retrieved_at=t0 - timedelta(hours=2),
            title="Talking about WindowHN",
            raw_text="WindowHN",
            content_hash="a",
            event_type="story",
            created_at=now,
        )
    )
    db_session.add(
        RawEvent(
            source_id=src.id,
            platform="hn",
            external_id="2",
            published_at=t0 + timedelta(minutes=5),
            retrieved_at=t0 + timedelta(minutes=5),
            title="WindowHN after",
            raw_text="WindowHN",
            content_hash="b",
            event_type="story",
            created_at=now,
        )
    )
    rss = Source(
        name="Blog",
        platform="official_rss",
        source_type="official_rss",
        base_url="https://example.com",
        poll_interval_seconds=600,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(rss)
    db_session.flush()
    db_session.add(
        RawEvent(
            source_id=rss.id,
            platform="official_rss",
            external_id="r1",
            published_at=t0 - timedelta(days=1),
            retrieved_at=t0 - timedelta(days=1),
            title="WindowRSS old",
            raw_text="WindowRSS",
            content_hash="c",
            event_type="rss_item",
            created_at=now,
        )
    )
    db_session.add(
        RawEvent(
            source_id=rss.id,
            platform="official_rss",
            external_id="r2",
            published_at=t0 + timedelta(minutes=5),
            retrieved_at=t0 + timedelta(minutes=5),
            title="WindowRSS new",
            raw_text="WindowRSS",
            content_hash="d",
            event_type="rss_item",
            created_at=now,
        )
    )
    db_session.commit()

    hn = _collect_hn_stats(db_session, ["WindowHN"], t0, now)
    assert hn["hn_matching_story_count"] == 1
    rss_stats = _collect_rss_stats(db_session, ["WindowRSS"], t0, now)
    assert rss_stats["rss_matching_count"] == 1


def test_historical_checkpoint_skipped_no_snapshot(db_session):
    _account(db_session)
    r = manual_ingest(
        db_session,
        url="https://x.com/karpathy/status/8401",
        handle="karpathy",
        text="I call this OldHist",
        posted_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    hype = accept_as_new_hype(db_session, r.candidate_signal_ids[0])
    rows = db_session.scalars(
        select(CandidateSnapshotSchedule).where(CandidateSnapshotSchedule.hype_id == hype.id)
    ).all()
    skipped = [s for s in rows if s.status == "SKIPPED"]
    assert skipped
    assert all(s.skip_reason == "MISSED_BEFORE_TRACKING" for s in skipped)
    snaps = db_session.scalars(
        select(CandidateSnapshot).where(CandidateSnapshot.hype_id == hype.id)
    ).all()
    assert snaps == []
    # skipped checkpoints must not be runnable into fake snapshots
    for s in skipped:
        with pytest.raises(ValueError):
            asyncio.run(run_checkpoint(db_session, s))


def test_live_checkpoint_timing_metadata(db_session, monkeypatch):
    hype = _accept_live(db_session, text="I call this LiveTerm", status_id="8501")

    async def fake_gh(*args, **kwargs):
        return {
            "github_search_result_count_raw": 0,
            "github_repo_count_relevant": 0,
            "github_repo_count_post_t0": 0,
            "github_repo_count_preexisting": 0,
            "github_repo_count_unknown_time": 0,
            "github_independent_owner_count_post_t0": 0,
            "github_total_stars_post_t0": 0,
            "github_max_star_velocity_24h_post_t0": None,
            "github_repo_count": 0,
            "github_independent_owner_count": 0,
            "github_total_stars": 0,
            "github_max_star_velocity_24h": None,
        }

    def fake_hf(*args, **kwargs):
        return {
            "hf_model_count_raw": 0,
            "hf_model_count_relevant": 0,
            "hf_model_count_post_t0": 0,
            "hf_model_count_preexisting": 0,
            "hf_model_count_unknown_time": 0,
            "hf_space_count_raw": 0,
            "hf_space_count_relevant": 0,
            "hf_space_count_post_t0": 0,
            "hf_space_count_preexisting": 0,
            "hf_space_count_unknown_time": 0,
            "hf_dataset_count_raw": 0,
            "hf_dataset_count_relevant": 0,
            "hf_dataset_count_post_t0": 0,
            "hf_dataset_count_preexisting": 0,
            "hf_dataset_count_unknown_time": 0,
            "hf_independent_author_count_post_t0": 0,
            "hf_model_count": 0,
            "hf_space_count": 0,
            "hf_dataset_count": 0,
            "hf_independent_author_count": 0,
        }

    monkeypatch.setattr("app.services.candidate_snapshots._collect_github_stats", fake_gh)
    monkeypatch.setattr("app.services.candidate_snapshots._collect_hf_stats", fake_hf)

    row = db_session.scalars(
        select(CandidateSnapshotSchedule).where(
            CandidateSnapshotSchedule.hype_id == hype.id,
            CandidateSnapshotSchedule.checkpoint == "1H",
        )
    ).one()
    assert row.status == "PENDING"
    row.due_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    db_session.commit()
    snap = asyncio.run(run_checkpoint(db_session, row))
    meta = snap.metadata_json or {}
    assert meta.get("scheduled_due_at")
    assert meta.get("late_by_seconds", 0) >= 15 * 60
    assert meta.get("timing_quality") == "LATE"


def test_irrelevant_github_hf_not_counted_raw_persisted(db_session):
    aliases = ["vibe coding"]
    relevant_gh = {
        "external_id": "alice/vibe-coding",
        "name": "vibe-coding",
        "description": "A vibe coding toolkit",
        "topics": ["ai"],
        "owner": "alice",
        "stars": 10,
    }
    irrelevant_gh = {
        "external_id": "bob/unrelated",
        "name": "unrelated",
        "description": "general coding tips",
        "topics": ["python"],
        "owner": "bob",
        "stars": 99,
    }
    assert _github_item_relevant(relevant_gh, aliases) is True
    assert _github_item_relevant(irrelevant_gh, aliases) is False

    relevant_hf = {
        "external_id": "org/vibe-coding-demo",
        "repo_id": "org/vibe-coding-demo",
        "tags": ["demo"],
        "pipeline_tag": None,
        "sdk": "gradio",
        "author": "org",
    }
    irrelevant_hf = {
        "external_id": "org/bert-base",
        "repo_id": "org/bert-base",
        "tags": ["transformers"],
        "pipeline_tag": "fill-mask",
        "sdk": None,
        "author": "org",
    }
    assert _hf_item_relevant(relevant_hf, aliases) is True
    assert _hf_item_relevant(irrelevant_hf, aliases) is False

    # raw discovery still persisted when collector runs
    async def fake_search(q, limit=10, source=None):
        return [relevant_gh, irrelevant_gh]

    def fake_hf_search(kind, q, limit=10):
        return [relevant_hf, irrelevant_hf]

    import app.services.candidate_snapshots as mod

    async def run():
        # monkey via local patch
        from app.adapters import github as gh_mod
        from app.adapters import huggingface as hf_mod

        return await mod._collect_github_stats(db_session, aliases)

    # persist path: call discovery helpers directly to prove raw survives filter
    from app.services.discovery import persist_github_discovery, persist_hf_discovery

    persist_github_discovery(db_session, [relevant_gh, irrelevant_gh])
    persist_hf_discovery(
        db_session,
        [
            {**relevant_hf, "entity_type": "hf_space"},
            {**irrelevant_hf, "entity_type": "hf_model"},
        ],
    )
    entities = db_session.scalars(select(TrackedEntity)).all()
    assert len(entities) >= 2
    assert any(e.external_id == "bob/unrelated" for e in entities)
    assert any(e.external_id == "org/bert-base" for e in entities)


def test_short_alias_boundary_match():
    aliases = ["zz"]
    assert _text_matches("prefix zz suffix", aliases) is True
    assert _text_matches("fuzzyzzmatch", aliases) is False
    assert _text_matches("the zzz tool", ["zzz"]) is True
    assert _text_matches("fuzzyzzzmatch", ["zzz"]) is False


def test_extraction_new_false_positive_and_zzz():
    now = datetime.now(timezone.utc)
    account = Account(
        platform="x",
        handle="scout",
        primary_bucket="MODEL_ANOMALY_OBJECT_SCOUT",
        monitor_priority="P0",
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    bad = extract_candidates("I love the NEW model from OpenAI", account)
    assert not any(c.normalized_text == "new" for c in bad)

    good = extract_candidates("the agents prefix it ZZZ", account)
    assert any(c.signal_type == "EMBEDDED_OBJECT" and c.normalized_text == "zzz" for c in good)
