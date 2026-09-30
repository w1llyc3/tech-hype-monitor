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
        if self.feed == "topstories":
            return await self._fetch_top_watch(source, since=since)
        return await self._fetch_new_cursor(source, since=since)

    async def _fetch_new_cursor(self, source, since: datetime | None = None) -> list[NormalizedRawEvent]:
        """newstories: incremental discovery via last_seen_id cursor."""
        cursor = dict(source.cursor_json or {})
        feed_cursors = dict(cursor.get("feeds") or {})
        last_seen = int(feed_cursors.get("newstories", {}).get("last_seen_id") or 0)

        async with httpx.AsyncClient(timeout=30.0) as client:
            ids_resp = await client.get(f"{HN_API}/newstories.json")
            ids_resp.raise_for_status()
            story_ids: list[int] = list(ids_resp.json() or [])

            if last_seen:
                candidates = [i for i in story_ids if i > last_seen][: self.max_items]
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
                event = self._normalize(item, rank=None)
                if since and event.published_at and event.published_at < since:
                    continue
                events.append(event)
                max_id = max(max_id, int(story_id))

            feed_cursors["newstories"] = {
                "last_seen_id": max_id,
                "updated_at": utcnow().isoformat(),
            }
            cursor["feeds"] = feed_cursors
            source._pending_cursor = cursor  # type: ignore[attr-defined]
            return events

    async def _fetch_top_watch(self, source, since: datetime | None = None) -> list[NormalizedRawEvent]:
        """topstories: rank/watch model — poll current top-N each run, no last_seen discovery."""
        cursor = dict(source.cursor_json or {})
        feed_cursors = dict(cursor.get("feeds") or {})

        async with httpx.AsyncClient(timeout=30.0) as client:
            ids_resp = await client.get(f"{HN_API}/topstories.json")
            ids_resp.raise_for_status()
            story_ids: list[int] = list(ids_resp.json() or [])
            ranked_ids = story_ids[: self.max_items]

            events: list[NormalizedRawEvent] = []
            for rank, story_id in enumerate(ranked_ids, start=1):
                item = await self._get_item(client, story_id)
                if not item or item.get("type") not in {"story", "job", "poll"}:
                    continue
                event = self._normalize(item, rank=rank)
                if since and event.published_at and event.published_at < since:
                    continue
                events.append(event)

            feed_cursors["topstories"] = {
                "mode": "rank_watch",
                "watched_ids": ranked_ids,
                "watch_size": len(ranked_ids),
                "updated_at": utcnow().isoformat(),
            }
            cursor["feeds"] = feed_cursors
            source._pending_cursor = cursor  # type: ignore[attr-defined]
            return events

    async def _get_item(self, client: httpx.AsyncClient, item_id: int) -> dict[str, Any] | None:
        resp = await client.get(f"{HN_API}/item/{item_id}.json")
        resp.raise_for_status()
        return resp.json()

    def _normalize(self, item: dict[str, Any], rank: int | None) -> NormalizedRawEvent:
        hn_id = item["id"]
        title = item.get("title")
        url = item.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
        author = item.get("by")
        ts = item.get("time")
        published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        text = item.get("text")
        payload = f"{hn_id}|{title}|{url}|{author}|{ts}"
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        metadata: dict[str, Any] = {
            "score": item.get("score"),
            "descendants": item.get("descendants"),
            "hn_id": hn_id,
            "type": item.get("type"),
            "feed": self.feed,
        }
        if rank is not None:
            metadata["rank"] = rank
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
            metadata=metadata,
        )
