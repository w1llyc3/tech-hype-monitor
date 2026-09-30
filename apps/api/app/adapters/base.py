from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class NormalizedRawEvent:
    platform: str
    event_type: str
    content_hash: str
    external_id: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    raw_text: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch(self, source, since: datetime | None = None) -> list[NormalizedRawEvent]:
        """Fetch normalized events for a source. Must not invent data."""

    def is_enabled(self) -> bool:
        return True
