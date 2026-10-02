"""Checkpoint-to-checkpoint trend direction (no fake deltas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.trend_engine import EvidenceMetrics


@dataclass
class TrendDeltaResult:
    trend_direction: str
    reasons: list[str] = field(default_factory=list)
    deltas: dict[str, Optional[int]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def compute_deltas(
    current: EvidenceMetrics,
    prior: Optional[EvidenceMetrics],
    *,
    prior_was_skipped: bool = False,
) -> TrendDeltaResult:
    if prior is None or prior_was_skipped:
        return TrendDeltaResult(
            trend_direction="INSUFFICIENT_DATA",
            reasons=["No prior completed checkpoint to compare"],
            deltas={
                "delta_mentions": None,
                "delta_independent_amplifiers": None,
                "delta_platforms": None,
                "delta_github_new_repos": None,
                "delta_hf_new_spaces": None,
                "delta_hf_new_models": None,
                "delta_hn_stories": None,
            },
            missing=["Prior checkpoint snapshot"],
        )

    deltas = {
        "delta_mentions": current.mention_count - prior.mention_count,
        "delta_independent_amplifiers": current.independent_amplifiers - prior.independent_amplifiers,
        "delta_platforms": current.platform_count - prior.platform_count,
        "delta_github_new_repos": current.github_post_t0 - prior.github_post_t0,
        "delta_hf_new_spaces": current.hf_spaces_post_t0 - prior.hf_spaces_post_t0,
        "delta_hf_new_models": current.hf_models_post_t0 - prior.hf_models_post_t0,
        "delta_hn_stories": current.hn_stories - prior.hn_stories,
    }

    reasons: list[str] = []
    amp_d = deltas["delta_independent_amplifiers"] or 0
    plat_d = deltas["delta_platforms"] or 0
    gh_d = deltas["delta_github_new_repos"] or 0
    hf_d = (deltas["delta_hf_new_spaces"] or 0) + (deltas["delta_hf_new_models"] or 0)
    ment_d = deltas["delta_mentions"] or 0

    growth_signals = sum(1 for x in (amp_d, plat_d, gh_d, hf_d) if x > 0)
    shrink_signals = sum(1 for x in (amp_d, plat_d, gh_d, hf_d, ment_d) if x < 0)

    if current.independent_amplifiers == 0 and current.post_t0_derivatives == 0 and ment_d <= 0:
        reasons.append("No independent amplifiers or new derivatives vs prior")
        return TrendDeltaResult("DORMANT", reasons, deltas)

    if amp_d >= 2 or (amp_d >= 1 and (gh_d > 0 or hf_d > 0)):
        reasons.append("Independent amplifiers and/or derivatives increasing")
        return TrendDeltaResult("ACCELERATING", reasons, deltas)

    if plat_d > 0 and amp_d >= 0:
        reasons.append("Active platforms broadened without amplifier loss")
        return TrendDeltaResult("BROADENING", reasons, deltas)

    if growth_signals == 0 and shrink_signals == 0:
        reasons.append("Metrics largely unchanged vs prior checkpoint")
        return TrendDeltaResult("STEADY", reasons, deltas)

    if shrink_signals >= 2 and growth_signals == 0:
        reasons.append("Multiple metrics declined vs prior checkpoint")
        return TrendDeltaResult("DECELERATING", reasons, deltas)

    if growth_signals >= 1 and shrink_signals == 0:
        reasons.append("At least one propagation metric increased")
        return TrendDeltaResult("ACCELERATING" if amp_d > 0 or gh_d > 0 or hf_d > 0 else "BROADENING", reasons, deltas)

    if shrink_signals >= 1 and growth_signals == 0:
        reasons.append("Propagation metrics softened")
        return TrendDeltaResult("DECELERATING", reasons, deltas)

    reasons.append("Mixed checkpoint deltas")
    return TrendDeltaResult("STEADY", reasons, deltas)


def deltas_from_meta(
    current_meta: Optional[dict[str, Any]],
    prior_meta: Optional[dict[str, Any]],
    *,
    prior_was_skipped: bool = False,
) -> TrendDeltaResult:
    from app.services.trend_engine import metrics_from_snapshot_meta

    cur = metrics_from_snapshot_meta(current_meta)
    prior = metrics_from_snapshot_meta(prior_meta) if prior_meta is not None else None
    return compute_deltas(cur, prior, prior_was_skipped=prior_was_skipped)
