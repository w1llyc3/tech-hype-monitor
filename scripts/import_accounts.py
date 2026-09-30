"""Import Account Universe CSV into the accounts table.

Expected columns (extras ignored):
platform,handle,display_name,primary_bucket,secondary_role,universe_tier,
monitor_priority,preferred_trigger,economic_exposure,conflict_risk,
reverse_test_status,tech_to_crypto_relevance,enabled
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.timeutil import utcnow  # noqa: E402
from app.db.models import Account  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from sqlalchemy import select  # noqa: E402

FIELDS = [
    "platform",
    "handle",
    "display_name",
    "primary_bucket",
    "secondary_role",
    "universe_tier",
    "monitor_priority",
    "preferred_trigger",
    "economic_exposure",
    "conflict_risk",
    "reverse_test_status",
    "tech_to_crypto_relevance",
    "enabled",
]


def _bool(value: str | None, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _normalize_handle(handle: str) -> str:
    h = (handle or "").strip()
    if h.startswith("@"):
        h = h[1:]
    return h.lower()


def import_accounts(csv_path: Path) -> tuple[int, int]:
    init_db()
    inserted = updated = 0
    now = utcnow()
    with csv_path.open(encoding="utf-8-sig", newline="") as f, SessionLocal() as db:
        reader = csv.DictReader(f)
        for row in reader:
            platform = (row.get("platform") or "").strip().lower()
            handle = _normalize_handle(row.get("handle") or "")
            if not platform or not handle:
                continue
            # Upsert keyed by (platform, handle); also match legacy @handle rows
            existing = db.scalar(
                select(Account).where(Account.platform == platform, Account.handle == handle)
            )
            if not existing:
                existing = db.scalar(
                    select(Account).where(
                        Account.platform == platform, Account.handle == f"@{handle}"
                    )
                )
                if existing:
                    existing.handle = handle
            payload = {k: (row.get(k) or None) for k in FIELDS if k not in {"platform", "handle", "enabled"}}
            enabled = _bool(row.get("enabled"), True)
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
                existing.enabled = enabled
                existing.updated_at = now
                updated += 1
            else:
                db.add(
                    Account(
                        platform=platform,
                        handle=handle,
                        enabled=enabled,
                        created_at=now,
                        updated_at=now,
                        **payload,
                    )
                )
                inserted += 1
        db.commit()
    return inserted, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Import accounts CSV")
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    if not args.csv_path.exists():
        raise SystemExit(f"File not found: {args.csv_path}")
    inserted, updated = import_accounts(args.csv_path)
    print(f"Import complete. inserted={inserted} updated={updated}")


if __name__ == "__main__":
    main()
