"""Phase 3: candidate signals, aliases, snapshot schedule, snapshot metadata.

Revision ID: 0004_phase3_candidate_engine
Revises: 0003_phase2_metrics_github_hf
Create Date: 2026-09-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase3_candidate_engine"
down_revision: Union[str, None] = "0003_phase2_metrics_github_hf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hype_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hype_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=512), nullable=False),
        sa.Column("normalized_alias", sa.String(length=512), nullable=False),
        sa.Column("alias_type", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hype_id"], ["hype_candidates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hype_id", "normalized_alias", name="uq_hype_aliases_hype_norm"),
    )
    op.create_index("ix_hype_aliases_normalized_alias", "hype_aliases", ["normalized_alias"])

    op.create_table(
        "candidate_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raw_event_id", sa.Integer(), nullable=False),
        sa.Column("account_event_id", sa.Integer(), nullable=True),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("candidate_text", sa.String(length=512), nullable=False),
        sa.Column("normalized_text", sa.String(length=512), nullable=False),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("source_role", sa.String(length=128), nullable=True),
        sa.Column("trigger_reason", sa.Text(), nullable=True),
        sa.Column("initial_priority", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("linked_hype_id", sa.Integer(), nullable=True),
        sa.Column("merged_into_signal_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_events.id"]),
        sa.ForeignKeyConstraint(["account_event_id"], ["account_events.id"]),
        sa.ForeignKeyConstraint(["linked_hype_id"], ["hype_candidates.id"]),
        sa.ForeignKeyConstraint(["merged_into_signal_id"], ["candidate_signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_signals_state_created",
        "candidate_signals",
        ["state", "created_at"],
    )
    op.create_index("ix_candidate_signals_normalized_text", "candidate_signals", ["normalized_text"])
    op.create_index("ix_candidate_signals_raw_event_id", "candidate_signals", ["raw_event_id"])
    op.create_index("ix_candidate_signals_linked_hype_id", "candidate_signals", ["linked_hype_id"])

    op.create_table(
        "candidate_snapshot_schedule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hype_id", sa.Integer(), nullable=False),
        sa.Column("checkpoint", sa.String(length=32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hype_id"], ["hype_candidates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hype_id", "checkpoint", name="uq_candidate_snapshot_schedule_hype_cp"),
    )
    op.create_index(
        "ix_candidate_snapshot_schedule_due",
        "candidate_snapshot_schedule",
        ["status", "due_at"],
    )

    with op.batch_alter_table("candidate_snapshots") as batch:
        batch.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("checkpoint", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_candidate_snapshots_hype_checkpoint",
        "candidate_snapshots",
        ["hype_id", "checkpoint"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_snapshots_hype_checkpoint", table_name="candidate_snapshots")
    with op.batch_alter_table("candidate_snapshots") as batch:
        batch.drop_column("checkpoint")
        batch.drop_column("metadata_json")

    op.drop_index("ix_candidate_snapshot_schedule_due", table_name="candidate_snapshot_schedule")
    op.drop_table("candidate_snapshot_schedule")

    op.drop_index("ix_candidate_signals_linked_hype_id", table_name="candidate_signals")
    op.drop_index("ix_candidate_signals_raw_event_id", table_name="candidate_signals")
    op.drop_index("ix_candidate_signals_normalized_text", table_name="candidate_signals")
    op.drop_index("ix_candidate_signals_state_created", table_name="candidate_signals")
    op.drop_table("candidate_signals")

    op.drop_index("ix_hype_aliases_normalized_alias", table_name="hype_aliases")
    op.drop_table("hype_aliases")
