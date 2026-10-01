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
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset_at: Optional[str] = None


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
    rate_limited: int = 0
    events_24h_by_group: dict[str, int]
    recent_events: list[RawEventOut]
    tracked_entities: dict[str, int] = {}
    recent_derivative_activity: dict[str, int] = {}


class TrackedEntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: Optional[int] = None
    platform: str
    entity_type: str
    external_id: str
    canonical_url: Optional[str] = None
    display_name: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class MetricPointOut(BaseModel):
    observed_at: datetime
    value: Optional[float] = None
    text: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class EntityMetricsOut(BaseModel):
    entity: TrackedEntityOut
    series: dict[str, list[MetricPointOut]]


class VelocityOut(BaseModel):
    metric: str
    window_hours: int
    start_value: Optional[float] = None
    end_value: Optional[float] = None
    delta: Optional[float] = None
    delta_per_hour: Optional[float] = None


class AccountListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    handle: str
    display_name: Optional[str] = None
    primary_bucket: Optional[str] = None
    secondary_role: Optional[str] = None
    universe_tier: Optional[str] = None
    monitor_priority: Optional[str] = None
    conflict_risk: Optional[str] = None
    tech_to_crypto_relevance: Optional[str] = None
    enabled: bool
    last_ingested_post_at: Optional[datetime] = None
    events_30d: int = 0
    open_candidate_signals: int = 0


class AccountStatsOut(BaseModel):
    account_id: int
    events_24h: int
    events_30d: int
    candidate_signals_30d: int
    accepted_signals_30d: int
    rejected_signals_30d: int
    open_signals: int
    last_event_at: Optional[datetime] = None


class VisibleMetricsIn(BaseModel):
    likes: Optional[int] = None
    reposts: Optional[int] = None
    replies: Optional[int] = None
    views: Optional[int] = None


class ManualXIngestIn(BaseModel):
    url: str
    handle: str
    text: str
    posted_at: Optional[datetime] = None
    post_type: str = "original"
    parent_url: Optional[str] = None
    quoted_url: Optional[str] = None
    visible_metrics: Optional[VisibleMetricsIn] = None


class ManualXIngestOut(BaseModel):
    raw_event_id: int
    account_id: Optional[int] = None
    account_event_id: Optional[int] = None
    known_account: bool
    created_raw: bool
    candidate_signal_ids: list[int]
    suggested_hype_ids: list[int] = []
    candidate_signals_extracted: int = 0


class CandidateSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_event_id: int
    account_event_id: Optional[int] = None
    signal_type: str
    candidate_text: str
    normalized_text: str
    extraction_method: str
    source_role: Optional[str] = None
    trigger_reason: Optional[str] = None
    initial_priority: Optional[str] = None
    state: str
    linked_hype_id: Optional[int] = None
    merged_into_signal_id: Optional[int] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    account_handle: Optional[str] = None
    conflict_risk: Optional[str] = None
    post_preview: Optional[str] = None
    source_url: Optional[str] = None
    suggested_hype_ids: list[int] = []


class AcceptSignalIn(BaseModel):
    plain_english: Optional[str] = None
    hype_unit_type: Optional[str] = None


class AttachSignalIn(BaseModel):
    hype_id: int


class RejectSignalIn(BaseModel):
    reason: Optional[str] = None
    note: Optional[str] = None


class MergeSignalIn(BaseModel):
    into_signal_id: int


class PromoteEventIn(BaseModel):
    candidate_name: str
    unit_type: Optional[str] = None
    phrase_or_object: Optional[str] = None


class HypeAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hype_id: int
    alias: str
    normalized_alias: str
    alias_type: Optional[str] = None
    created_at: datetime


class HypeAliasIn(BaseModel):
    alias: str
    alias_type: Optional[str] = None


class HypeCandidatePatchIn(BaseModel):
    plain_english: Optional[str] = None
    candidate_status: Optional[str] = None
    hype_unit_type: Optional[str] = None


class HypeCandidateDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_name: str
    plain_english: Optional[str] = None
    hype_unit_type: Optional[str] = None
    formation_pattern: Optional[str] = None
    first_known_use_t0: Optional[datetime] = None
    event_occurrence_t0: Optional[datetime] = None
    public_disclosure_t0: Optional[datetime] = None
    breakout_origin_t0: Optional[datetime] = None
    category_adoption_t0: Optional[datetime] = None
    reactivation_t0: Optional[datetime] = None
    candidate_status: str
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    updated_at: datetime
    aliases: list[HypeAliasOut] = []
    origin_account: Optional[str] = None
    initial_trigger: Optional[str] = None
    independent_accounts: Optional[int] = None
    platforms: Optional[int] = None
    github_repos: Optional[int] = None
    hf_spaces: Optional[int] = None
    hn_stories: Optional[int] = None
    last_snapshot_at: Optional[datetime] = None
    next_checkpoint: Optional[str] = None
    next_checkpoint_due_at: Optional[datetime] = None


class CandidateSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hype_id: int
    snapshot_at: datetime
    checkpoint: Optional[str] = None
    mention_count: Optional[int] = None
    independent_account_count: Optional[int] = None
    high_quality_amplifier_count: Optional[int] = None
    platform_count: Optional[int] = None
    dominant_keyword: Optional[str] = None
    keyword_variant_count: Optional[int] = None
    canonical_state: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class SnapshotScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hype_id: int
    checkpoint: str
    due_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    attempts: int = 0
    last_error: Optional[str] = None
    skip_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # joined from completed snapshot when available
    snapshot_at: Optional[datetime] = None
    late_by_seconds: Optional[int] = None
    timing_quality: Optional[str] = None
    scheduled_due_at: Optional[str] = None


class TimelineItemOut(BaseModel):
    kind: str
    at: datetime
    title: str
    detail: Optional[str] = None
    ref_id: Optional[int] = None
