"""Seed sources from config/sources.yaml into SQLite."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from sqlalchemy import select

# Allow `python -m app.db.seed` from apps/api
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402
from app.core.timeutil import utcnow  # noqa: E402
from app.db.models import Source  # noqa: E402
from app.db.session import SessionLocal, run_migrations  # noqa: E402


def seed_sources(config_path: Path | None = None) -> int:
    path = Path(config_path or settings.sources_config_path)
    with path.open(encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    items = payload.get("sources") or []
    now = utcnow()
    created = 0
    configured_names = {item["name"] for item in items}

    with SessionLocal() as db:
        for item in items:
            name = item["name"]
            existing = db.scalar(select(Source).where(Source.name == name))
            if existing:
                existing.platform = item["platform"]
                existing.source_type = item["source_type"]
                existing.base_url = item["base_url"]
                existing.feed_url = item.get("feed_url")
                existing.poll_interval_seconds = int(item.get("poll_interval_seconds", 600))
                existing.enabled = bool(item.get("enabled", False))
                existing.updated_at = now
                if item.get("metadata"):
                    cursor = dict(existing.cursor_json or {})
                    cursor["config"] = item["metadata"]
                    existing.cursor_json = cursor
                continue

            cursor = {"config": item["metadata"]} if item.get("metadata") else None
            db.add(
                Source(
                    name=name,
                    platform=item["platform"],
                    source_type=item["source_type"],
                    base_url=item["base_url"],
                    feed_url=item.get("feed_url"),
                    poll_interval_seconds=int(item.get("poll_interval_seconds", 600)),
                    enabled=bool(item.get("enabled", False)),
                    cursor_json=cursor,
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1

        # Disable sources removed from config (e.g. broken feed URLs).
        for orphan in db.scalars(select(Source)).all():
            if orphan.name not in configured_names and orphan.enabled:
                orphan.enabled = False
                orphan.updated_at = now

        db.commit()
    return created


def main() -> None:
    run_migrations()
    n = seed_sources()
    print(f"Seed complete. New sources inserted: {n}")


if __name__ == "__main__":
    main()
