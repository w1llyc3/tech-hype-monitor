"""Explainable formation pattern + stage engine (no opaque score)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

TREND_ENGINE_VERSION = "0.1"

FORMATION_PATTERNS = {
    "NAMING_FIRST",
    "OBJECT_FIRST",
    "EMBEDDED_OBJECT",
    "REFRAMING",
    "CAPABILITY_LED",
    "CATEGORY_CONVERGENCE",
    "REACTIVATED_TERM",
    "PROOF_LED",
    "VISUAL_PROOF_LED",
    "LORE_NATIVE",
    "UNKNOWN",
}

FORMATION_STAGES = {
    "SEED",
    "WATCHING",
    "FORMATION",
    "BREAKOUT",
    "SATURATING",
    "DECLINING",
    "CLOSED",
}


@dataclass
class EvidenceMetrics:
    """Normalized metrics fed to the trend engine (live or replay)."""

    independent_amplifiers: int = 0
    total_monitored_accounts: int = 0
    hq_independent_amplifiers: int = 0
    active_platforms: list[str] = field(default_factory=list)
    mention_count: int = 0
    github_post_t0: int = 0
    github_preexisting: int = 0
    hf_spaces_post_t0: int = 0
    hf_models_post_t0: int = 0
    hf_datasets_post_t0: int = 0
    hf_preexisting: int = 0
    hn_stories: int = 0
    origin_signal_type: Optional[str] = None
    origin_role: Optional[str] = None
    origin_handle: Optional[str] = None
    source_detachment: Optional[str] = None
    has_demo_or_repo_proof: bool = False
    has_visual_proof: bool = False
    has_capability_launch: bool = False
    naming_fragmented: bool = False
    prior_concept_exists: bool = False
    lore_evidence: bool = False
    confirmation_checkpoints: int = 0
    evidence_incomplete: bool = False

    @property
    def platform_count(self) -> int:
        return len(self.active_platforms)

    @property
    def post_t0_derivatives(self) -> int:
        return (
            self.github_post_t0
            + self.hf_spaces_post_t0
            + self.hf_models_post_t0
            + self.hf_datasets_post_t0
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["platform_count"] = self.platform_count
        d["post_t0_derivatives"] = self.post_t0_derivatives
        return d


@dataclass
class PatternResult:
    suggested_pattern: str
    confidence: str  # LOW / MEDIUM / HIGH
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    formation_stage: str
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _role_blob(role: Optional[str]) -> str:
    return (role or "").upper()


def infer_formation_pattern(m: EvidenceMetrics) -> PatternResult:
    reasons: list[str] = []
    missing: list[str] = []
    role = _role_blob(m.origin_role)
    sig = (m.origin_signal_type or "").upper()

    # REACTIVATED_TERM
    if m.github_preexisting + m.hf_preexisting >= 1 and m.post_t0_derivatives >= 1 and (
        m.independent_amplifiers >= 1 or m.platform_count >= 2
    ):
        reasons.append("Meaningful PREEXISTING inventory with fresh post-T0 derivatives")
        reasons.append("Fresh amplification after T0")
        conf = "HIGH" if m.independent_amplifiers >= 2 else "MEDIUM"
        return PatternResult("REACTIVATED_TERM", conf, reasons, missing)

    # LORE_NATIVE — only with clear lore evidence
    if m.lore_evidence:
        reasons.append("Persistent persona/lore evidence present")
        return PatternResult("LORE_NATIVE", "MEDIUM", reasons, missing)

    # VISUAL_PROOF_LED
    if m.has_visual_proof and (m.independent_amplifiers >= 1 or m.post_t0_derivatives >= 1):
        reasons.append("Visual/embodied demo appears to drive spread")
        return PatternResult("VISUAL_PROOF_LED", "MEDIUM", reasons, missing)

    # PROOF_LED
    if m.has_demo_or_repo_proof and m.naming_fragmented and m.post_t0_derivatives >= 1:
        reasons.append("Working demo/repo drives propagation before naming stabilizes")
        reasons.append("Naming remains fragmented")
        return PatternResult("PROOF_LED", "MEDIUM", reasons, missing)

    # REFRAMING
    if sig in {"REFRAME"} or "better term" in " ".join(reasons).lower():
        if m.prior_concept_exists or sig == "REFRAME":
            reasons.append("Replacement / better-term origin signal")
            if m.independent_amplifiers >= 1:
                reasons.append("Fresh adoption of new label after T0")
                return PatternResult("REFRAMING", "MEDIUM", reasons, missing)
            missing.append("Independent adoption of replacement label")
            return PatternResult("REFRAMING", "LOW", reasons, missing)

    # NAMING_FIRST
    namer = any(tok in role for tok in ("NARRATIVE_NAMER", "FRAMER", "NARRATIVE_FRAMER", "CATEGORY_FRAMER"))
    if sig in {"NEW_TERM", "REFRAME"} and namer:
        reasons.append(f"Origin signal {sig} from naming/framer role")
        if m.independent_amplifiers >= 1 or m.platform_count >= 2:
            reasons.append("Same label appears across independent accounts/platforms")
            conf = "HIGH" if m.independent_amplifiers >= 2 and m.platform_count >= 2 else "MEDIUM"
            return PatternResult("NAMING_FIRST", conf, reasons, missing)
        missing.append("Independent adoption of the coined label")
        return PatternResult("NAMING_FIRST", "LOW", reasons, missing)

    # EMBEDDED_OBJECT
    if sig in {"EMBEDDED_OBJECT"} or (sig == "WEIRD_AI_EVENT" and "OBJECT" in role):
        reasons.append("Small named artifact extracted from broader event")
        if m.independent_amplifiers >= 1:
            reasons.append("Object later independently amplified")
            return PatternResult("EMBEDDED_OBJECT", "MEDIUM", reasons, missing)
        missing.append("Independent amplification of the embedded object")
        return PatternResult("EMBEDDED_OBJECT", "LOW", reasons, missing)

    # OBJECT_FIRST
    if sig in {"EMBEDDED_OBJECT", "PRODUCT_PROOF", "VISUAL_PROOF"} or "OBJECT" in role:
        reasons.append("Concrete object/artifact framing at origin")
        if m.independent_amplifiers >= 1:
            return PatternResult("OBJECT_FIRST", "MEDIUM", reasons, missing)
        missing.append("Independent repetition around the object")
        return PatternResult("OBJECT_FIRST", "LOW", reasons, missing)

    # CAPABILITY_LED
    if m.has_capability_launch:
        reasons.append("Capability launch / research event drives adoption")
        if m.naming_fragmented:
            reasons.append("Naming may stay fragmented")
        return PatternResult("CAPABILITY_LED", "MEDIUM", reasons, missing)

    # CATEGORY_CONVERGENCE
    if m.independent_amplifiers >= 3 and m.platform_count >= 3 and m.post_t0_derivatives >= 2:
        reasons.append("Multiple independent builders expose similar capability")
        reasons.append("No single source fully owns the category")
        return PatternResult("CATEGORY_CONVERGENCE", "MEDIUM", reasons, missing)

    missing.append("Clearer origin signal type / role")
    missing.append("Independent amplifier or post-T0 derivative confirmation")
    if m.evidence_incomplete:
        missing.append("INCOMPLETE_EVIDENCE in fixture coverage")
    return PatternResult("UNKNOWN", "LOW", ["Insufficient pattern evidence"], missing)


def infer_formation_stage(m: EvidenceMetrics, *, prior_stages: Optional[list[str]] = None) -> StageResult:
    reasons: list[str] = []
    missing: list[str] = []
    prior_stages = prior_stages or []

    # Never BREAKOUT from a single source
    single_source = m.independent_amplifiers == 0 and m.total_monitored_accounts <= 1

    # BREAKOUT
    if (
        not single_source
        and m.independent_amplifiers >= 3
        and m.platform_count >= 3
        and (m.confirmation_checkpoints >= 2 or m.post_t0_derivatives >= 2)
    ):
        reasons.append(">=3 independent amplifiers and >=3 platforms with persistence/derivatives")
        return StageResult("BREAKOUT", reasons, missing)

    if (
        not single_source
        and m.post_t0_derivatives >= 3
        and m.independent_amplifiers >= 2
        and m.platform_count >= 2
    ):
        reasons.append("Derivative acceleration plus independent propagation")
        return StageResult("BREAKOUT", reasons, missing)

    # FORMATION
    if m.independent_amplifiers >= 2:
        reasons.append(">=2 independent amplifiers")
        return StageResult("FORMATION", reasons, missing)
    if m.platform_count >= 2 and m.post_t0_derivatives >= 1:
        reasons.append(">=2 active platforms AND >=1 post-T0 derivative")
        return StageResult("FORMATION", reasons, missing)
    if m.confirmation_checkpoints >= 2 and (m.independent_amplifiers >= 1 or m.post_t0_derivatives >= 1):
        reasons.append("Repeated confirmation across >=2 checkpoints")
        return StageResult("FORMATION", reasons, missing)

    # WATCHING
    if m.independent_amplifiers >= 1:
        reasons.append("1 independent amplifier")
        return StageResult("WATCHING", reasons, missing)
    if m.platform_count >= 2:
        reasons.append("2 active platforms")
        return StageResult("WATCHING", reasons, missing)
    if m.post_t0_derivatives >= 1:
        reasons.append(">=1 post-T0 derivative")
        return StageResult("WATCHING", reasons, missing)

    # SEED
    reasons.append("Origin/source exists with no independent amplifiers")
    if m.platform_count <= 1:
        reasons.append("<=1 active platform")
    if m.post_t0_derivatives == 0:
        reasons.append("No post-T0 derivative")
    missing.append("Independent amplifiers")
    missing.append("Cross-platform confirmation")
    return StageResult("SEED", reasons, missing)


def metrics_from_snapshot_meta(meta: Optional[dict[str, Any]], **overrides: Any) -> EvidenceMetrics:
    meta = meta or {}
    platforms = list(meta.get("platforms_active") or [])
    m = EvidenceMetrics(
        independent_amplifiers=int(meta.get("independent_account_count") or 0),
        total_monitored_accounts=int(meta.get("total_monitored_account_count") or 0),
        hq_independent_amplifiers=int(
            meta.get("high_quality_independent_amplifier_count")
            or meta.get("high_quality_amplifier_count")
            or 0
        ),
        active_platforms=platforms,
        mention_count=int(meta.get("mention_count") or 0),
        github_post_t0=int(meta.get("github_repo_count_post_t0") or meta.get("github_repo_count") or 0),
        github_preexisting=int(meta.get("github_repo_count_preexisting") or 0),
        hf_spaces_post_t0=int(meta.get("hf_space_count_post_t0") or meta.get("hf_space_count") or 0),
        hf_models_post_t0=int(meta.get("hf_model_count_post_t0") or meta.get("hf_model_count") or 0),
        hf_datasets_post_t0=int(meta.get("hf_dataset_count_post_t0") or meta.get("hf_dataset_count") or 0),
        hf_preexisting=int(
            (meta.get("hf_space_count_preexisting") or 0)
            + (meta.get("hf_model_count_preexisting") or 0)
            + (meta.get("hf_dataset_count_preexisting") or 0)
        ),
        hn_stories=int(meta.get("hn_matching_story_count") or 0),
        origin_handle=meta.get("origin_account_handle"),
        source_detachment=meta.get("source_detachment_level"),
    )
    for k, v in overrides.items():
        if hasattr(m, k):
            setattr(m, k, v)
    return m
