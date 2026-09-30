"""Smoke discovery across GitHub + Hugging Face without hype classification.

Usage:
  python scripts/discovery_smoke.py "vibe coding"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))


async def _run(query: str) -> None:
    from app.adapters.github import search_github_repos
    from app.adapters.huggingface import search_hf

    print(f"Query: {query}\n")

    print("=== GitHub ===")
    try:
        gh = await search_github_repos(query, limit=5)
        for item in gh:
            print(
                f"- {item.get('external_id')} stars={item.get('stars')} "
                f"lang={item.get('language')} {item.get('url')}"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"GitHub error: {exc}")

    for kind, label in [("model", "HF Models"), ("space", "HF Spaces"), ("dataset", "HF Datasets")]:
        print(f"\n=== {label} ===")
        try:
            items = search_hf(kind, query, limit=5)  # type: ignore[arg-type]
            for item in items:
                print(
                    f"- {item.get('repo_id')} likes={item.get('likes')} "
                    f"downloads={item.get('downloads')} {item.get('url')}"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"{label} error: {exc}")


def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or "vibe coding"
    asyncio.run(_run(query))


if __name__ == "__main__":
    main()
