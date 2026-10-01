"""Deterministic, role-aware candidate extraction (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.db.models import Account

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "is",
    "are",
    "was",
    "were",
    "this",
    "that",
    "with",
    "from",
    "it",
    "as",
    "at",
    "by",
    "be",
    "new",
    "just",
    "like",
    "than",
    "into",
    "about",
    "over",
    "after",
    "before",
    "today",
    "great",
    "weather",
    "you",
    "your",
    "we",
    "our",
    "they",
    "their",
    "my",
    "me",
    "i",
}

TRAILING_CUT = STOPWORDS | {
    "where",
    "when",
    "which",
    "who",
    "what",
    "because",
    "so",
    "but",
    "while",
    "if",
}

GENERIC_CAPS = {
    "AI",
    "API",
    "HTTP",
    "HTTPS",
    "URL",
    "HTML",
    "CSS",
    "JS",
    "UI",
    "UX",
    "CEO",
    "CTO",
    "USA",
    "UK",
    "EU",
    "GPU",
    "CPU",
    "LLM",
    "GPT",
    "OK",
    "ID",
    "PDF",
    "FAQ",
    "NEW",
    "OLD",
    "YES",
    "NO",
}


@dataclass
class ExtractedCandidate:
    signal_type: str
    candidate_text: str
    normalized_text: str
    extraction_method: str
    trigger_reason: str
    initial_priority: Optional[str] = None
    source_role: Optional[str] = None


def normalize_candidate_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.lower()
    if t.startswith("$") or t.startswith("#"):
        t = t[1:]
    return t.strip()


def normalize_handle(handle: str) -> str:
    h = (handle or "").strip()
    if h.startswith("@"):
        h = h[1:]
    return h.lower()


def _priority_for_account(account: Account | None) -> str:
    if not account:
        return "MEDIUM"
    pri = (account.monitor_priority or "").upper()
    if pri == "P0":
        return "HIGH"
    if pri == "P1":
        return "MEDIUM"
    return "LOW"


def _role_blob(account: Account | None) -> str:
    if not account:
        return ""
    return f"{account.primary_bucket or ''} {account.secondary_role or ''}".upper()


def _has_role(blob: str, *tokens: str) -> bool:
    return any(tok in blob for tok in tokens)


def _is_onchain_only(account: Account | None) -> bool:
    blob = _role_blob(account)
    return _has_role(blob, "SYSTEM_ONCHAIN_SCOUT", "ONCHAIN_SCOUT") and not _has_role(
        blob, "TECH_TO_MEME", "NARRATIVE", "FRAMER", "OBJECT", "AMPLIFIER", "BRIDGE"
    )


def _extract_primitives(text: str) -> list[ExtractedCandidate]:
    out: list[ExtractedCandidate] = []
    seen: set[tuple[str, str]] = set()

    def add(signal_type: str, raw: str, method: str, reason: str) -> None:
        raw = raw.strip()
        if not raw or len(raw) > 512:
            return
        norm = normalize_candidate_text(raw)
        if not norm or len(norm) < 2:
            return
        key = (signal_type, norm)
        if key in seen:
            return
        seen.add(key)
        out.append(
            ExtractedCandidate(
                signal_type=signal_type,
                candidate_text=raw[:512],
                normalized_text=norm[:512],
                extraction_method=method,
                trigger_reason=reason,
            )
        )

    # Explicit naming / framing patterns
    patterns = [
        (
            r"(?i)\bi\s+call\s+(?:(?:this|it)\s+)?([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
            "NEW_TERM",
            "PATTERN_I_CALL_THIS",
            "Matched 'I call (this) X'",
        ),
        (
            r"(?i)\b(?:called|dubbed)\s+[\"']?([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})[\"']?",
            "NEW_TERM",
            "PATTERN_CALLED",
            "Matched 'called/dubbed X'",
        ),
        (
            r"(?i)\bthe\s+new\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
            "REFRAME",
            "PATTERN_THE_NEW",
            "Matched 'the new X'",
        ),
        (
            r"(?i)\b([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})\s+is\s+the\s+new\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
            "REFRAME",
            "PATTERN_X_IS_THE_NEW_Y",
            "Matched 'X is the new Y'",
        ),
        (
            r"(?i)\bi\s+prefer\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})\s+to\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
            "REFRAME",
            "PATTERN_PREFER_X_TO_Y",
            "Matched 'I prefer X to Y'",
        ),
        (
            r"(?i)\bthis\s+is\s+basically\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
            "REFRAME",
            "PATTERN_BASICALLY",
            "Matched 'this is basically X'",
        ),
        (
            r"(?i)\b([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})\s+is\s+a\s+better\s+term\s+than\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
            "REFRAME",
            "PATTERN_BETTER_TERM",
            "Matched 'X is a better term than Y'",
        ),
    ]

    def _trim_phrase(raw: str) -> str:
        parts = raw.strip(" .,!?;:\"'").split()
        while parts and parts[-1].lower().strip(".,!?;:\"'") in TRAILING_CUT:
            parts.pop()
        while parts and parts[0].lower().strip(".,!?;:\"'") in STOPWORDS:
            parts.pop(0)
        return " ".join(parts)

    for pattern, signal_type, method, reason in patterns:
        for m in re.finditer(pattern, text):
            if m.lastindex and m.lastindex >= 1:
                add(signal_type, _trim_phrase(m.group(1)), method, reason)

    # $TICKER
    for m in re.finditer(r"\$([A-Za-z]{2,15})\b", text):
        add("EMBEDDED_OBJECT", f"${m.group(1)}", "TICKER", "Matched $TICKER")

    # Hashtags
    for m in re.finditer(r"#([A-Za-z][\w]{1,40})", text):
        add("NEW_TERM", f"#{m.group(1)}", "HASHTAG", "Matched hashtag")

    # Quoted phrases
    for m in re.finditer(r"[\"“]([^\"”]{2,60})[\"”]", text):
        phrase = m.group(1).strip()
        if phrase and not phrase.lower() in STOPWORDS:
            add("NEW_TERM", phrase, "QUOTED_PHRASE", "Matched quoted phrase")

    # Acronym in parentheses: Foo Bar Baz (FBB)
    for m in re.finditer(r"\(([A-Z]{2,10})\)", text):
        if m.group(1) not in GENERIC_CAPS:
            add("EMBEDDED_OBJECT", m.group(1), "PAREN_ACRONYM", "Matched acronym in parentheses")

    # ALL-CAPS tokens
    for m in re.finditer(r"\b([A-Z]{2,15})\b", text):
        tok = m.group(1)
        if tok in GENERIC_CAPS:
            continue
        add("EMBEDDED_OBJECT", tok, "ALL_CAPS", "Matched ALL-CAPS token")

    # CamelCase / PascalCase product-like
    for m in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]+)+)\b", text):
        add("EMBEDDED_OBJECT", m.group(1), "CAMEL_CASE", "Matched CamelCase/PascalCase term")

    # Lightweight repeated noun-like 1–4 word phrases (appearance >= 2)
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", text)
    for n in (1, 2, 3, 4):
        counts: dict[str, int] = {}
        raw_map: dict[str, str] = {}
        for i in range(len(words) - n + 1):
            chunk = words[i : i + n]
            if any(w.lower() in STOPWORDS for w in chunk):
                continue
            if n == 1 and chunk[0].lower() in STOPWORDS:
                continue
            raw = " ".join(chunk)
            norm = normalize_candidate_text(raw)
            counts[norm] = counts.get(norm, 0) + 1
            raw_map[norm] = raw
        for norm, c in counts.items():
            if c >= 2 and 2 <= len(norm) <= 40:
                add(
                    "STORY_FRAME",
                    raw_map[norm],
                    "REPEATED_PHRASE",
                    f"Repeated phrase count={c}",
                )

    return out


def _apply_role_filter(
    candidates: list[ExtractedCandidate], account: Account | None
) -> list[ExtractedCandidate]:
    if account is None:
        # Unknown account: keep high-confidence naming / object primitives only
        keep_types = {"NEW_TERM", "REFRAME", "EMBEDDED_OBJECT"}
        filtered = [c for c in candidates if c.signal_type in keep_types]
        for c in filtered:
            c.initial_priority = "MEDIUM"
            c.source_role = None
        return filtered

    if _is_onchain_only(account):
        # Phase 3: do not create tech-hype candidates from ordinary on-chain posts
        return []

    blob = _role_blob(account)
    pri = _priority_for_account(account)
    role = account.primary_bucket or account.secondary_role

    out: list[ExtractedCandidate] = []

    is_namer = _has_role(
        blob,
        "NARRATIVE_NAMER",
        "NARRATIVE_FRAMER",
        "CATEGORY_FRAMER",
        "FRAMER",
        "SOURCE_FRAMER",
        "PRODUCT_FRAMER",
        "RESEARCH_FRAMER",
        "APPLIED_AI_FRAMER",
        "FOUNDER_FRAMER",
        "MEME_META_FRAMER",
    )
    is_object = _has_role(
        blob,
        "MODEL_ANOMALY_OBJECT_SCOUT",
        "OBJECT_EXTRACTOR",
        "OBJECT_NARRATIVE",
        "OPEN_MODEL_ANOMALY",
        "AI_MIND_ANOMALY",
        "AGENT_SCOUT",
        "BUILDER_SCOUT",
    )
    is_viral = _has_role(blob, "VIRAL_ANOMALY_AMPLIFIER", "AI_HYPE_SCOUT", "CRYPTO_ATTENTION")
    is_visual = _has_role(blob, "VISUAL_TECH_AMPLIFIER", "PROOF_AMPLIFIER", "BUILDER_PROOF")
    is_thesis = _has_role(blob, "TECH_TO_MEME_THESIS_BRIDGE", "TECH_CRYPTO_THESIS")

    for c in candidates:
        c.source_role = role
        c.initial_priority = pri
        st = c.signal_type

        if is_namer and st in {"NEW_TERM", "REFRAME"}:
            out.append(c)
            continue
        if is_object and st in {"EMBEDDED_OBJECT", "WEIRD_AI_EVENT"}:
            # Boost short concrete objects
            if len(c.normalized_text) <= 15:
                c.initial_priority = "HIGH" if pri != "LOW" else pri
            out.append(c)
            continue
        if is_viral:
            if st in {"NEW_TERM", "EMBEDDED_OBJECT", "STORY_FRAME"}:
                mapped = ExtractedCandidate(
                    signal_type="WEIRD_AI_EVENT" if st != "STORY_FRAME" else "STORY_FRAME",
                    candidate_text=c.candidate_text,
                    normalized_text=c.normalized_text,
                    extraction_method=c.extraction_method,
                    trigger_reason=c.trigger_reason + " (viral amplifier)",
                    initial_priority=pri,
                    source_role=role,
                )
                out.append(mapped)
            continue
        if is_visual and st in {"EMBEDDED_OBJECT", "NEW_TERM", "CAMEL_CASE"}:
            mapped = ExtractedCandidate(
                signal_type="PRODUCT_PROOF" if c.extraction_method == "CAMEL_CASE" else "VISUAL_PROOF",
                candidate_text=c.candidate_text,
                normalized_text=c.normalized_text,
                extraction_method=c.extraction_method,
                trigger_reason=c.trigger_reason + " (visual/proof amplifier)",
                initial_priority=pri,
                source_role=role,
            )
            out.append(mapped)
            continue
        if is_thesis and st in {"NEW_TERM", "REFRAME", "EMBEDDED_OBJECT", "STORY_FRAME"}:
            mapped = ExtractedCandidate(
                signal_type="TECH_TO_MEME_THESIS",
                candidate_text=c.candidate_text,
                normalized_text=c.normalized_text,
                extraction_method=c.extraction_method,
                trigger_reason=c.trigger_reason + " (tech-to-meme bridge)",
                initial_priority="HIGH",
                source_role=role,
            )
            out.append(mapped)
            continue

        # Default scout / educator / validator: keep naming + object primitives
        if st in {"NEW_TERM", "REFRAME", "EMBEDDED_OBJECT"}:
            if c.extraction_method in {
                "PATTERN_I_CALL_THIS",
                "PATTERN_CALLED",
                "PATTERN_BETTER_TERM",
                "TICKER",
                "QUOTED_PHRASE",
                "CAMEL_CASE",
                "ALL_CAPS",
                "PAREN_ACRONYM",
                "PATTERN_X_IS_THE_NEW_Y",
                "PATTERN_PREFER_X_TO_Y",
                "PATTERN_THE_NEW",
                "PATTERN_BASICALLY",
            }:
                out.append(c)

    # Deduplicate again after role remapping
    final: list[ExtractedCandidate] = []
    seen: set[tuple[str, str]] = set()
    for c in out:
        key = (c.signal_type, c.normalized_text)
        if key in seen:
            continue
        seen.add(key)
        final.append(c)
    return final


def extract_candidates(text: str, account: Account | None = None) -> list[ExtractedCandidate]:
    """Extract role-aware candidate signals from raw post text."""
    if not text or not text.strip():
        return []
    primitives = _extract_primitives(text)
    return _apply_role_filter(primitives, account)
