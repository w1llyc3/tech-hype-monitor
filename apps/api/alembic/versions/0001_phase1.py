"""Initial Phase 1 schema."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("feed_url", sa.String(length=1024), nullable=True),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("cursor_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("primary_bucket", sa.String(length=128), nullable=True),
        sa.Column("secondary_role", sa.String(length=128), nullable=True),
        sa.Column("universe_tier", sa.String(length=64), nullable=True),
        sa.Column("monitor_priority", sa.String(length=64), nullable=True),
        sa.Column("preferred_trigger", sa.String(length=128), nullable=True),
        sa.Column("economic_exposure", sa.String(length=128), nullable=True),
        sa.Column("conflict_risk", sa.String(length=128), nullable=True),
        sa.Column("reverse_test_status", sa.String(length=128), nullable=True),
        sa.Column("tech_to_crypto_relevance", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "handle", name="uq_accounts_platform_handle"),
    )
    op.create_table(
        "hype_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("plain_english", sa.Text(), nullable=True),
        sa.Column("hype_unit_type", sa.String(length=64), nullable=True),
        sa.Column("formation_pattern", sa.String(length=64), nullable=True),
        sa.Column("first_known_use_t0", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_occurrence_t0", sa.DateTime(timezone=True), nullable=True),
        sa.Column("public_disclosure_t0", sa.DateTime(timezone=True), nullable=True),
        sa.Column("breakout_origin_t0", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category_adoption_t0", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reactivation_t0", sa.DateTime(timezone=True), nullable=True),
        sa.Column("candidate_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name"),
    )
    op.create_table(
        "raw_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "external_id", name="uq_raw_events_platform_external"),
    )
    op.create_index("ix_raw_events_url_hash", "raw_events", ["canonical_url", "content_hash"])
    op.create_index("ix_raw_events_published_at", "raw_events", ["published_at"])
    op.create_index("ix_raw_events_retrieved_at", "raw_events", ["retrieved_at"])

    op.create_table(
        "account_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("raw_event_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("is_original", sa.Boolean(), nullable=True),
        sa.Column("is_reply", sa.Boolean(), nullable=True),
        sa.Column("is_quote", sa.Boolean(), nullable=True),
        sa.Column("parent_url", sa.String(length=2048), nullable=True),
        sa.Column("candidate_phrase", sa.String(length=512), nullable=True),
        sa.Column("candidate_object", sa.String(length=512), nullable=True),
        sa.Column("semantic_cluster", sa.String(length=128), nullable=True),
        sa.Column("object_source_mode", sa.String(length=64), nullable=True),
        sa.Column("source_self_initiated", sa.Boolean(), nullable=True),
        sa.Column("economic_exposure_at_time", sa.String(length=128), nullable=True),
        sa.Column("participant_status", sa.String(length=64), nullable=True),
        sa.Column("candidate_state", sa.String(length=64), nullable=False),
        sa.Column("investigation_priority", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "candidate_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hype_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=True),
        sa.Column("independent_account_count", sa.Integer(), nullable=True),
        sa.Column("high_quality_amplifier_count", sa.Integer(), nullable=True),
        sa.Column("platform_count", sa.Integer(), nullable=True),
        sa.Column("cross_cluster_count", sa.Integer(), nullable=True),
        sa.Column("dominant_keyword", sa.String(length=255), nullable=True),
        sa.Column("keyword_variant_count", sa.Integer(), nullable=True),
        sa.Column("keyword_convergence", sa.Float(), nullable=True),
        sa.Column("derivative_count", sa.Integer(), nullable=True),
        sa.Column("source_detachment", sa.Float(), nullable=True),
        sa.Column("token_exists", sa.Boolean(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("canonical_state", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hype_id"], ["hype_candidates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hype_id", sa.Integer(), nullable=True),
        sa.Column("raw_event_id", sa.Integer(), nullable=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("observation_status", sa.String(length=64), nullable=False),
        sa.Column("evidence_phase", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hype_id"], ["hype_candidates.id"]),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("evidence")
    op.drop_table("candidate_snapshots")
    op.drop_table("account_events")
    op.drop_index("ix_raw_events_retrieved_at", table_name="raw_events")
    op.drop_index("ix_raw_events_published_at", table_name="raw_events")
    op.drop_index("ix_raw_events_url_hash", table_name="raw_events")
    op.drop_table("raw_events")
    op.drop_table("hype_candidates")
    op.drop_table("accounts")
    op.drop_table("sources")
