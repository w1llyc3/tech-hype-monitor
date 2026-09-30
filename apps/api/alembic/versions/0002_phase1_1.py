"""Phase 1.1 data integrity: source-aware dedupe, drop canonical_name unique.

Revision ID: 0002_phase1_1
Revises: 0001_phase1
Create Date: 2026-09-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase1_1"
down_revision: Union[str, None] = "0001_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite may have an unnamed UNIQUE(canonical_name). Recreate table without it.
    op.execute(
        """
        CREATE TABLE hype_candidates_new (
            id INTEGER NOT NULL,
            canonical_name VARCHAR(255) NOT NULL,
            plain_english TEXT,
            hype_unit_type VARCHAR(64),
            formation_pattern VARCHAR(64),
            first_known_use_t0 DATETIME,
            event_occurrence_t0 DATETIME,
            public_disclosure_t0 DATETIME,
            breakout_origin_t0 DATETIME,
            category_adoption_t0 DATETIME,
            reactivation_t0 DATETIME,
            candidate_status VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL,
            last_activity_at DATETIME,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO hype_candidates_new (
            id, canonical_name, plain_english, hype_unit_type, formation_pattern,
            first_known_use_t0, event_occurrence_t0, public_disclosure_t0,
            breakout_origin_t0, category_adoption_t0, reactivation_t0,
            candidate_status, created_at, last_activity_at, updated_at
        )
        SELECT
            id, canonical_name, plain_english, hype_unit_type, formation_pattern,
            first_known_use_t0, event_occurrence_t0, public_disclosure_t0,
            breakout_origin_t0, category_adoption_t0, reactivation_t0,
            candidate_status, created_at, last_activity_at, updated_at
        FROM hype_candidates
        """
    )
    op.drop_table("hype_candidates")
    op.rename_table("hype_candidates_new", "hype_candidates")

    with op.batch_alter_table("raw_events") as batch:
        try:
            batch.drop_constraint("uq_raw_events_platform_external", type_="unique")
        except Exception:
            pass
        batch.create_unique_constraint(
            "uq_raw_events_source_external",
            ["source_id", "external_id"],
        )
        try:
            batch.drop_index("ix_raw_events_url_hash")
        except Exception:
            pass
        batch.create_index(
            "ix_raw_events_source_url_hash",
            ["source_id", "canonical_url", "content_hash"],
        )


def downgrade() -> None:
    with op.batch_alter_table("raw_events") as batch:
        batch.drop_index("ix_raw_events_source_url_hash")
        batch.create_index("ix_raw_events_url_hash", ["canonical_url", "content_hash"])
        batch.drop_constraint("uq_raw_events_source_external", type_="unique")
        batch.create_unique_constraint(
            "uq_raw_events_platform_external",
            ["platform", "external_id"],
        )

    op.execute(
        """
        CREATE TABLE hype_candidates_old (
            id INTEGER NOT NULL,
            canonical_name VARCHAR(255) NOT NULL,
            plain_english TEXT,
            hype_unit_type VARCHAR(64),
            formation_pattern VARCHAR(64),
            first_known_use_t0 DATETIME,
            event_occurrence_t0 DATETIME,
            public_disclosure_t0 DATETIME,
            breakout_origin_t0 DATETIME,
            category_adoption_t0 DATETIME,
            reactivation_t0 DATETIME,
            candidate_status VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL,
            last_activity_at DATETIME,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (canonical_name)
        )
        """
    )
    op.execute(
        """
        INSERT INTO hype_candidates_old (
            id, canonical_name, plain_english, hype_unit_type, formation_pattern,
            first_known_use_t0, event_occurrence_t0, public_disclosure_t0,
            breakout_origin_t0, category_adoption_t0, reactivation_t0,
            candidate_status, created_at, last_activity_at, updated_at
        )
        SELECT
            id, canonical_name, plain_english, hype_unit_type, formation_pattern,
            first_known_use_t0, event_occurrence_t0, public_disclosure_t0,
            breakout_origin_t0, category_adoption_t0, reactivation_t0,
            candidate_status, created_at, last_activity_at, updated_at
        FROM hype_candidates
        """
    )
    op.drop_table("hype_candidates")
    op.rename_table("hype_candidates_old", "hype_candidates")
