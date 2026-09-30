from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from app.adapters.base import NormalizedRawEvent, SourceAdapter
from app.core.timeutil import utcnow

HN_API = "https://hacker-news.firebaseio.com/v0"


class HNAdapter(SourceAdapter):
    name = "hacker_news"

    def __init__(self, feed: str = "newstories", max_items: int = 40) -> None:
        if feed not in {"newstories", "topstories"}:
            raise ValueError(f"Unsupported HN feed: {feed}")
        self.feed = feed
        self.max_items = max_items

    async def fetch(self, source, since: datetime | None = None) -> list[NormalizedRawEvent]:
        cursor = dict(source.cursor_json or {})
        feed_cursors = dict(cursor.get("feeds") or {})
        last_seen = int(feed_cursors.get(self.feed, {}).get("last_seen_id") or 0)

        async with httpx.AsyncClient(timeout=30.0) as client:
            ids_resp = await client.get(f"{HN_API}/{self.feed}.json")
            ids_resp.raise_for_status()
            story_ids: list[int] = list(ids_resp.json() or [])

            # Prefer items newer than cursor; if first run, only take a small window.
            if last_seen:
                candidates = [i for i in story_ids if i > last_seen][: self.max_items]
                # Also refresh a slice of recently seen top/new items for score updates.
                refresh_ids = [i for i in story_ids if i <= last_seen][: min(15, self.max_items)]
                fetch_ids = list(dict.fromkeys(candidates + refresh_ids))
            else:
                fetch_ids = story_ids[: self.max_items]

            events: list[NormalizedRawEvent] = []
            max_id = last_seen
            for story_id in fetch_ids:
                item = await self._get_item(client, story_id)
                if not item or item.get("type") not in {"story", "job", "poll"}:
                    continue
                event = self._normalize(item)
                if since and event.published_at and event.published_at < since:
                    continue
                events.append(event)
                max_id = max(max_id, int(story_id))

            feed_cursors[self.feed] = {
                "last_seen_id": max_id,
                "updated_at": utcnow().isoformat(),
            }
            cursor["feeds"] = feed_cursors
            # Attach updated cursor for collector to persist.
            source._pending_cursor = cursor  # type: ignore[attr-defined]
            return events

    async def _get_item(self, client: httpx.AsyncClient, item_id: int) -> dict[str, Any] | None:
        resp = await client.get(f"{HN_API}/item/{item_id}.json")
        resp.raise_for_status()
        return resp.json()

    def _normalize(self, item: dict[str, Any]) -> NormalizedRawEvent:
        hn_id = item["id"]
        title = item.get("title")
        url = item.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
        author = item.get("by")
        ts = item.get("time")
        published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        text = item.get("text")
        payload = f"{hn_id}|{title}|{url}|{author}|{ts}"
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return NormalizedRawEvent(
            platform="hn",
            external_id=str(hn_id),
            author=author,
            published_at=published,
            canonical_url=url,
            title=title,
            raw_text=text,
            content_hash=content_hash,
            event_type=item.get("type") or "story",
            metadata={
                "score": item.get("score"),
                "descendants": item.get("descendants"),
                "hn_id": hn_id,
                "type": item.get("type"),
                "feed": self.feed,
            },
        )
