"""Replay all READY cases from replay/cases (no live network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.replay import list_cases, replay_case  # noqa: E402


def main() -> None:
    rows = list_cases()
    summary = []
    for meta in rows:
        if (meta.get("fixture_status") or "").upper() not in {"READY", "PARTIAL"}:
            summary.append({**meta, "replay_status": "SKIPPED_NEEDS_RESEARCH"})
            continue
        try:
            results = replay_case(meta["case_id"])
            last = results[-1].to_dict() if results else {}
            earliest = next(
                (r for r in results if r.suggested_formation_stage != "SEED"),
                results[0] if results else None,
            )
            summary.append(
                {
                    **meta,
                    "replay_status": "OK",
                    "earliest_non_seed_stage": earliest.suggested_formation_stage if earliest else None,
                    "final_stage": last.get("suggested_formation_stage"),
                    "suggested_pattern": last.get("suggested_formation_pattern"),
                    "evaluation_comparison": last.get("evaluation_comparison"),
                }
            )
            print(
                f"{meta['case_id']}: pattern={last.get('suggested_formation_pattern')} "
                f"stage={last.get('suggested_formation_stage')} "
                f"eval={last.get('evaluation_comparison')}"
            )
        except Exception as exc:  # noqa: BLE001
            summary.append({**meta, "replay_status": f"ERROR: {exc}"})
            print(f"{meta['case_id']}: ERROR {exc}")
    print(json.dumps({"count": len(summary), "results": summary}, indent=2))


if __name__ == "__main__":
    main()
