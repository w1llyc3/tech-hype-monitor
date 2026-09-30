from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.base import NormalizedRawEvent, SourceAdapter
from app.core.config import settings
from app.core.timeutil import utcnow

GITHUB_API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubRateLimitError(RuntimeError):
    def __init__(self, message: str, *, remaining: int | None = None, reset_at: str | None = None):
        super().__init__(message)
        self.remaining = remaining
        self.reset_at = reset_at


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "tech-hype-monitor",
    }
    token = (settings.github_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_rate_limit(resp: httpx.Response) -> dict[str, Any]:
    remaining = resp.headers.get("X-RateLimit-Remaining")
    reset = resp.headers.get("X-RateLimit-Reset")
    limit = resp.headers.get("X-RateLimit-Limit")
    reset_at = None
    if reset and reset.isdigit():
        reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc).isoformat()
    return {
        "rate_limit_limit": int(limit) if limit and limit.isdigit() else None,
        "rate_limit_remaining": int(remaining) if remaining and remaining.isdigit() else None,
        "rate_limit_reset_at": reset_at,
    }


def _attach_runtime(source, runtime: dict[str, Any]) -> None:
    cursor = dict(getattr(source, "cursor_json", None) or {})
    existing = dict(cursor.get("runtime") or {})
    existing.update({k: v for k, v in runtime.items() if v is not None})
    cursor["runtime"] = existing
    source._pending_cursor = cursor  # type: ignore[attr-defined]


def _repo_event(repo: dict[str, Any]) -> NormalizedRawEvent:
    full_name = repo.get("full_name") or f"{repo.get('owner', {}).get('login')}/{repo.get('name')}"
    payload = f"{full_name}|{repo.get('updated_at')}|{repo.get('stargazers_count')}|{repo.get('pushed_at')}"
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    owner = repo.get("owner") or {}
    meta: dict[str, Any] = {
        "owner": owner.get("login"),
        "name": repo.get("name"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "open_issues": repo.get("open_issues_count"),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
        "topics": repo.get("topics") or [],
        "default_branch": repo.get("default_branch"),
        "archived": repo.get("archived"),
    }
    # Only record subscribers when explicitly present (repo-detail). Never use watchers_count.
    if "subscribers_count" in repo and repo.get("subscribers_count") is not None:
        meta["subscribers"] = repo.get("subscribers_count")
    return NormalizedRawEvent(
        platform="github",
        external_id=full_name,
        author=owner.get("login"),
        published_at=_parse_dt(repo.get("created_at")),
        canonical_url=repo.get("html_url"),
        title=full_name,
        raw_text=repo.get("description"),
        content_hash=content_hash,
        event_type="github_repo",
        metadata=meta,
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GitHubAdapter(SourceAdapter):
    name = "github"

    def is_enabled(self) -> bool:
        return True

    async def fetch(self, source, since=None) -> list[NormalizedRawEvent]:
        st = (source.source_type or "").lower()
        if st == "github_org":
            return await self._fetch_org(source)
        if st in {"github_repo", "github"}:
            return await self._fetch_repo(source)
        raise ValueError(f"Unsupported GitHub source_type: {source.source_type}")

    async def _request(self, source, client: httpx.AsyncClient, url: str, params: dict | None = None):
        resp = await client.get(url, params=params, headers=_github_headers())
        runtime = _parse_rate_limit(resp)
        _attach_runtime(source, runtime)
        remaining = runtime.get("rate_limit_remaining")
        if resp.status_code == 403 and remaining == 0:
            raise GitHubRateLimitError(
                "GitHub rate limit exceeded",
                remaining=remaining,
                reset_at=runtime.get("rate_limit_reset_at"),
            )
        if resp.status_code == 403 and "rate limit" in (resp.text or "").lower():
            raise GitHubRateLimitError(
                "GitHub rate limit exceeded",
                remaining=remaining,
                reset_at=runtime.get("rate_limit_reset_at"),
            )
        resp.raise_for_status()
        if remaining is not None and remaining < 5:
            # Soft signal for health; still return payload.
            runtime["rate_limited"] = True
            _attach_runtime(source, runtime)
        return resp

    async def _fetch_org(self, source) -> list[NormalizedRawEvent]:
        meta = (source.cursor_json or {}).get("config") or {}
        # Also allow metadata from seed stored in cursor config; fallback parse from base_url
        org = meta.get("org")
        if not org and source.base_url:
            org = source.base_url.rstrip("/").split("/")[-1]
        if not org:
            raise ValueError(f"github_org source {source.name} missing org")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await self._request(
                source,
                client,
                f"{GITHUB_API}/orgs/{quote(org)}/repos",
                params={"sort": "updated", "per_page": 30, "type": "public"},
            )
            repos = resp.json() or []
            return [_repo_event(r) for r in repos if isinstance(r, dict)]

    async def _fetch_repo(self, source) -> list[NormalizedRawEvent]:
        meta = (source.cursor_json or {}).get("config") or {}
        full_name = meta.get("repo") or meta.get("full_name")
        if not full_name and source.base_url:
            parts = source.base_url.rstrip("/").split("/")
            if len(parts) >= 2:
                full_name = f"{parts[-2]}/{parts[-1]}"
        if not full_name or "/" not in full_name:
            raise ValueError(f"github_repo source {source.name} missing repo")

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await self._request(source, client, f"{GITHUB_API}/repos/{full_name}")
            repo = resp.json()
            events = [_repo_event(repo)]
            # Optional latest release
            try:
                rel = await self._request(
                    source, client, f"{GITHUB_API}/repos/{full_name}/releases/latest"
                )
                if rel.status_code == 200:
                    data = rel.json()
                    events[0].metadata["latest_release_tag"] = data.get("tag_name")
                    events[0].metadata["latest_release_published_at"] = data.get("published_at")
            except Exception:  # noqa: BLE001
                pass
            return events


async def search_github_repos(
    query: str,
    *,
    limit: int = 30,
    source=None,
) -> list[dict[str, Any]]:
    """Search public repos; persists rate-limit onto optional source."""
    q = query.strip()
    if not q:
        return []
    limit = max(1, min(limit, 50))
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": q, "per_page": limit},
            headers=_github_headers(),
        )
        runtime = _parse_rate_limit(resp)
        if source is not None:
            _attach_runtime(source, runtime)
        if resp.status_code == 403:
            raise GitHubRateLimitError(
                "GitHub rate limit exceeded",
                remaining=runtime.get("rate_limit_remaining"),
                reset_at=runtime.get("rate_limit_reset_at"),
            )
        resp.raise_for_status()
        items = (resp.json() or {}).get("items") or []
        out = []
        for repo in items:
            owner = (repo.get("owner") or {}).get("login")
            out.append(
                {
                    "platform": "github",
                    "entity_type": "github_repo",
                    "external_id": repo.get("full_name"),
                    "name": repo.get("name"),
                    "owner": owner,
                    "url": repo.get("html_url"),
                    "description": repo.get("description"),
                    "stars": repo.get("stargazers_count"),
                    "forks": repo.get("forks_count"),
                    "language": repo.get("language"),
                    "created_at": repo.get("created_at"),
                    "updated_at": repo.get("updated_at"),
                    "pushed_at": repo.get("pushed_at"),
                    "topics": repo.get("topics") or [],
                }
            )
        return out
