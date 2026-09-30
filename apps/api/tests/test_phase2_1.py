"""Phase 2.1 — Discovery & Metric Integrity Patch tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.adapters.github import _repo_event, search_github_repos
from app.db.models import Base, MetricObservation, Source, TrackedEntity
from app.services.collector import persist_events
from app.services.discovery import persist_github_discovery


@pytest.fixture()
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'p21.db').as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_github_best_match_omits_sort(monkeypatch):
    captured: dict = {}

    class FakeResp:
        status_code = 200
        headers = {
            "X-RateLimit-Remaining": "50",
            "X-RateLimit-Limit": "60",
            "X-RateLimit-Reset": "1700000000",
        }
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": []}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = dict(params or {})
            return FakeResp()

    monkeypatch.setattr("app.adapters.github.httpx.AsyncClient", FakeClient)
    await search_github_repos("vibe coding", limit=10)
    assert "sort" not in captured["params"]
    assert "order" not in captured["params"]
    assert captured["params"]["q"] == "vibe coding"
    assert captured["params"]["per_page"] == 10


def test_org_list_does_not_write_subscribers_from_watchers(db_session):
    now = datetime.now(timezone.utc)
    source = Source(
        name="Org",
        platform="github",
        source_type="github_org",
        base_url="https://github.com/acme",
        poll_interval_seconds=3600,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(source)
    db_session.commit()

    event = _repo_event(
        {
            "full_name": "acme/demo",
            "name": "demo",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/demo",
            "description": "x",
            "stargazers_count": 100,
            "forks_count": 2,
            "watchers_count": 100,  # must NOT become subscribers
            "open_issues_count": 1,
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "created_at": "2023-01-01T00:00:00Z",
            "topics": [],
        }
    )
    assert "subscribers" not in (event.metadata or {})
    assert event.metadata["stars"] == 100
    persist_events(db_session, source, [event])
    db_session.commit()
    entity = db_session.scalar(
        select(TrackedEntity).where(TrackedEntity.external_id == "acme/demo")
    )
    assert entity is not None
    subs = db_session.scalars(
        select(MetricObservation).where(
            MetricObservation.tracked_entity_id == entity.id,
            MetricObservation.metric_name == "subscribers",
        )
    ).all()
    assert subs == []


def test_repo_detail_records_subscribers(db_session):
    now = datetime.now(timezone.utc)
    source = Source(
        name="Repo",
        platform="github",
        source_type="github_repo",
        base_url="https://github.com/acme/demo",
        poll_interval_seconds=3600,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(source)
    db_session.commit()

    event = _repo_event(
        {
            "full_name": "acme/demo",
            "name": "demo",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/demo",
            "stargazers_count": 10,
            "forks_count": 1,
            "subscribers_count": 7,
            "watchers_count": 99,
            "open_issues_count": 0,
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "created_at": "2023-01-01T00:00:00Z",
            "topics": [],
        }
    )
    assert event.metadata["subscribers"] == 7
    persist_events(db_session, source, [event])
    db_session.commit()
    entity = db_session.scalar(
        select(TrackedEntity).where(TrackedEntity.external_id == "acme/demo")
    )
    row = db_session.scalar(
        select(MetricObservation).where(
            MetricObservation.tracked_entity_id == entity.id,
            MetricObservation.metric_name == "subscribers",
        )
    )
    assert row is not None
    assert row.metric_value == 7.0


def test_discovery_returns_entity_id_even_when_name_misses_query(db_session, monkeypatch):
    from fastapi.testclient import TestClient

    import app.core.config as config_mod
    from app.db import session as session_mod
    from app.main import app

    monkeypatch.setattr(config_mod.settings, "scheduler_enabled", False)

    async def fake_search(query, *, limit=30, source=None):
        return [
            {
                "platform": "github",
                "entity_type": "github_repo",
                "external_id": "acme/foo",
                "name": "foo",
                "owner": "acme",
                "url": "https://github.com/acme/foo",
                "description": "vibe coding toolkit",
                "stars": 12,
                "forks": 1,
                "language": "Python",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-06-01T00:00:00Z",
                "pushed_at": "2024-06-01T00:00:00Z",
                "topics": [],
            }
        ]

    monkeypatch.setattr("app.adapters.github.search_github_repos", fake_search)

    def _override():
        yield db_session

    app.dependency_overrides[session_mod.get_db] = _override
    with TestClient(app) as client:
        res = client.get("/api/discovery/github", params={"q": "vibe coding"})
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["external_id"] == "acme/foo"
        assert "entity_id" in data[0]
        entity_id = data[0]["entity_id"]
        assert isinstance(entity_id, int)
        # Detail must resolve by entity_id, not by name containing the query.
        detail = client.get(f"/api/entities/{entity_id}")
        assert detail.status_code == 200
        assert detail.json()["external_id"] == "acme/foo"
        # Name does not contain query; description does — persistence still works.
        assert "vibe" not in data[0]["name"].lower()
        assert "vibe coding" in (data[0]["description"] or "").lower()
    app.dependency_overrides.clear()
