"""Trend productization: replay, formation engine, deltas, assessments, research bundle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import API_ROOT
from app.db.models import Base, CandidateTrendAssessment, HypeCandidate
from app.services.replay import detection_view, load_case, replay_case
from app.services.research_bundle import export_research_bundle
from app.services.trend_assess import assess_metrics, manual_override, persist_assessment
from app.services.trend_deltas import compute_deltas
from app.services.trend_engine import (
    TREND_ENGINE_VERSION,
    EvidenceMetrics,
    infer_formation_pattern,
    infer_formation_stage,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "trend.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_migration_includes_trend_assessments(tmp_path: Path):
    db_path = tmp_path / "mig.db"
    url = f"sqlite:///{db_path.as_posix()}"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(candidate_trend_assessments)")}
    assert "engine_version" in cols
    assert "formation_stage" in cols
    assert "trend_direction" in cols
    assert "formation_pattern" in cols
    engine.dispose()


def test_replay_cutoff_hides_future_events():
    results = replay_case("synth-naming-first", checkpoint="+1H")
    assert len(results) == 1
    # at +1H only origin event (T0) is visible; adopter is at +6H
    assert results[0].visible_evidence_count == 1
    assert results[0].independent_amplifiers == 0


def test_evaluation_block_stripped_from_detection_view():
    raw = load_case("synth-naming-first")
    assert "evaluation" in raw
    view = detection_view(raw)
    assert "evaluation" not in view
    # mutate view evaluation would fail — ensure engine path uses stripped view
    results = replay_case("synth-naming-first", checkpoint="+24H")
    assert results[0].evaluation_comparison is not None
    assert results[0].evaluation_comparison["reference_pattern"] == "NAMING_FIRST"


def test_naming_first_replay():
    results = replay_case("synth-naming-first", checkpoint="+24H")
    assert results[0].suggested_formation_pattern == "NAMING_FIRST"
    assert results[0].suggested_formation_stage in {"WATCHING", "FORMATION", "BREAKOUT"}


def test_proof_led_replay():
    results = replay_case("synth-proof-led", checkpoint="+24H")
    assert results[0].suggested_formation_pattern == "PROOF_LED"


def test_reactivated_replay():
    results = replay_case("synth-reactivated", checkpoint="+24H")
    assert results[0].suggested_formation_pattern == "REACTIVATED_TERM"


def test_source_only_stays_seed():
    results = replay_case("synth-source-only", checkpoint="+24H")
    assert results[0].suggested_formation_stage == "SEED"
    assert results[0].suggested_trend_direction == "INSUFFICIENT_DATA"
    assert results[0].independent_amplifiers == 0


def test_no_single_source_breakout():
    m = EvidenceMetrics(
        independent_amplifiers=0,
        total_monitored_accounts=1,
        active_platforms=["x"],
        mention_count=1000,
        confirmation_checkpoints=5,
    )
    stage = infer_formation_stage(m)
    assert stage.formation_stage != "BREAKOUT"


def test_stage_transitions():
    seed = infer_formation_stage(EvidenceMetrics(active_platforms=["x"]))
    assert seed.formation_stage == "SEED"
    watching = infer_formation_stage(
        EvidenceMetrics(independent_amplifiers=1, active_platforms=["x"])
    )
    assert watching.formation_stage == "WATCHING"
    formation = infer_formation_stage(
        EvidenceMetrics(independent_amplifiers=2, active_platforms=["x", "hn"])
    )
    assert formation.formation_stage == "FORMATION"


def test_trend_deltas_and_skipped_no_fake():
    prior = EvidenceMetrics(independent_amplifiers=1, github_post_t0=0, active_platforms=["x"])
    cur = EvidenceMetrics(independent_amplifiers=3, github_post_t0=2, active_platforms=["x", "github"])
    ok = compute_deltas(cur, prior)
    assert ok.trend_direction == "ACCELERATING"
    assert ok.deltas["delta_independent_amplifiers"] == 2

    skipped = compute_deltas(cur, prior, prior_was_skipped=True)
    assert skipped.trend_direction == "INSUFFICIENT_DATA"
    assert skipped.deltas["delta_independent_amplifiers"] is None

    none_prior = compute_deltas(cur, None)
    assert none_prior.trend_direction == "INSUFFICIENT_DATA"


def test_unknown_pattern_allowed():
    m = EvidenceMetrics(active_platforms=["x"])
    p = infer_formation_pattern(m)
    assert p.suggested_pattern == "UNKNOWN"
    assert p.confidence == "LOW"
    assert p.missing


def test_assessment_version_persisted(db_session):
    now = datetime.now(timezone.utc)
    hype = HypeCandidate(
        canonical_name="LabelX",
        candidate_status="OPEN",
        created_at=now,
        updated_at=now,
    )
    db_session.add(hype)
    db_session.commit()
    payload = assess_metrics(
        EvidenceMetrics(
            independent_amplifiers=2,
            active_platforms=["x", "hn"],
            origin_signal_type="NEW_TERM",
            origin_role="NARRATIVE_NAMER",
            github_post_t0=1,
        ),
        confirmation_checkpoints=2,
    )
    row = persist_assessment(db_session, hype.id, payload)
    db_session.commit()
    assert row.engine_version == TREND_ENGINE_VERSION
    assert row.formation_stage
    assert row.trend_direction
    assert row.formation_pattern


def test_manual_override_preserves_suggestion(db_session):
    now = datetime.now(timezone.utc)
    hype = HypeCandidate(
        canonical_name="OverrideMe",
        candidate_status="OPEN",
        created_at=now,
        updated_at=now,
    )
    db_session.add(hype)
    db_session.commit()
    payload = assess_metrics(
        EvidenceMetrics(
            independent_amplifiers=2,
            active_platforms=["x", "hn"],
            origin_signal_type="NEW_TERM",
            origin_role="NARRATIVE_NAMER",
        )
    )
    first = persist_assessment(db_session, hype.id, payload)
    db_session.commit()
    override = manual_override(
        db_session,
        hype.id,
        formation_stage="BREAKOUT",
        formation_pattern="REFRAMING",
    )
    assert override.is_manual_override is True
    suggested = (override.metrics_json or {}).get("suggested") or {}
    assert suggested.get("formation_pattern") == first.formation_pattern
    assert suggested.get("formation_stage") == first.formation_stage
    hist = list(
        db_session.scalars(
            select(CandidateTrendAssessment).where(CandidateTrendAssessment.hype_id == hype.id)
        ).all()
    )
    assert len(hist) == 2


def test_research_bundle_contains_evidence_and_missing(db_session, tmp_path: Path):
    now = datetime.now(timezone.utc)
    hype = HypeCandidate(
        canonical_name="Bundle Case",
        candidate_status="WATCHING",
        plain_english="test",
        public_disclosure_t0=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(hype)
    db_session.commit()
    payload = assess_metrics(EvidenceMetrics(active_platforms=["x"]))
    persist_assessment(db_session, hype.id, payload)
    db_session.commit()
    path = export_research_bundle(db_session, hype.id, exports_dir=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "Research Bundle" in text
    assert "Missing evidence" in text or "missing" in text.lower()
    assert "ChatGPT Research Prompt" in text
    assert "token" not in text.lower() or "Do not include token" in text
    assert "DEX" not in text or "Do not include token/DEX" in text


def test_no_token_dex_fields_in_trend_model():
    cols = set(CandidateTrendAssessment.__table__.columns.keys())
    forbidden = {"token", "ticker", "dex", "liquidity", "contract_address", "ca", "wallet"}
    assert not (cols & forbidden)


def test_no_openai_dependency_imported():
    import app.services.research_bundle as rb
    import app.services.trend_engine as te
    import app.services.replay as rp

    for mod in (rb, te, rp):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "openai" not in src.lower()
        assert "OpenAI" not in src
