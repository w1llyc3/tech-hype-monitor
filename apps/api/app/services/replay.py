"""Historical replay from frozen local fixtures (no live internet)."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.timeutil import ensure_aware
from app.services.trend_assess import assess_metrics
from app.services.trend_engine import EvidenceMetrics

ROOT = Path(__file__).resolve().parents[4]
REPLAY_ROOT = ROOT / "replay"
CASES_DIR = REPLAY_ROOT / "cases"
FIXTURES_DIR = REPLAY_ROOT / "fixtures"

CHECKPOINTS = [
    ("T0", timedelta(0)),
    ("+1H", timedelta(hours=1)),
    ("+6H", timedelta(hours=6)),
    ("+24H", timedelta(hours=24)),
    ("+72H", timedelta(hours=72)),
    ("+7D", timedelta(days=7)),
    ("+30D", timedelta(days=30)),
]

EVIDENCE_PHASE_ORDER = {
    "PRE_HYPE": 0,
    "FORMATION": 1,
    "BREAKOUT": 2,
    "POST_OUTCOME": 3,
}


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def load_case(case_id: str, cases_dir: Optional[Path] = None) -> dict[str, Any]:
    path = Path(cases_dir or CASES_DIR) / f"{case_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Case not found: {path}")
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def detection_view(case: dict[str, Any]) -> dict[str, Any]:
    """Strip evaluation block so the trend engine cannot read reference labels."""
    view = deepcopy(case)
    view.pop("evaluation", None)
    return view


def list_cases(cases_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    base = Path(cases_dir or CASES_DIR)
    rows = []
    for path in sorted(base.glob("*.json")):
        with path.open(encoding="utf-8-sig") as f:
            data = json.load(f)
        ev = data.get("evaluation") or {}
        rows.append(
            {
                "case_id": data.get("case_id") or path.stem,
                "display_name": data.get("display_name"),
                "fixture_status": data.get("fixture_status"),
                "t0": data.get("t0"),
                "reference_pattern": ev.get("reference_pattern"),
                "evaluation_notes": ev.get("notes"),
                "event_count": len(data.get("events") or []),
            }
        )
    return rows


def visible_events(
    case: dict[str, Any],
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Events with occurred_at <= cutoff. Uses immutable occurred_at only."""
    out = []
    for ev in case.get("events") or []:
        ts = _parse_dt(ev.get("occurred_at"))
        if ts is None:
            continue
        if ensure_aware(ts) <= ensure_aware(cutoff):
            out.append(ev)
    return out


def _platforms_from_events(events: list[dict[str, Any]]) -> list[str]:
    mapping = {
        "x": "X",
        "hn": "HN",
        "hacker_news": "HN",
        "github": "GitHub",
        "huggingface": "Hugging Face",
        "hf": "Hugging Face",
        "official_rss": "Official/RSS",
        "rss": "Official/RSS",
    }
    seen: list[str] = []
    for e in events:
        p = mapping.get((e.get("platform") or "").lower())
        if p and p not in seen:
            # Only count platform if evidence is confirming (not merely PREEXISTING inventory)
            phase = (e.get("evidence_phase") or "").upper()
            kind = (e.get("source_type") or e.get("event_kind") or "").upper()
            if kind in {"PREEXISTING_REPO", "PREEXISTING_MODEL", "PREEXISTING_SPACE"}:
                continue
            if phase == "PRE_HYPE" and kind.startswith("PREEXISTING"):
                continue
            seen.append(p)
    return seen


def metrics_at_cutoff(case: dict[str, Any], cutoff: datetime) -> EvidenceMetrics:
    t0 = _parse_dt(case.get("t0")) or cutoff
    events = visible_events(case, cutoff)
    incomplete = any(
        (e.get("coverage_status") or "").upper() == "INCOMPLETE_EVIDENCE" for e in events
    ) or (case.get("fixture_status") or "").upper() in {"PARTIAL", "NEEDS_RESEARCH"}

    origin = None
    for e in sorted(events, key=lambda x: _parse_dt(x.get("occurred_at")) or cutoff):
        if e.get("account_handle") and (e.get("platform") or "").lower() in {"x", "twitter"}:
            origin = e
            break
    if origin is None and events:
        origin = events[0]

    origin_handle = (origin or {}).get("account_handle")
    origin_role = (origin or {}).get("account_role")
    origin_signal = (origin or {}).get("signal_type")

    # Independent amplifiers: distinct X handles excluding origin
    x_handles = set()
    for e in events:
        if (e.get("platform") or "").lower() not in {"x", "twitter"}:
            continue
        h = (e.get("account_handle") or "").lstrip("@").lower()
        if h:
            x_handles.add(h)
    origin_norm = (origin_handle or "").lstrip("@").lower() or None
    independent = {h for h in x_handles if origin_norm is None or h != origin_norm}

    github_post = 0
    github_pre = 0
    hf_spaces_post = 0
    hf_models_post = 0
    hf_pre = 0
    hn = 0
    has_demo = False
    has_visual = False
    has_capability = False
    naming_fragmented = False
    prior_concept = False
    lore = False

    for e in events:
        plat = (e.get("platform") or "").lower()
        kind = (e.get("source_type") or e.get("event_kind") or "").upper()
        ts = _parse_dt(e.get("occurred_at"))
        post = ts is not None and ensure_aware(ts) >= ensure_aware(t0)

        if plat in {"github"}:
            if kind in {"PREEXISTING_REPO"} or (e.get("timing_class") or "").upper() == "PREEXISTING":
                github_pre += 1
            elif post and kind not in {"PREEXISTING_REPO"}:
                github_post += 1
                has_demo = has_demo or kind in {"REPO", "DEMO", "PROOF"}
        if plat in {"huggingface", "hf"}:
            if kind in {"PREEXISTING_MODEL", "PREEXISTING_SPACE", "PREEXISTING_DATASET"}:
                hf_pre += 1
            elif post:
                if "SPACE" in kind:
                    hf_spaces_post += 1
                elif "MODEL" in kind:
                    hf_models_post += 1
                else:
                    hf_spaces_post += 1
        if plat in {"hn", "hacker_news"} and post:
            hn += 1
        if kind in {"DEMO", "PROOF", "REPO"}:
            has_demo = True
        if kind in {"VISUAL_PROOF", "ROBOT_DEMO"}:
            has_visual = True
        if kind in {"CAPABILITY_LAUNCH", "RESEARCH_RELEASE"}:
            has_capability = True
        if e.get("naming_fragmented"):
            naming_fragmented = True
        if e.get("prior_concept_exists"):
            prior_concept = True
        if e.get("lore_evidence"):
            lore = True
        if (e.get("signal_type") or "").upper() == "REFRAME":
            prior_concept = True

    platforms = _platforms_from_events(events)
    # X platform only if there is at least one X event in window
    if any((e.get("platform") or "").lower() in {"x", "twitter"} for e in events):
        if "X" not in platforms:
            platforms.insert(0, "X")
    if hn and "HN" not in platforms:
        platforms.append("HN")
    if github_post and "GitHub" not in platforms:
        platforms.append("GitHub")
    if (hf_spaces_post + hf_models_post) and "Hugging Face" not in platforms:
        platforms.append("Hugging Face")

    return EvidenceMetrics(
        independent_amplifiers=len(independent),
        total_monitored_accounts=len(x_handles),
        hq_independent_amplifiers=sum(
            1
            for e in events
            if (e.get("account_handle") or "").lstrip("@").lower() in independent
            and (
                (e.get("universe_tier") or "").upper() == "CORE"
                or (e.get("monitor_priority") or "").upper() == "P0"
            )
        ),
        active_platforms=platforms,
        mention_count=sum(1 for e in events if (e.get("platform") or "").lower() in {"x", "twitter"}),
        github_post_t0=github_post,
        github_preexisting=github_pre,
        hf_spaces_post_t0=hf_spaces_post,
        hf_models_post_t0=hf_models_post,
        hf_preexisting=hf_pre,
        hn_stories=hn,
        origin_signal_type=origin_signal,
        origin_role=origin_role,
        origin_handle=origin_handle,
        has_demo_or_repo_proof=has_demo,
        has_visual_proof=has_visual,
        has_capability_launch=has_capability,
        naming_fragmented=naming_fragmented,
        prior_concept_exists=prior_concept,
        lore_evidence=lore,
        evidence_incomplete=incomplete,
        source_detachment=(
            "NONE"
            if len(independent) == 0 and len(platforms) <= 1
            else "WEAK"
            if len(independent) == 1 and len(platforms) <= 1
            else "EMERGING"
            if len(independent) >= 2 or len(platforms) >= 2
            else "UNKNOWN"
        ),
    )


@dataclass
class ReplayCheckpointResult:
    case_id: str
    checkpoint: str
    cutoff: str
    visible_evidence_count: int
    origin_source_account: Optional[str]
    independent_amplifiers: int
    active_platforms: list[str]
    post_t0_github: int
    post_t0_hf_spaces: int
    post_t0_hf_models: int
    hn_evidence: int
    source_detachment: Optional[str]
    suggested_formation_stage: str
    suggested_trend_direction: str
    suggested_formation_pattern: str
    pattern_confidence: str
    pattern_evidence: list[str]
    missing_evidence: dict[str, Any]
    metrics: dict[str, Any]
    evaluation_comparison: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case_id,
            "checkpoint": self.checkpoint,
            "cutoff": self.cutoff,
            "visible_evidence_count": self.visible_evidence_count,
            "origin_source_account": self.origin_source_account,
            "independent_amplifiers": self.independent_amplifiers,
            "active_platforms": self.active_platforms,
            "post_t0_github_derivatives": self.post_t0_github,
            "post_t0_hf_derivatives": {
                "spaces": self.post_t0_hf_spaces,
                "models": self.post_t0_hf_models,
            },
            "hn_evidence": self.hn_evidence,
            "source_detachment": self.source_detachment,
            "suggested_formation_stage": self.suggested_formation_stage,
            "suggested_trend_direction": self.suggested_trend_direction,
            "suggested_formation_pattern": self.suggested_formation_pattern,
            "pattern_confidence": self.pattern_confidence,
            "pattern_evidence": self.pattern_evidence,
            "missing_evidence": self.missing_evidence,
            "metrics": self.metrics,
            "evaluation_comparison": self.evaluation_comparison,
        }


def replay_case(
    case_id: str,
    *,
    cutoff: Optional[datetime] = None,
    checkpoint: Optional[str] = None,
    cases_dir: Optional[Path] = None,
    include_evaluation_compare: bool = True,
) -> list[ReplayCheckpointResult]:
    raw = load_case(case_id, cases_dir=cases_dir)
    case = detection_view(raw)  # engine never sees evaluation
    t0 = _parse_dt(case.get("t0"))
    if t0 is None:
        # No T0 => only empty/incomplete result
        return [
            ReplayCheckpointResult(
                case_id=case_id,
                checkpoint="T0",
                cutoff="",
                visible_evidence_count=0,
                origin_source_account=None,
                independent_amplifiers=0,
                active_platforms=[],
                post_t0_github=0,
                post_t0_hf_spaces=0,
                post_t0_hf_models=0,
                hn_evidence=0,
                source_detachment=None,
                suggested_formation_stage="SEED",
                suggested_trend_direction="INSUFFICIENT_DATA",
                suggested_formation_pattern="UNKNOWN",
                pattern_confidence="LOW",
                pattern_evidence=["Case missing t0 / frozen evidence"],
                missing_evidence={"case": ["t0", "events"]},
                metrics={},
            )
        ]

    targets = CHECKPOINTS
    if checkpoint:
        targets = [c for c in CHECKPOINTS if c[0] == checkpoint]
    if cutoff is not None:
        # Single ad-hoc cutoff
        targets = [("CUSTOM", cutoff - t0)]

    results: list[ReplayCheckpointResult] = []
    prior_metrics: Optional[EvidenceMetrics] = None
    ref_pattern = None
    if include_evaluation_compare:
        ref_pattern = ((raw.get("evaluation") or {}).get("reference_pattern"))

    for name, delta in targets:
        cp_time = cutoff if name == "CUSTOM" and cutoff is not None else t0 + delta
        events = visible_events(case, cp_time)
        metrics = metrics_at_cutoff(case, cp_time)
        assessed = assess_metrics(metrics, prior_metrics=prior_metrics, confirmation_checkpoints=len(results) + 1)
        compare = None
        if ref_pattern:
            compare = {
                "reference_pattern": ref_pattern,
                "suggested_pattern": assessed["formation_pattern"],
                "match": assessed["formation_pattern"] == ref_pattern,
            }
        results.append(
            ReplayCheckpointResult(
                case_id=case_id,
                checkpoint=name,
                cutoff=cp_time.isoformat(),
                visible_evidence_count=len(events),
                origin_source_account=metrics.origin_handle,
                independent_amplifiers=metrics.independent_amplifiers,
                active_platforms=list(metrics.active_platforms),
                post_t0_github=metrics.github_post_t0,
                post_t0_hf_spaces=metrics.hf_spaces_post_t0,
                post_t0_hf_models=metrics.hf_models_post_t0,
                hn_evidence=metrics.hn_stories,
                source_detachment=metrics.source_detachment,
                suggested_formation_stage=assessed["formation_stage"],
                suggested_trend_direction=assessed["trend_direction"],
                suggested_formation_pattern=assessed["formation_pattern"],
                pattern_confidence=assessed["pattern_confidence"],
                pattern_evidence=(assessed.get("reasons_json") or {}).get("pattern") or [],
                missing_evidence=assessed.get("missing_evidence_json") or {},
                metrics=assessed.get("metrics_json") or {},
                evaluation_comparison=compare,
            )
        )
        prior_metrics = metrics
    return results
