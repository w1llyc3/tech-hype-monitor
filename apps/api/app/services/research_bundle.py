"""Export local research bundle Markdown for ChatGPT Pro handoff (no API)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    AccountEvent,
    CandidateSignal,
    CandidateSnapshot,
    CandidateTrendAssessment,
    HypeAlias,
    HypeCandidate,
    RawEvent,
)
from app.services.trend_assess import latest_assessment, list_assessments

ROOT = Path(__file__).resolve().parents[4]
EXPORTS = ROOT / "exports"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s[:60] or "candidate"


def _chatgpt_prompt(hype: HypeCandidate) -> str:
    return f"""You are helping research a technology hype candidate for a local-first Tech Hype Monitor.

Candidate: {hype.canonical_name}
T0 (public disclosure): {hype.public_disclosure_t0}

Please:
1. Explain the technology/phrase in plain English.
2. Verify primary sources where possible from the evidence listed in the research bundle.
3. Identify what is genuinely new vs a rename/reframe of an existing concept.
4. Explain why the trend may be spreading (or why evidence is weak).
5. Identify key people/entities involved.
6. List uncertainties and what evidence is still missing.
7. Do NOT suggest tokens, tickers, trading, or DEX launches.
"""


def export_research_bundle(db: Session, hype_id: int, exports_dir: Optional[Path] = None) -> Path:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise ValueError("hype not found")

    out_dir = Path(exports_dir or EXPORTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"hype_{hype.id}_{_slug(hype.canonical_name)}_research_bundle.md"

    aliases = db.scalars(select(HypeAlias).where(HypeAlias.hype_id == hype.id)).all()
    snaps = db.scalars(
        select(CandidateSnapshot)
        .where(CandidateSnapshot.hype_id == hype.id)
        .order_by(CandidateSnapshot.snapshot_at.asc())
    ).all()
    assessments = list_assessments(db, hype.id)
    latest = latest_assessment(db, hype.id)
    signals = db.scalars(
        select(CandidateSignal).where(CandidateSignal.linked_hype_id == hype.id)
    ).all()

    lines: list[str] = []
    lines.append(f"# Research Bundle — {hype.canonical_name}")
    lines.append("")
    lines.append("## Candidate summary")
    lines.append(f"- Canonical name: {hype.canonical_name}")
    lines.append(f"- Plain English: {hype.plain_english or '—'}")
    lines.append(f"- Status: {hype.candidate_status}")
    lines.append(f"- T0 public disclosure: {hype.public_disclosure_t0}")
    lines.append(f"- Aliases: {', '.join(a.alias for a in aliases) or '—'}")
    lines.append("")

    if latest:
        lines.append("## Current trend assessment")
        lines.append(f"- Formation Stage: {latest.formation_stage}")
        lines.append(f"- Trend Direction: {latest.trend_direction}")
        lines.append(f"- Formation Pattern: {latest.formation_pattern} ({latest.pattern_confidence})")
        lines.append(f"- Engine version: {latest.engine_version}")
        lines.append(f"- Manual override: {latest.is_manual_override}")
        reasons = latest.reasons_json or {}
        missing = latest.missing_evidence_json or {}
        lines.append(f"- Why: {reasons}")
        lines.append(f"- Missing evidence: {missing}")
        lines.append("")

    lines.append("## Origin / signals")
    for s in signals:
        lines.append(
            f"- signal#{s.id} {s.signal_type} `{s.candidate_text}` state={s.state} role={s.source_role}"
        )
    lines.append("")

    lines.append("## Snapshots")
    for snap in snaps:
        meta = snap.metadata_json or {}
        lines.append(
            f"- {snap.checkpoint} at {snap.snapshot_at}: "
            f"mentions={snap.mention_count} indep={snap.independent_account_count} "
            f"platforms={snap.platform_count} "
            f"gh_post_t0={meta.get('github_repo_count_post_t0')} "
            f"hf_spaces_post_t0={meta.get('hf_space_count_post_t0')} "
            f"hn={meta.get('hn_matching_story_count')}"
        )
    lines.append("")

    lines.append("## Trend assessments (history)")
    for a in assessments:
        lines.append(
            f"- {a.assessed_at}: stage={a.formation_stage} dir={a.trend_direction} "
            f"pattern={a.formation_pattern} override={a.is_manual_override} v={a.engine_version}"
        )
    lines.append("")

    lines.append("## Evidence trail (raw events linked via signals)")
    for s in signals:
        ev = db.get(RawEvent, s.raw_event_id)
        if not ev:
            continue
        lines.append(
            f"- [{ev.platform}] {ev.published_at or ev.created_at}: "
            f"{(ev.title or ev.raw_text or '')[:120]} — {ev.canonical_url}"
        )
    lines.append("")

    lines.append("## Account propagation")
    account_ids = set()
    for s in signals:
        if not s.account_event_id:
            continue
        ae = db.get(AccountEvent, s.account_event_id)
        if ae:
            account_ids.add(ae.account_id)
    for aid in sorted(account_ids):
        acc = db.get(Account, aid)
        if acc:
            lines.append(f"- @{acc.handle} role={acc.primary_bucket} tier={acc.universe_tier}")
    lines.append("")

    lines.append("## Questions for research")
    lines.append("- What is the primary-source first public disclosure?")
    lines.append("- Is this a new capability, a rename, or a meme frame?")
    lines.append("- Which independent communities adopted it without economic conflict?")
    lines.append("- What evidence is still missing for formation vs breakout?")
    lines.append("")

    lines.append("## ChatGPT Research Prompt")
    lines.append("```")
    lines.append(_chatgpt_prompt(hype))
    lines.append("```")
    lines.append("")
    lines.append("Do not include token/DEX guidance.")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def chatgpt_research_prompt(db: Session, hype_id: int) -> str:
    hype = db.get(HypeCandidate, hype_id)
    if not hype:
        raise ValueError("hype not found")
    return _chatgpt_prompt(hype)
