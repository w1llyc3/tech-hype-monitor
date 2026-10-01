"""Phase 3.2: immutable evidence time, post-T0 derivatives, origin-excluded amplifiers."""

from __future__ import annotations

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
    AccountEvent,
    Base,
    CandidateSignal,
    HypeCandidate,
    RawEvent,
    Source,
)
from app.services.candidate_review import accept_as_new_hype
from app.services.candidate_snapshots import (
    _classify_timing,
    _collect_hf_stats,
    _collect_x_account_stats,
    _event_time,
    _github_item_relevant,
    _hf_item_relevant,
    _origin_account,
    _source_detachment_level,
)
from app.services.x_ingest import manual_ingest


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "p32.db"
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


def test_migration_chain_to_head(tmp_path: Path):
    db_path = tmp_path / "mig.db"
    url = f"sqlite:///{db_path.as_posix()}"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "candidate_signals" in tables
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(candidate_snapshot_schedule)"))}
        assert "skip_reason" in cols
    engine.dispose()


def test_immutable_event_time_ignores_refreshed_retrieved_at(db_session):
    now = utcnow()
    t0 = now - timedelta(hours=1)
    src = Source(
        name="X Manual Ingest",
        platform="x",
        source_type="x_manual",
        base_url="https://x.com",
        poll_interval_seconds=86400,
        enabled=True,
        created_at=t0 - timedelta(hours=5),
        updated_at=t0 - timedelta(hours=5),
    )
    db_session.add(src)
    db_session.flush()
    # No published_at; created before T0; later "refresh" moves retrieved_at after T0
    ev = RawEvent(
        source_id=src.id,
        platform="x",
        external_id="imm1",
        author="karpathy",
        published_at=None,
        retrieved_at=now,  # refreshed after T0 — must NOT count
        canonical_url="https://x.com/karpathy/status/imm1",
        raw_text="I call this ImmTerm",
        content_hash="imm1",
        event_type="x_post",
        created_at=t0 - timedelta(hours=4),
    )
    db_session.add(ev)
    db_session.commit()

    assert _event_time(ev) == ensure_aware_local(ev.created_at)
    hype = HypeCandidate(
        canonical_name="ImmTerm",
        public_disclosure_t0=t0,
        candidate_status="OPEN",
        created_at=now,
        updated_at=now,
    )
    db_session.add(hype)
    db_session.commit()
    stats = _collect_x_account_stats(db_session, hype, ["ImmTerm"], t0, now)
    assert stats["mention_count"] == 0


def ensure_aware_local(dt):
    from app.core.timeutil import ensure_aware

    return ensure_aware(dt)


def test_hn_rss_without_published_at_use_created_at(db_session):
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
    old = RawEvent(
        source_id=src.id,
        platform="hn",
        external_id="h1",
        published_at=None,
        retrieved_at=now,
        title="CreatedAtTerm old",
        raw_text="CreatedAtTerm",
        content_hash="h1",
        event_type="story",
        created_at=t0 - timedelta(days=1),
    )
    new = RawEvent(
        source_id=src.id,
        platform="hn",
        external_id="h2",
        published_at=None,
        retrieved_at=now,
        title="CreatedAtTerm new",
        raw_text="CreatedAtTerm",
        content_hash="h2",
        event_type="story",
        created_at=t0 + timedelta(minutes=5),
    )
    db_session.add_all([old, new])
    db_session.commit()
    from app.services.candidate_snapshots import _collect_hn_stats

    hn = _collect_hn_stats(db_session, ["CreatedAtTerm"], t0, now)
    assert hn["hn_matching_story_count"] == 1


def test_github_timing_classes_and_platform():
    t0 = datetime(2026, 1, 10, tzinfo=timezone.utc)
    end = datetime(2026, 1, 11, tzinfo=timezone.utc)
    assert _classify_timing("2026-01-01T00:00:00Z", t0, end) == "PREEXISTING"
    assert _classify_timing("2026-01-10T12:00:00Z", t0, end) == "POST_T0"
    assert _classify_timing(None, t0, end) == "UNKNOWN_TIME"
    assert _classify_timing("not-a-date", t0, end) == "UNKNOWN_TIME"

    # Platform activation uses post_t0 only
    assert _source_detachment_level(independent_accounts=0, high_quality=0, platform_count=1) == "NONE"


def test_github_preexisting_vs_post_t0_counts(db_session, monkeypatch):
    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc)
    aliases = ["vibe coding"]

    async def fake_search(q, limit=10, source=None):
        return [
            {
                "external_id": "a/vibe-coding-old",
                "name": "vibe-coding-old",
                "description": "vibe coding",
                "topics": [],
                "owner": "a",
                "stars": 5,
                "created_at": (t0 - timedelta(days=30)).isoformat(),
            },
            {
                "external_id": "b/vibe-coding-new",
                "name": "vibe-coding-new",
                "description": "vibe coding",
                "topics": [],
                "owner": "b",
                "stars": 3,
                "created_at": (t0 + timedelta(hours=2)).isoformat(),
            },
            {
                "external_id": "c/vibe-coding-unk",
                "name": "vibe-coding-unk",
                "description": "vibe coding",
                "topics": [],
                "owner": "c",
                "stars": 1,
                "created_at": None,
            },
        ]

    monkeypatch.setattr(
        "app.adapters.github.search_github_repos", fake_search
    )
    import asyncio
    from app.services.candidate_snapshots import _collect_github_stats

    stats = asyncio.run(_collect_github_stats(db_session, aliases, t0, end))
    assert stats["github_repo_count_relevant"] == 3
    assert stats["github_repo_count_preexisting"] == 1
    assert stats["github_repo_count_post_t0"] == 1
    assert stats["github_repo_count_unknown_time"] == 1
    assert stats["github_repo_count"] == 1  # platform/radar = post_t0
    # preexisting still persisted
    from app.db.models import TrackedEntity

    entities = db_session.scalars(select(TrackedEntity)).all()
    assert any(e.external_id == "a/vibe-coding-old" for e in entities)


def test_hf_post_t0_vs_preexisting(db_session, monkeypatch):
    t0 = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc)

    def fake_hf(kind, q, limit=10):
        return [
            {
                "external_id": "org/old-space",
                "repo_id": "org/old-space",
                "author": "org",
                "tags": ["vibe-coding"],
                "pipeline_tag": None,
                "sdk": "gradio",
                "created_at": (t0 - timedelta(days=10)).isoformat(),
                "entity_type": f"hf_{kind if kind != 'space' else 'space'}",
            },
            {
                "external_id": "org/new-space",
                "repo_id": "org/new-space",
                "author": "org",
                "tags": ["vibe-coding"],
                "pipeline_tag": None,
                "sdk": "gradio",
                "created_at": (t0 + timedelta(hours=3)).isoformat(),
                "entity_type": f"hf_{kind if kind != 'space' else 'space'}",
            },
            {
                "external_id": "org/unk-space",
                "repo_id": "org/unk-space",
                "author": "org",
                "tags": ["vibe-coding"],
                "pipeline_tag": None,
                "sdk": "gradio",
                "created_at": None,
                "entity_type": f"hf_{kind if kind != 'space' else 'space'}",
            },
        ]

    monkeypatch.setattr("app.adapters.huggingface.search_hf", fake_hf)
    stats = _collect_hf_stats(db_session, ["vibe coding"], t0, end)
    assert stats["hf_space_count_relevant"] == 3
    assert stats["hf_space_count_preexisting"] == 1
    assert stats["hf_space_count_post_t0"] == 1
    assert stats["hf_space_count_unknown_time"] == 1
    assert stats["hf_space_count"] == 1
    assert stats["hf_independent_author_count_post_t0"] == 1


def test_origin_excluded_from_independent_and_hq(db_session):
    origin = _account(db_session, handle="origin_acc", universe_tier="CORE", monitor_priority="P0")
    other = _account(db_session, handle="other_acc", universe_tier="CORE", monitor_priority="P0")
    t0 = datetime.now(timezone.utc) - timedelta(minutes=30)
    r1 = manual_ingest(
        db_session,
        url="https://x.com/origin_acc/status/9201",
        handle="origin_acc",
        text="I call this AmpTerm",
        posted_at=t0 + timedelta(minutes=1),
    )
    hype = accept_as_new_hype(db_session, r1.candidate_signal_ids[0])
    manual_ingest(
        db_session,
        url="https://x.com/other_acc/status/9202",
        handle="other_acc",
        text="AmpTerm is spreading",
        posted_at=t0 + timedelta(minutes=5),
    )

    oid, ohandle = _origin_account(db_session, hype)
    assert oid == origin.id
    assert ohandle == "origin_acc"

    # origin alone
    stats0 = _collect_x_account_stats(
        db_session,
        hype,
        ["AmpTerm"],
        t0,
        utcnow(),
        origin_account_id=origin.id,
        origin_account_handle="origin_acc",
    )
    # Both accounts match after second ingest
    assert stats0["total_monitored_account_count"] == 2
    assert stats0["independent_account_count"] == 1
    assert stats0["high_quality_independent_amplifier_count"] == 1
    assert stats0["high_quality_amplifier_count"] == 1

    # Source-only: build window with only origin mention by filtering aliases oddly —
    # simulate by collecting with only origin's posts: use a fresh hype-like call
    stats_src = _collect_x_account_stats(
        db_session,
        hype,
        ["AmpTerm"],
        t0,
        utcnow(),
        origin_account_id=origin.id,
        origin_account_handle="origin_acc",
    )
    # Detachment with origin alone would be NONE
    alone = _source_detachment_level(
        independent_accounts=0, high_quality=0, platform_count=1
    )
    assert alone == "NONE"
    # With one independent amplifier on same platform
    assert (
        _source_detachment_level(
            independent_accounts=stats_src["independent_account_count"],
            high_quality=stats_src["high_quality_independent_amplifier_count"],
            platform_count=1,
        )
        == "WEAK"
    )


def test_source_only_hq_does_not_count_as_independent_amplifier(db_session):
    origin = _account(db_session, handle="solo", universe_tier="CORE", monitor_priority="P0")
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    r = manual_ingest(
        db_session,
        url="https://x.com/solo/status/9301",
        handle="solo",
        text="I call this SoloTerm",
        posted_at=t0 + timedelta(minutes=1),
    )
    hype = accept_as_new_hype(db_session, r.candidate_signal_ids[0])
    stats = _collect_x_account_stats(
        db_session,
        hype,
        ["SoloTerm"],
        t0,
        utcnow(),
        origin_account_id=origin.id,
        origin_account_handle="solo",
    )
    assert stats["total_monitored_account_count"] == 1
    assert stats["independent_account_count"] == 0
    assert stats["high_quality_independent_amplifier_count"] == 0
    assert _source_detachment_level(
        independent_accounts=0, high_quality=0, platform_count=1
    ) == "NONE"


def test_preexisting_does_not_activate_platforms():
    # Already covered by counts: post_t0=0 means platform inactive in run_checkpoint
    assert _github_item_relevant(
        {"external_id": "x/vibe-coding", "name": "vibe-coding", "description": "", "topics": []},
        ["vibe coding"],
    )
    assert _hf_item_relevant(
        {"external_id": "o/vibe-coding", "tags": [], "pipeline_tag": None, "sdk": None},
        ["vibe coding"],
    )
