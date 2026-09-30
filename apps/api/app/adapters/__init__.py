from app.adapters.base import NormalizedRawEvent, SourceAdapter
from app.adapters.hn import HNAdapter
from app.adapters.rss import RSSAdapter
from app.adapters.stubs import (
    DexScreenerAdapter,
    GitHubAdapter,
    HuggingFaceAdapter,
    XAdapter,
)

__all__ = [
    "NormalizedRawEvent",
    "SourceAdapter",
    "HNAdapter",
    "RSSAdapter",
    "GitHubAdapter",
    "HuggingFaceAdapter",
    "XAdapter",
    "DexScreenerAdapter",
    "get_adapter_for_source",
]


def get_adapter_for_source(source, feed: str | None = None) -> SourceAdapter:
    st = (source.source_type or "").lower()
    if st in {"hacker_news", "hn"}:
        return HNAdapter(feed=feed or "newstories")
    if st in {"official_rss", "rss"}:
        return RSSAdapter()
    if st == "github":
        return GitHubAdapter()
    if st in {"huggingface", "hugging_face"}:
        return HuggingFaceAdapter()
    if st in {"x", "twitter"}:
        return XAdapter()
    if st in {"dex", "dexscreener"}:
        return DexScreenerAdapter()
    raise ValueError(f"Unknown source_type: {source.source_type}")
