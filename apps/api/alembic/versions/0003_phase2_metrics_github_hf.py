"""Phase 2: tracked_entities + metric_observations.

Revision ID: 0003_phase2_metrics_github_hf
Revises: 0002_phase1_1
Create Date: 2026-09-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase2_metrics_github_hf"
down_revision: Union[str, None] = "0002_phase1_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "entity_type",
            "external_id",
            name="uq_tracked_entities_platform_type_external",
        ),
    )
    op.create_index(
        "ix_tracked_entities_platform_type",
        "tracked_entities",
        ["platform", "entity_type"],
    )
    op.create_index("ix_tracked_entities_last_seen_at", "tracked_entities", ["last_seen_at"])

    op.create_table(
        "metric_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tracked_entity_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("metric_text", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tracked_entity_id"], ["tracked_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_metric_obs_entity_name_time",
        "metric_observations",
        ["tracked_entity_id", "metric_name", "observed_at"],
    )
    op.create_index("ix_metric_observations_observed_at", "metric_observations", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_metric_observations_observed_at", table_name="metric_observations")
    op.drop_index("ix_metric_obs_entity_name_time", table_name="metric_observations")
    op.drop_table("metric_observations")
    op.drop_index("ix_tracked_entities_last_seen_at", table_name="tracked_entities")
    op.drop_index("ix_tracked_entities_platform_type", table_name="tracked_entities")
    op.drop_table("tracked_entities")
