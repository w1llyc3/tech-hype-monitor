"""Persist versioned trend assessments from snapshots or replay metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.db.models import CandidateSnapshot, CandidateTrendAssessment, HypeCandidate
from app.services.trend_deltas import TrendDeltaResult, compute_deltas
from app.services.trend_engine import (
    TREND_ENGINE_VERSION,
    EvidenceMetrics,
    infer_formation_pattern,
    infer_formation_stage,
    metrics_from_snapshot_meta,
)


def assess_metrics(
    metrics: EvidenceMetrics,
    *,
    prior_metrics: Optional[EvidenceMetrics] = None,
    prior_was_skipped: bool = False,
    confirmation_checkpoints: int = 0,
) -> dict[str, Any]:
    metrics.confirmation_checkpoints = confirmation_checkpoints or metrics.confirmation_checkpoints
    pattern = infer_formation_pattern(metrics)
    stage = infer_formation_stage(metrics)
    direction = compute_deltas(metrics, prior_metrics, prior_was_skipped=prior_was_skipped)

    reasons = {
        "pattern": pattern.reasons,
        "stage": stage.reasons,
        "direction": direction.reasons,
    }
    missing = {
        "pattern": pattern.missing,
        "stage": stage.missing,
        "direction": direction.missing,
    }
    return {
        "formation_stage": stage.formation_stage,
        "trend_direction": direction.trend_direction,
        "formation_pattern": pattern.suggested_pattern,
        "pattern_confidence": pattern.confidence,
        "reasons_json": reasons,
        "missing_evidence_json": missing,
        "metrics_json": {**metrics.to_dict(), "deltas": direction.deltas},
        "engine_version": TREND_ENGINE_VERSION,
    }


def persist_assessment(
    db: Session,
    hype_id: int,
    payload: dict[str, Any],
    *,
    snapshot_id: Optional[int] = None,
    is_manual_override: bool = False,
    assessed_at: Optional[datetime] = None,
) -> CandidateTrendAssessment:
    now = utcnow()
    row = CandidateTrendAssessment(
        hype_id=hype_id,
        snapshot_id=snapshot_id,
        assessed_at=assessed_at or now,
        formation_stage=payload["formation_stage"],
        trend_direction=payload["trend_direction"],
        formation_pattern=payload["formation_pattern"],
        pattern_confidence=payload.get("pattern_confidence"),
        reasons_json=payload.get("reasons_json"),
        missing_evidence_json=payload.get("missing_evidence_json"),
        metrics_json=payload.get("metrics_json"),
        engine_version=payload.get("engine_version") or TREND_ENGINE_VERSION,
        is_manual_override=is_manual_override,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def assess_snapshot(db: Session, snapshot: CandidateSnapshot) -> CandidateTrendAssessment:
    """Create a new assessment for a completed snapshot (never overwrite history)."""
    meta = snapshot.metadata_json or {}
    # Enrich origin signal/role from linked accepted signals if available
    from app.db.models import CandidateSignal

    origin_sig = db.scalar(
        select(CandidateSignal)
        .where(CandidateSignal.linked_hype_id == snapshot.hype_id, CandidateSignal.state == "ACCEPTED")
        .order_by(CandidateSignal.id.asc())
        .limit(1)
    )
    metrics = metrics_from_snapshot_meta(
        meta,
        origin_signal_type=origin_sig.signal_type if origin_sig else None,
        origin_role=origin_sig.source_role if origin_sig else None,
    )

    prior = db.scalar(
        select(CandidateSnapshot)
        .where(
            CandidateSnapshot.hype_id == snapshot.hype_id,
            CandidateSnapshot.id != snapshot.id,
            CandidateSnapshot.snapshot_at < snapshot.snapshot_at,
        )
        .order_by(CandidateSnapshot.snapshot_at.desc())
        .limit(1)
    )
    prior_metrics = metrics_from_snapshot_meta(prior.metadata_json if prior else None) if prior else None
    completed = db.scalars(
        select(CandidateSnapshot).where(CandidateSnapshot.hype_id == snapshot.hype_id)
    ).all()
    payload = assess_metrics(
        metrics,
        prior_metrics=prior_metrics,
        confirmation_checkpoints=len(completed),
    )
    row = persist_assessment(db, snapshot.hype_id, payload, snapshot_id=snapshot.id)
    db.commit()
    db.refresh(row)
    return row


def manual_override(
    db: Session,
    hype_id: int,
    *,
    formation_stage: Optional[str] = None,
    formation_pattern: Optional[str] = None,
) -> CandidateTrendAssessment:
    """Write a manual override assessment; keep last engine suggestion in metrics_json."""
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise ValueError("hype not found")
    last = db.scalar(
        select(CandidateTrendAssessment)
        .where(CandidateTrendAssessment.hype_id == hype_id)
        .order_by(CandidateTrendAssessment.assessed_at.desc(), CandidateTrendAssessment.id.desc())
        .limit(1)
    )
    suggested = {
        "formation_stage": last.formation_stage if last else None,
        "formation_pattern": last.formation_pattern if last else None,
        "trend_direction": last.trend_direction if last else None,
        "pattern_confidence": last.pattern_confidence if last else None,
    }
    payload = {
        "formation_stage": formation_stage or (last.formation_stage if last else "SEED"),
        "trend_direction": last.trend_direction if last else "INSUFFICIENT_DATA",
        "formation_pattern": formation_pattern or (last.formation_pattern if last else "UNKNOWN"),
        "pattern_confidence": last.pattern_confidence if last else "LOW",
        "reasons_json": {
            "manual": ["Manual override"],
            "suggested": suggested,
            "pattern": (last.reasons_json or {}).get("pattern") if last else [],
            "stage": (last.reasons_json or {}).get("stage") if last else [],
            "direction": (last.reasons_json or {}).get("direction") if last else [],
        },
        "missing_evidence_json": last.missing_evidence_json if last else {},
        "metrics_json": {
            **(last.metrics_json or {}),
            "suggested": suggested,
            "manual_override": True,
        },
        "engine_version": TREND_ENGINE_VERSION,
    }
    row = persist_assessment(db, hype_id, payload, snapshot_id=last.snapshot_id if last else None, is_manual_override=True)
    # Mirror onto hype candidate status fields without deleting history
    if formation_stage:
        # Map stage to legacy candidate_status loosely
        mapping = {
            "SEED": "OPEN",
            "WATCHING": "WATCHING",
            "FORMATION": "FORMATION",
            "BREAKOUT": "BREAKOUT",
            "SATURATING": "SATURATING",
            "DECLINING": "DECLINING",
            "CLOSED": "CLOSED",
        }
        hype.candidate_status = mapping.get(formation_stage, hype.candidate_status)
    if formation_pattern:
        hype.formation_pattern = formation_pattern
    hype.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def latest_assessment(db: Session, hype_id: int) -> Optional[CandidateTrendAssessment]:
    return db.scalar(
        select(CandidateTrendAssessment)
        .where(CandidateTrendAssessment.hype_id == hype_id)
        .order_by(CandidateTrendAssessment.assessed_at.desc(), CandidateTrendAssessment.id.desc())
        .limit(1)
    )


def list_assessments(db: Session, hype_id: int) -> list[CandidateTrendAssessment]:
    return list(
        db.scalars(
            select(CandidateTrendAssessment)
            .where(CandidateTrendAssessment.hype_id == hype_id)
            .order_by(CandidateTrendAssessment.assessed_at.asc(), CandidateTrendAssessment.id.asc())
        ).all()
    )


def flatten_reasons(assessment: Optional[CandidateTrendAssessment]) -> list[str]:
    if not assessment or not assessment.reasons_json:
        return []
    out: list[str] = []
    for key in ("direction", "stage", "pattern", "manual"):
        vals = assessment.reasons_json.get(key) or []
        if isinstance(vals, list):
            out.extend(str(v) for v in vals)
    return out


def flatten_missing(assessment: Optional[CandidateTrendAssessment]) -> list[str]:
    if not assessment or not assessment.missing_evidence_json:
        return []
    out: list[str] = []
    for key in ("pattern", "stage", "direction"):
        vals = assessment.missing_evidence_json.get(key) or []
        if isinstance(vals, list):
            out.extend(str(v) for v in vals)
    return out


def last_meaningful_change(assessment: Optional[CandidateTrendAssessment]) -> Optional[str]:
    if not assessment:
        return None
    deltas = (assessment.metrics_json or {}).get("deltas") or {}
    parts = []
    for key, val in deltas.items():
        if isinstance(val, int) and val != 0:
            parts.append(f"{key}={val:+d}")
    if parts:
        return "; ".join(parts[:4])
    reasons = flatten_reasons(assessment)
    return reasons[0] if reasons else None


def review_flags(assessment: Optional[CandidateTrendAssessment]) -> list[str]:
    flags: list[str] = []
    if not assessment:
        flags.append("manual override needed")
        return flags
    if assessment.formation_pattern == "UNKNOWN" or assessment.pattern_confidence == "LOW":
        flags.append("pattern uncertain")
    if flatten_missing(assessment):
        flags.append("missing evidence")
    if assessment.trend_direction == "INSUFFICIENT_DATA":
        flags.append("missing evidence")
    if assessment.is_manual_override:
        flags.append("manual override needed")
    suggested = (assessment.metrics_json or {}).get("suggested") or {}
    if assessment.is_manual_override and suggested:
        if suggested.get("formation_stage") and suggested.get("formation_stage") != assessment.formation_stage:
            flags.append("stage conflict")
        if suggested.get("formation_pattern") and suggested.get("formation_pattern") != assessment.formation_pattern:
            flags.append("stage conflict")
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def radar_group_for(assessment: Optional[CandidateTrendAssessment]) -> str:
    """Bucket for Daily Hype Radar — no hidden score."""
    if not assessment:
        return "Needs Review"
    stage = assessment.formation_stage
    direction = assessment.trend_direction
    pattern = assessment.formation_pattern
    conf = assessment.pattern_confidence
    missing = flatten_missing(assessment)

    if pattern == "UNKNOWN" or (conf == "LOW" and missing) or "stage conflict" in review_flags(assessment):
        return "Needs Review"
    if direction in {"DECELERATING", "DORMANT"} or stage in {"DECLINING", "SATURATING", "CLOSED"}:
        return "Cooling"
    if direction == "ACCELERATING":
        return "Accelerating"
    if direction == "BROADENING":
        return "Broadening"
    if stage in {"SEED", "WATCHING", "FORMATION"} or direction in {"STEADY", "INSUFFICIENT_DATA"}:
        return "Emerging"
    return "Emerging"
