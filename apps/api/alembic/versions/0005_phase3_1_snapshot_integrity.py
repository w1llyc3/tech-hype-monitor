"""Phase 3.1: snapshot schedule skip_reason for missed historical checkpoints.

Revision ID: 0005_phase3_1_snapshot_integrity
Revises: 0004_phase3_candidate_engine
Create Date: 2026-10-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase3_1_snapshot_integrity"
down_revision: Union[str, None] = "0004_phase3_candidate_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("candidate_snapshot_schedule") as batch:
        batch.add_column(sa.Column("skip_reason", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("candidate_snapshot_schedule") as batch:
        batch.drop_column("skip_reason")
