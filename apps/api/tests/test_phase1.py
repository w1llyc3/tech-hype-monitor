from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.base import NormalizedRawEvent
from app.adapters.rss import RSSAdapter
from app.adapters.stubs import GitHubAdapter
from app.db.models import Base, RawEvent, Source
from app.services.collector import persist_events, poll_source
from app.services.health import compute_source_status


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _source(db, **overrides) -> Source:
    now = datetime.now(timezone.utc)
    data = dict(
        name="Test HN",
        platform="hn",
        source_type="hacker_news",
        base_url="https://hacker-news.firebaseio.com",
        feed_url=None,
        poll_interval_seconds=120,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    data.update(overrides)
    s = Source(**data)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_dedupe_same_hn_story_twice(db_session):
    source = _source(db_session)
    event = NormalizedRawEvent(
        platform="hn",
        external_id="999001",
        author="pg",
        published_at=datetime.now(timezone.utc),
        canonical_url="https://example.com/a",
        title="Hello",
        raw_text=None,
        content_hash="abc123",
        event_type="story",
        metadata={"score": 1, "descendants": 0, "hn_id": 999001},
    )
    i1, d1, _ = persist_events(db_session, source, [event])
    db_session.commit()
    i2, d2, u2 = persist_events(
        db_session,
        source,
        [
            NormalizedRawEvent(
                platform="hn",
                external_id="999001",
                author="pg",
                published_at=event.published_at,
                canonical_url="https://example.com/a",
                title="Hello",
                raw_text=None,
                content_hash="abc123",
                event_type="story",
                metadata={"score": 10, "descendants": 2, "hn_id": 999001},
            )
        ],
    )
    db_session.commit()
    count = db_session.scalar(select(RawEvent).where(RawEvent.external_id == "999001"))
    assert i1 == 1 and d1 == 0
    assert i2 == 0 and d2 == 1
    assert u2 == 1
    assert db_session.scalars(select(RawEvent)).all().__len__() == 1
    assert count.metadata_json["score"] == 10


@pytest.mark.asyncio
async def test_adapter_failure_does_not_kill_other_jobs(db_session, monkeypatch):
    good = _source(db_session, name="Good RSS", platform="official_rss", source_type="official_rss", feed_url="https://example.com/good.xml")
    bad = _source(db_session, name="Bad RSS", platform="official_rss", source_type="official_rss", feed_url="https://example.com/bad.xml")

    async def fake_fetch(self, source, since=None):
        if "bad" in (source.feed_url or ""):
            raise RuntimeError("feed down")
        return [
            NormalizedRawEvent(
                platform="official_rss",
                external_id="e1",
                title="ok",
                canonical_url="https://example.com/ok",
                content_hash="hash-ok",
                event_type="rss_item",
            )
        ]

    monkeypatch.setattr(RSSAdapter, "fetch", fake_fetch)

    bad_result = await poll_source(db_session, bad)
    db_session.refresh(good)
    good_result = await poll_source(db_session, good)

    assert bad_result.error is not None
    assert good_result.error is None
    assert good_result.inserted == 1
    assert db_session.get(Source, bad.id).last_error is not None
    assert db_session.get(Source, good.id).last_success_at is not None


@pytest.mark.asyncio
async def test_source_health_updates_on_success(db_session, monkeypatch):
    source = _source(
        db_session,
        name="RSS Health",
        platform="official_rss",
        source_type="official_rss",
        feed_url="https://example.com/feed.xml",
    )
    assert source.last_success_at is None

    async def fake_fetch(self, source, since=None):
        return []

    monkeypatch.setattr(RSSAdapter, "fetch", fake_fetch)
    result = await poll_source(db_session, source)
    db_session.refresh(source)
    assert result.error is None
    assert source.last_success_at is not None
    assert compute_source_status(source) in {"Healthy", "Stale"}


def test_event_api_filterable(db_session, monkeypatch):
    from fastapi.testclient import TestClient

    import app.core.config as config_mod
    from app.db import session as session_mod
    from app.main import app

    monkeypatch.setattr(config_mod.settings, "scheduler_enabled", False)

    source = _source(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        RawEvent(
            source_id=source.id,
            platform="hn",
            external_id="42",
            author="alice",
            published_at=now,
            retrieved_at=now,
            canonical_url="https://example.com/x",
            title="filter-me-please",
            raw_text="body",
            content_hash="h42",
            event_type="story",
            metadata_json={"score": 3},
            created_at=now,
        )
    )
    db_session.commit()

    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[session_mod.get_db] = _override
    with TestClient(app) as client:
        res = client.get("/api/events", params={"q": "filter-me"})
        assert res.status_code == 200
        data = res.json()
        assert any(e["title"] == "filter-me-please" for e in data)
        matched = next(e for e in data if e["title"] == "filter-me-please")
        one = client.get(f"/api/events/{matched['id']}")
        assert one.status_code == 200
        assert one.json()["external_id"] == "42"
    app.dependency_overrides.clear()


def test_restart_persistence(tmp_path: Path):
    db_path = tmp_path / "persist.db"
    url = f"sqlite:///{db_path.as_posix()}"

    def make_session():
        engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

        @event.listens_for(engine, "connect")
        def _pragma(dbapi_connection, _):  # noqa: ANN001
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)(), engine

    session1, engine1 = make_session()
    source = _source(session1, name="Persist HN")
    raw = NormalizedRawEvent(
        platform="hn",
        external_id="777",
        title="persisted",
        canonical_url="https://example.com/p",
        content_hash="ph",
        event_type="story",
    )
    persist_events(session1, source, [raw])
    session1.commit()
    session1.close()
    engine1.dispose()

    session2, engine2 = make_session()
    rows = session2.scalars(select(RawEvent).where(RawEvent.external_id == "777")).all()
    assert len(rows) == 1
    assert rows[0].title == "persisted"
    session2.close()
    engine2.dispose()


def test_stub_adapter_disabled():
    stub = GitHubAdapter()
    assert stub.is_enabled() is False
