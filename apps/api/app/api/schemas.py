from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: str
    source_type: str
    base_url: str
    feed_url: Optional[str] = None
    poll_interval_seconds: int
    enabled: bool
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SourceHealthOut(BaseModel):
    id: int
    name: str
    platform: str
    source_type: str
    enabled: bool
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error: Optional[str] = None
    events_24h: int
    status: str


class RawEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    platform: str
    external_id: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    retrieved_at: datetime
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    raw_text: Optional[str] = None
    content_hash: str
    event_type: str
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
    source_name: Optional[str] = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    handle: str
    display_name: Optional[str] = None
    primary_bucket: Optional[str] = None
    secondary_role: Optional[str] = None
    universe_tier: Optional[str] = None
    monitor_priority: Optional[str] = None
    preferred_trigger: Optional[str] = None
    economic_exposure: Optional[str] = None
    conflict_risk: Optional[str] = None
    reverse_test_status: Optional[str] = None
    tech_to_crypto_relevance: Optional[str] = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class HypeCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_name: str
    plain_english: Optional[str] = None
    hype_unit_type: Optional[str] = None
    formation_pattern: Optional[str] = None
    candidate_status: str
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    updated_at: datetime


class PollResultOut(BaseModel):
    source_id: int
    source_name: str
    fetched: int
    inserted: int
    duplicates: int
    updated: int
    error: Optional[str] = None
    duration_ms: int


class DashboardOut(BaseModel):
    healthy: int
    stale: int
    error: int
    disabled: int
    events_24h_by_group: dict[str, int]
    recent_events: list[RawEventOut]
