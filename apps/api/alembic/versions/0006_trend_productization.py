"""Phase Trend Productization: candidate_trend_assessments.

Revision ID: 0006_trend_productization
Revises: 0005_phase3_1_snapshot_integrity
Create Date: 2026-10-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_trend_productization"
down_revision: Union[str, None] = "0005_phase3_1_snapshot_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_trend_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hype_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("formation_stage", sa.String(length=64), nullable=False),
        sa.Column("trend_direction", sa.String(length=64), nullable=False),
        sa.Column("formation_pattern", sa.String(length=64), nullable=False),
        sa.Column("pattern_confidence", sa.String(length=32), nullable=True),
        sa.Column("reasons_json", sa.JSON(), nullable=True),
        sa.Column("missing_evidence_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("is_manual_override", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hype_id"], ["hype_candidates.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["candidate_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_trend_assessments_hype_assessed",
        "candidate_trend_assessments",
        ["hype_id", "assessed_at"],
    )
    op.create_index(
        "ix_candidate_trend_assessments_snapshot_id",
        "candidate_trend_assessments",
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_trend_assessments_snapshot_id", table_name="candidate_trend_assessments")
    op.drop_index("ix_candidate_trend_assessments_hype_assessed", table_name="candidate_trend_assessments")
    op.drop_table("candidate_trend_assessments")
