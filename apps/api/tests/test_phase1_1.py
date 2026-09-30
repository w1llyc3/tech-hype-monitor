"""Phase 1.1 — Data Integrity Patch tests."""

from __future__ import annotations

from calendar import timegm
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.base import NormalizedRawEvent
from app.adapters.hn import HNAdapter
from app.adapters.rss import RSSAdapter
from app.db.models import Base, HypeCandidate, RawEvent, Source
from app.services.collector import persist_events
from app.services.scheduler import last_activity_at


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "phase11.db"
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
        name="S1",
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


def test_rss_timegm_not_mktime():
    adapter = RSSAdapter()
    # struct_time as UTC noon on 2020-06-15
    parsed = (2020, 6, 15, 12, 0, 0, 0, 0, 0)
    entry = SimpleNamespace(published_parsed=parsed, updated_parsed=None)
    dt = adapter._parse_published(entry)
    assert dt is not None
    assert dt == datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)
    assert dt.hour == 12
    from pathlib import Path as P

    src = P(__file__).resolve().parents[1] / "app" / "adapters" / "rss.py"
    text = src.read_text(encoding="utf-8")
    assert "timegm" in text
    assert "mktime" not in text


def test_scheduler_last_activity_uses_max():
    older = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    source = SimpleNamespace(last_success_at=older, last_error_at=newer)
    assert last_activity_at(source) == newer
    source2 = SimpleNamespace(last_success_at=newer, last_error_at=older)
    assert last_activity_at(source2) == newer
    source3 = SimpleNamespace(last_success_at=None, last_error_at=None)
    assert last_activity_at(source3) is None


def test_dedupe_is_source_aware(db_session):
    a = _source(db_session, name="Feed A", platform="official_rss", source_type="official_rss")
    b = _source(db_session, name="Feed B", platform="official_rss", source_type="official_rss")
    event = NormalizedRawEvent(
        platform="official_rss",
        external_id="same-id",
        title="Shared GUID",
        canonical_url="https://example.com/post",
        content_hash="hash-shared",
        event_type="rss_item",
    )
    i1, d1, _ = persist_events(db_session, a, [event])
    i2, d2, _ = persist_events(db_session, b, [event])
    db_session.commit()
    assert i1 == 1 and d1 == 0
    assert i2 == 1 and d2 == 0
    rows = db_session.scalars(select(RawEvent).where(RawEvent.external_id == "same-id")).all()
    assert len(rows) == 2
    assert {r.source_id for r in rows} == {a.id, b.id}

    # Same source still dedupes
    i3, d3, _ = persist_events(db_session, a, [event])
    db_session.commit()
    assert i3 == 0 and d3 == 1
    assert db_session.scalars(select(RawEvent)).all().__len__() == 2


def test_canonical_name_not_unique(db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            HypeCandidate(
                canonical_name="same-name",
                candidate_status="UNKNOWN",
                created_at=now,
                updated_at=now,
            ),
            HypeCandidate(
                canonical_name="same-name",
                candidate_status="UNKNOWN",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()
    rows = db_session.scalars(
        select(HypeCandidate).where(HypeCandidate.canonical_name == "same-name")
    ).all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_hn_topstories_rank_watch_model(monkeypatch):
    adapter = HNAdapter(feed="topstories", max_items=3)
    source = SimpleNamespace(cursor_json={}, _pending_cursor=None)

    async def fake_get(self_client, url):
        if url.endswith("/topstories.json"):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: [101, 102, 103, 104])
        item_id = int(url.rstrip(".json").split("/")[-1])
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "id": item_id,
                "type": "story",
                "title": f"Story {item_id}",
                "by": "user",
                "time": 1_700_000_000,
                "score": 10,
                "descendants": 1,
                "url": f"https://example.com/{item_id}",
            },
        )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return await fake_get(self, url)

    monkeypatch.setattr("app.adapters.hn.httpx.AsyncClient", FakeClient)
    events = await adapter.fetch(source)
    assert len(events) == 3
    assert [e.metadata["rank"] for e in events] == [1, 2, 3]
    assert all(e.metadata["feeds_seen"] == ["topstories"] for e in events)
    cursor = source._pending_cursor
    assert cursor["feeds"]["topstories"]["mode"] == "rank_watch"
    assert cursor["feeds"]["topstories"]["watched_ids"] == [101, 102, 103]


def test_production_init_db_does_not_create_all():
    from pathlib import Path as P

    session_src = (P(__file__).resolve().parents[1] / "app" / "db" / "session.py").read_text(
        encoding="utf-8"
    )
    main_src = (P(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "metadata.create_all" not in session_src
    assert "run_migrations" in session_src
    assert "metadata.create_all" not in main_src
    assert "run_migrations" in main_src


def test_model_raw_event_unique_is_source_aware():
    args = RawEvent.__table_args__
    uniques = [a for a in args if getattr(a, "name", None) == "uq_raw_events_source_external"]
    assert uniques
    assert list(uniques[0].columns.keys()) == ["source_id", "external_id"]


def test_hype_candidate_canonical_name_has_no_unique():
    col = HypeCandidate.__table__.c.canonical_name
    assert col.unique is False or col.unique is None
    # No table-level unique solely on canonical_name
    for uq in HypeCandidate.__table__.constraints:
        if getattr(uq, "columns", None) is None:
            continue
        cols = [c.name for c in uq.columns]
        if cols == ["canonical_name"] and uq.__class__.__name__ == "UniqueConstraint":
            raise AssertionError("canonical_name should not be unique")
