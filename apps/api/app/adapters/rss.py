from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import mktime

import feedparser
import httpx

from app.adapters.base import NormalizedRawEvent, SourceAdapter


class RSSAdapter(SourceAdapter):
    name = "official_rss"

    def __init__(self, max_entries: int = 100) -> None:
        self.max_entries = max_entries

    async def fetch(self, source, since: datetime | None = None) -> list[NormalizedRawEvent]:
        if not source.feed_url:
            raise ValueError(f"Source {source.name} has no feed_url")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(source.feed_url)
            resp.raise_for_status()
            body = resp.text

        parsed = feedparser.parse(body)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise RuntimeError(f"Failed to parse RSS feed: {getattr(parsed, 'bozo_exception', 'unknown')}")

        events: list[NormalizedRawEvent] = []
        for entry in parsed.entries[: self.max_entries]:
            event = self._normalize(entry, platform=source.platform)
            if since and event.published_at and event.published_at < since:
                continue
            events.append(event)
        return events

    def _normalize(self, entry, platform: str) -> NormalizedRawEvent:
        title = getattr(entry, "title", None) or None
        link = getattr(entry, "link", None) or None
        author = getattr(entry, "author", None) or None
        summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or None
        external_id = (
            getattr(entry, "id", None)
            or getattr(entry, "guid", None)
            or link
        )
        published_at = self._parse_published(entry)
        payload = f"{external_id}|{title}|{link}|{summary}"
        content_hash = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
        return NormalizedRawEvent(
            platform=platform,
            external_id=str(external_id) if external_id else None,
            author=author,
            published_at=published_at,
            canonical_url=link,
            title=title,
            raw_text=summary,
            content_hash=content_hash,
            event_type="rss_item",
            metadata={
                "guid": getattr(entry, "guid", None),
                "tags": [t.get("term") for t in getattr(entry, "tags", []) if isinstance(t, dict)],
            },
        )

    def _parse_published(self, entry) -> datetime | None:
        if getattr(entry, "published_parsed", None):
            return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
        if getattr(entry, "updated_parsed", None):
            return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
        for key in ("published", "updated"):
            raw = getattr(entry, key, None)
            if not raw:
                continue
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (TypeError, ValueError, IndexError):
                continue
        return None
