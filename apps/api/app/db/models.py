from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    feed_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    cursor_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    raw_events: Mapped[list["RawEvent"]] = relationship(back_populates="source")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform", "handle", name="uq_accounts_platform_handle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    primary_bucket: Mapped[Optional[str]] = mapped_column(String(128))
    secondary_role: Mapped[Optional[str]] = mapped_column(String(128))
    universe_tier: Mapped[Optional[str]] = mapped_column(String(64))
    monitor_priority: Mapped[Optional[str]] = mapped_column(String(64))
    preferred_trigger: Mapped[Optional[str]] = mapped_column(String(128))
    economic_exposure: Mapped[Optional[str]] = mapped_column(String(128))
    conflict_risk: Mapped[Optional[str]] = mapped_column(String(128))
    reverse_test_status: Mapped[Optional[str]] = mapped_column(String(128))
    tech_to_crypto_relevance: Mapped[Optional[str]] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_events_source_external"),
        Index("ix_raw_events_source_url_hash", "source_id", "canonical_url", "content_hash"),
        Index("ix_raw_events_published_at", "published_at"),
        Index("ix_raw_events_retrieved_at", "retrieved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    author: Mapped[Optional[str]] = mapped_column(String(255))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048))
    title: Mapped[Optional[str]] = mapped_column(String(1024))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped["Source"] = relationship(back_populates="raw_events")


class AccountEvent(Base):
    __tablename__ = "account_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    raw_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("raw_events.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_original: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_reply: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_quote: Mapped[Optional[bool]] = mapped_column(Boolean)
    parent_url: Mapped[Optional[str]] = mapped_column(String(2048))
    candidate_phrase: Mapped[Optional[str]] = mapped_column(String(512))
    candidate_object: Mapped[Optional[str]] = mapped_column(String(512))
    semantic_cluster: Mapped[Optional[str]] = mapped_column(String(128))
    object_source_mode: Mapped[Optional[str]] = mapped_column(String(64))
    source_self_initiated: Mapped[Optional[bool]] = mapped_column(Boolean)
    economic_exposure_at_time: Mapped[Optional[str]] = mapped_column(String(128))
    participant_status: Mapped[Optional[str]] = mapped_column(String(64))
    candidate_state: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    investigation_priority: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypeCandidate(Base):
    __tablename__ = "hype_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plain_english: Mapped[Optional[str]] = mapped_column(Text)
    hype_unit_type: Mapped[Optional[str]] = mapped_column(String(64))
    formation_pattern: Mapped[Optional[str]] = mapped_column(String(64))
    first_known_use_t0: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    event_occurrence_t0: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    public_disclosure_t0: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    breakout_origin_t0: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    category_adoption_t0: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reactivation_t0: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    candidate_status: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CandidateSnapshot(Base):
    __tablename__ = "candidate_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hype_id: Mapped[int] = mapped_column(ForeignKey("hype_candidates.id"), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mention_count: Mapped[Optional[int]] = mapped_column(Integer)
    independent_account_count: Mapped[Optional[int]] = mapped_column(Integer)
    high_quality_amplifier_count: Mapped[Optional[int]] = mapped_column(Integer)
    platform_count: Mapped[Optional[int]] = mapped_column(Integer)
    cross_cluster_count: Mapped[Optional[int]] = mapped_column(Integer)
    dominant_keyword: Mapped[Optional[str]] = mapped_column(String(255))
    keyword_variant_count: Mapped[Optional[int]] = mapped_column(Integer)
    keyword_convergence: Mapped[Optional[float]] = mapped_column(Float)
    derivative_count: Mapped[Optional[int]] = mapped_column(Integer)
    source_detachment: Mapped[Optional[float]] = mapped_column(Float)
    token_exists: Mapped[Optional[bool]] = mapped_column(Boolean)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    canonical_state: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hype_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hype_candidates.id"))
    raw_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("raw_events.id"))
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    observation_status: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    evidence_phase: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrackedEntity(Base):
    __tablename__ = "tracked_entities"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "entity_type",
            "external_id",
            name="uq_tracked_entities_platform_type_external",
        ),
        Index("ix_tracked_entities_platform_type", "platform", "entity_type"),
        Index("ix_tracked_entities_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id"))
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048))
    display_name: Mapped[Optional[str]] = mapped_column(String(512))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    observations: Mapped[list["MetricObservation"]] = relationship(back_populates="entity")


class MetricObservation(Base):
    __tablename__ = "metric_observations"
    __table_args__ = (
        Index(
            "ix_metric_obs_entity_name_time",
            "tracked_entity_id",
            "metric_name",
            "observed_at",
        ),
        Index("ix_metric_observations_observed_at", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracked_entity_id: Mapped[int] = mapped_column(
        ForeignKey("tracked_entities.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value: Mapped[Optional[float]] = mapped_column(Float)
    metric_text: Mapped[Optional[str]] = mapped_column(String(512))
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    entity: Mapped["TrackedEntity"] = relationship(back_populates="observations")
