"""Replay one frozen case (no live network)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.replay import replay_case  # noqa: E402


def _parse_cutoff(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a frozen hype case")
    parser.add_argument("case_id")
    parser.add_argument("--cutoff", default=None, help="ISO timestamp cutoff")
    parser.add_argument("--checkpoint", default=None, help="e.g. +24H")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = replay_case(
        args.case_id,
        cutoff=_parse_cutoff(args.cutoff),
        checkpoint=args.checkpoint,
    )
    payload = [r.to_dict() for r in results]
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    for row in payload:
        print(
            f"{row['case']} {row['checkpoint']}: stage={row['suggested_formation_stage']} "
            f"dir={row['suggested_trend_direction']} pattern={row['suggested_formation_pattern']} "
            f"indep={row['independent_amplifiers']} platforms={row['active_platforms']} "
            f"evidence={row['visible_evidence_count']}"
        )
        if row.get("evaluation_comparison"):
            print(f"  eval: {row['evaluation_comparison']}")


if __name__ == "__main__":
    main()
