"""Phase 2 tests: metrics, HN history, GitHub/HF, APIs, migration chain."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.adapters.base import NormalizedRawEvent
from app.adapters.github import GitHubAdapter, GitHubRateLimitError
from app.core.config import API_ROOT
from app.db.models import Base, HypeCandidate, MetricObservation, RawEvent, Source, TrackedEntity
from app.services.collector import persist_events
from app.services.discovery import persist_github_discovery, persist_hf_discovery
from app.services.metrics import (
    compute_velocity,
    mark_hn_left_top_n,
    record_metric,
    upsert_tracked_entity,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "p2.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _source(db, **kw) -> Source:
    now = datetime.now(timezone.utc)
    data = dict(
        name="HN",
        platform="hn",
        source_type="hacker_news",
        base_url="https://example.com",
        poll_interval_seconds=120,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    data.update(kw)
    s = Source(**data)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_metric_observation_write_rules(db_session, monkeypatch):
    entity = upsert_tracked_entity(
        db_session,
        platform="github",
        entity_type="github_repo",
        external_id="o/r",
    )
    # first
    assert record_metric(db_session, entity, metric_name="stars", metric_value=1) is not None
    # unchanged inside heartbeat — no write
    assert (
        record_metric(
            db_session, entity, metric_name="stars", metric_value=1, heartbeat_seconds=3600
        )
        is None
    )
    # changed — write
    assert record_metric(db_session, entity, metric_name="stars", metric_value=2) is not None
    # heartbeat after interval
    latest = db_session.scalars(
        select(MetricObservation).order_by(MetricObservation.id.desc())
    ).first()
    latest.observed_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()
    assert (
        record_metric(
            db_session, entity, metric_name="stars", metric_value=2, heartbeat_seconds=3600
        )
        is not None
    )
    assert (
        db_session.scalar(select(MetricObservation).where(MetricObservation.metric_name == "stars"))
        is not None
    )
    assert (
        len(
            db_session.scalars(
                select(MetricObservation).where(MetricObservation.metric_name == "stars")
            ).all()
        )
        == 3
    )


def test_hn_history_and_feeds_seen(db_session):
    source = _source(db_session)
    e1 = NormalizedRawEvent(
        platform="hn",
        external_id="1",
        title="A",
        canonical_url="https://news.ycombinator.com/item?id=1",
        content_hash="h1",
        event_type="story",
        metadata={"score": 10, "descendants": 2, "feeds_seen": ["newstories"]},
    )
    persist_events(db_session, source, [e1], feed="newstories")
    db_session.commit()
    e2 = NormalizedRawEvent(
        platform="hn",
        external_id="1",
        title="A",
        canonical_url="https://news.ycombinator.com/item?id=1",
        content_hash="h1",
        event_type="story",
        metadata={
            "score": 20,
            "descendants": 5,
            "rank": 3,
            "latest_top_rank": 3,
            "feeds_seen": ["topstories"],
        },
    )
    persist_events(db_session, source, [e2], feed="topstories")
    db_session.commit()

    entity = db_session.scalar(select(TrackedEntity).where(TrackedEntity.external_id == "1"))
    assert entity is not None
    feeds = (entity.metadata_json or {}).get("feeds_seen") or []
    assert "newstories" in feeds and "topstories" in feeds

    scores = db_session.scalars(
        select(MetricObservation)
        .where(
            MetricObservation.tracked_entity_id == entity.id,
            MetricObservation.metric_name == "score",
        )
        .order_by(MetricObservation.observed_at.asc())
    ).all()
    assert [s.metric_value for s in scores] == [10.0, 20.0]

    ranks = db_session.scalars(
        select(MetricObservation).where(
            MetricObservation.tracked_entity_id == entity.id,
            MetricObservation.metric_name == "rank",
        )
    ).all()
    assert any(r.metric_value == 3.0 for r in ranks)

    # leaving top-N writes one null
    mark_hn_left_top_n(db_session, set())
    db_session.commit()
    nulls = [
        r
        for r in db_session.scalars(
            select(MetricObservation).where(
                MetricObservation.tracked_entity_id == entity.id,
                MetricObservation.metric_name == "rank",
            )
        ).all()
        if r.metric_value is None
    ]
    assert len(nulls) == 1
    assert (nulls[0].metadata_json or {}).get("state") == "left_top_n"
    # second leave does not duplicate
    mark_hn_left_top_n(db_session, set())
    db_session.commit()
    nulls2 = [
        r
        for r in db_session.scalars(
            select(MetricObservation).where(
                MetricObservation.tracked_entity_id == entity.id,
                MetricObservation.metric_name == "rank",
            )
        ).all()
        if r.metric_value is None
    ]
    assert len(nulls2) == 1

    # newstories must not erase topstories
    raw = db_session.scalar(select(RawEvent).where(RawEvent.external_id == "1"))
    assert "topstories" in ((raw.metadata_json or {}).get("feeds_seen") or [])


@pytest.mark.asyncio
async def test_github_rate_limit_and_no_token(monkeypatch, db_session):
    source = _source(
        db_session,
        name="GH",
        platform="github",
        source_type="github_repo",
        cursor_json={"config": {"repo": "openai/whisper"}},
    )

    class FakeResp:
        status_code = 403
        text = "API rate limit exceeded"
        headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1700000000",
            "X-RateLimit-Limit": "60",
        }

        def raise_for_status(self):
            raise AssertionError("should not raise_for_status on handled 403")

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr("app.adapters.github.httpx.AsyncClient", FakeClient)
    adapter = GitHubAdapter()
    with pytest.raises(GitHubRateLimitError):
        await adapter.fetch(source)
    runtime = (source._pending_cursor or {}).get("runtime")  # type: ignore[attr-defined]
    assert runtime["rate_limit_remaining"] == 0


def test_github_discovery_dedupe_and_star_change(db_session):
    items = [
        {
            "external_id": "acme/demo",
            "name": "demo",
            "owner": "acme",
            "url": "https://github.com/acme/demo",
            "stars": 10,
            "forks": 1,
        }
    ]
    ids1 = persist_github_discovery(db_session, items)
    ids2 = persist_github_discovery(db_session, items)
    assert ids1 == ids2
    assert (
        db_session.scalars(select(TrackedEntity).where(TrackedEntity.external_id == "acme/demo"))
        .all()
        .__len__()
        == 1
    )
    items[0]["stars"] = 15
    persist_github_discovery(db_session, items)
    stars = db_session.scalars(
        select(MetricObservation)
        .where(MetricObservation.metric_name == "stars")
        .order_by(MetricObservation.id.asc())
    ).all()
    assert [s.metric_value for s in stars] == [10.0, 15.0]


def test_hf_discovery_null_downloads(db_session):
    items = [
        {
            "external_id": "org/model",
            "entity_type": "hf_model",
            "url": "https://huggingface.co/org/model",
            "likes": 3,
            "downloads": None,
        }
    ]
    persist_hf_discovery(db_session, items)
    persist_hf_discovery(db_session, items)
    assert (
        len(db_session.scalars(select(TrackedEntity).where(TrackedEntity.external_id == "org/model")).all())
        == 1
    )
    downloads = db_session.scalars(
        select(MetricObservation).where(MetricObservation.metric_name == "downloads")
    ).all()
    assert downloads
    assert downloads[0].metric_value is None


def test_velocity_and_metric_order(db_session):
    entity = upsert_tracked_entity(
        db_session, platform="github", entity_type="github_repo", external_id="a/b"
    )
    now = datetime.now(timezone.utc)
    for i, val in enumerate([10, 20, 30]):
        db_session.add(
            MetricObservation(
                tracked_entity_id=entity.id,
                observed_at=now - timedelta(hours=24 - i * 8),
                metric_name="stars",
                metric_value=float(val),
                created_at=now,
            )
        )
    db_session.commit()
    from fastapi.testclient import TestClient
    import app.core.config as config_mod
    from app.db import session as session_mod
    from app.main import app

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(config_mod.settings, "scheduler_enabled", False)

    def _override():
        yield db_session

    app.dependency_overrides[session_mod.get_db] = _override
    with TestClient(app) as client:
        res = client.get(f"/api/entities/{entity.id}/metrics")
        assert res.status_code == 200
        series = res.json()["series"]["stars"]
        assert [p["value"] for p in series] == [10.0, 20.0, 30.0]
        vel = client.get(f"/api/entities/{entity.id}/velocity", params={"metric": "stars"})
        assert vel.status_code == 200
        body = vel.json()
        assert body["delta"] == 20.0
        empty = compute_velocity(db_session, entity.id, "missing")
        assert empty["delta"] is None
    app.dependency_overrides.clear()
    monkeypatch.undo()


def test_migration_0001_to_0003(tmp_path: Path):
    db_path = tmp_path / "migrate.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url, future=True)
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "0001_phase1")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as db:
        now = datetime.now(timezone.utc)
        src = Source(
            name="S",
            platform="hn",
            source_type="hacker_news",
            base_url="https://x",
            poll_interval_seconds=120,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        db.add(src)
        db.flush()
        db.add(
            RawEvent(
                source_id=src.id,
                platform="hn",
                external_id="9",
                retrieved_at=now,
                content_hash="c",
                event_type="story",
                title="t",
                created_at=now,
            )
        )
        db.add(
            HypeCandidate(
                canonical_name="c1",
                candidate_status="UNKNOWN",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    command.upgrade(cfg, "0002_phase1_1")
    command.upgrade(cfg, "0003_phase2_metrics_github_hf")

    with Session() as db:
        assert db.scalar(select(Source).where(Source.name == "S")) is not None
        assert db.scalar(select(RawEvent).where(RawEvent.external_id == "9")) is not None
        assert db.scalar(select(HypeCandidate).where(HypeCandidate.canonical_name == "c1")) is not None
        tables = db.execute(text("select name from sqlite_master where type='table'")).fetchall()
        names = {t[0] for t in tables}
        assert "tracked_entities" in names
        assert "metric_observations" in names
    engine.dispose()
