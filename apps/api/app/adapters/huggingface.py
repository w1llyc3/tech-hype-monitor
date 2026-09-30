from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from app.adapters.base import NormalizedRawEvent, SourceAdapter
from app.core.config import settings

EntityKind = Literal["model", "dataset", "space"]


def _hf_token() -> str | None:
    token = (settings.hf_token or "").strip()
    return token or None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _to_event(kind: EntityKind, item: Any) -> NormalizedRawEvent:
    repo_id = getattr(item, "id", None) or getattr(item, "modelId", None) or getattr(item, "datasetId", None)
    if isinstance(item, dict):
        repo_id = item.get("id") or item.get("modelId") or item.get("datasetId") or repo_id
        likes = item.get("likes")
        downloads = item.get("downloads")
        author = item.get("author")
        tags = item.get("tags") or []
        pipeline_tag = item.get("pipeline_tag")
        sdk = item.get("sdk")
        last_modified = item.get("lastModified") or item.get("last_modified")
        created_at = item.get("createdAt") or item.get("created_at")
        private = item.get("private")
        gated = item.get("gated")
    else:
        likes = getattr(item, "likes", None)
        downloads = getattr(item, "downloads", None)
        author = getattr(item, "author", None)
        tags = list(getattr(item, "tags", None) or [])
        pipeline_tag = getattr(item, "pipeline_tag", None)
        sdk = getattr(item, "sdk", None)
        last_modified = getattr(item, "lastModified", None) or getattr(item, "last_modified", None)
        created_at = getattr(item, "createdAt", None) or getattr(item, "created_at", None)
        private = getattr(item, "private", None)
        gated = getattr(item, "gated", None)

    repo_id = str(repo_id)
    entity_type = {"model": "hf_model", "dataset": "hf_dataset", "space": "hf_space"}[kind]
    url = f"https://huggingface.co/{repo_id}"
    if kind == "dataset":
        url = f"https://huggingface.co/datasets/{repo_id}" if not repo_id.startswith("datasets/") else f"https://huggingface.co/{repo_id}"
    if kind == "space":
        url = f"https://huggingface.co/spaces/{repo_id}" if "/" in repo_id else f"https://huggingface.co/spaces/{repo_id}"

    payload = f"{kind}|{repo_id}|{likes}|{downloads}|{last_modified}"
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    meta: dict[str, Any] = {
        "author": author,
        "pipeline_tag": pipeline_tag,
        "tags": tags,
        "last_modified": str(last_modified) if last_modified else None,
        "created_at": str(created_at) if created_at else None,
        "sdk": sdk,
        "private": private,
        "gated": gated,
        "likes": likes,
        # Keep missing downloads as None, never coerce to 0.
        "downloads": downloads if downloads is not None else None,
        "kind": kind,
    }
    return NormalizedRawEvent(
        platform="huggingface",
        external_id=repo_id,
        author=author,
        published_at=_parse_dt(created_at),
        canonical_url=url,
        title=repo_id,
        raw_text=None,
        content_hash=content_hash,
        event_type=entity_type,
        metadata=meta,
    )


def _normalize_search_item(kind: EntityKind, item: Any) -> dict[str, Any]:
    ev = _to_event(kind, item)
    meta = ev.metadata or {}
    return {
        "platform": "huggingface",
        "entity_type": ev.event_type,
        "external_id": ev.external_id,
        "repo_id": ev.external_id,
        "author": meta.get("author"),
        "url": ev.canonical_url,
        "last_modified": meta.get("last_modified"),
        "likes": meta.get("likes"),
        "downloads": meta.get("downloads"),
        "tags": meta.get("tags") or [],
        "pipeline_tag": meta.get("pipeline_tag"),
        "sdk": meta.get("sdk"),
    }


class HuggingFaceAdapter(SourceAdapter):
    name = "huggingface"

    def is_enabled(self) -> bool:
        return True

    async def fetch(self, source, since=None) -> list[NormalizedRawEvent]:
        st = (source.source_type or "").lower()
        meta = (source.cursor_json or {}).get("config") or {}
        author = meta.get("author") or meta.get("org")
        if not author:
            raise ValueError(f"HF source {source.name} missing author/org in config metadata")

        if st == "hf_org_models":
            return self._list_author("model", author)
        if st == "hf_org_datasets":
            return self._list_author("dataset", author)
        if st == "hf_org_spaces":
            return self._list_author("space", author)
        raise ValueError(f"Unsupported HF source_type: {source.source_type}")

    def _list_author(self, kind: EntityKind, author: str) -> list[NormalizedRawEvent]:
        from huggingface_hub import HfApi

        api = HfApi(token=_hf_token())
        if kind == "model":
            items = api.list_models(author=author, sort="last_modified", limit=30)
        elif kind == "dataset":
            items = api.list_datasets(author=author, sort="last_modified", limit=30)
        else:
            items = api.list_spaces(author=author, sort="last_modified", limit=30)
        return [_to_event(kind, it) for it in items]


def search_hf(kind: EntityKind, query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    from huggingface_hub import HfApi

    q = query.strip()
    if not q:
        return []
    limit = max(1, min(limit, 50))
    api = HfApi(token=_hf_token())
    if kind == "model":
        items = api.list_models(search=q, sort="likes", limit=limit)
    elif kind == "dataset":
        items = api.list_datasets(search=q, sort="likes", limit=limit)
    else:
        items = api.list_spaces(search=q, sort="likes", limit=limit)
    return [_normalize_search_item(kind, it) for it in items]
