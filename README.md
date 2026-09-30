# Tech Hype Monitor — Phase 0–3

Local-first tech hype monitoring: collect Hacker News + Official RSS, track GitHub / Hugging Face entities, import a monitored Account Universe, manually ingest X posts, extract deterministic candidate signals, and confirm them on a Hype Radar.

No paid APIs required. Optional tokens improve rate limits only.

## Requirements

- Python 3.12+
- Node.js 20+
- Windows: PowerShell 5.1+ (or `scripts/dev.sh` on macOS/Linux)

## Quick start

```powershell
# From repo root
Copy-Item .env.example .env   # if needed
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

```bash
make dev
```

- API: http://localhost:8000
- Web: http://localhost:3000

## Account Universe

CSV lives at `data/account_universe_v1.csv`.

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\import_accounts.py ..\..\data\account_universe_v1.csv
```

Upsert key: `(platform, handle)`. Re-import updates rows; does not duplicate.

## Manual X ingest

1. Open http://localhost:3000/x-ingest
2. Paste URL, handle, exact post text (optional metrics)
3. **Save & Analyze** → raw event + account_event denominator + candidate signals
4. Review at `/candidate-inbox` → Accept / Attach / Reject / Merge
5. Accepted signals appear on `/hype-radar` and `/hype/[id]`

API:

```http
POST /api/x/manual-ingest
```

Every monitored-account post creates an `account_events` row. If extraction finds nothing:

```text
trigger_type = NO_CANDIDATE
candidate_state = CLOSED
```

## Optional tokens

In `.env`:

```text
GITHUB_TOKEN=          # optional — improves GitHub API rate limits
HF_TOKEN=              # optional — Hugging Face Hub auth for higher limits
```

## Pages

| Path | Purpose |
|------|---------|
| `/` | Dashboard |
| `/hype-radar` | Active hype candidates (no opaque score) |
| `/hype/[id]` | Candidate evidence trail |
| `/candidate-inbox` | Review OPEN signals |
| `/x-ingest` | Manual X post ingest |
| `/accounts` | Account Universe browser |
| `/discovery` | GitHub / HF search |
| `/entities/[id]` | Entity metric history |
| `/events` | Raw events (+ Create Candidate) |
| `/source-health` | Adapter health |

## Smoke scripts

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\discovery_smoke.py "vibe coding"
.\.venv\Scripts\python ..\..\scripts\candidate_smoke.py
```

## Tests

```powershell
cd apps\api
.\.venv\Scripts\python -m pytest -q
```

## Phase boundary

Phase 3 stops here. Do not add DEX / token inventory, OpenAI/LLM APIs, or automated X scraping without approval.
