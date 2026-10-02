# Tech Hype Monitor — Technology Hype & Trend Intelligence

Local-first product: detect emerging tech hype, explain formation (stage / direction / pattern), confirm with cross-platform evidence and post-T0 derivatives, and export research bundles for manual ChatGPT Pro review.

Hard boundary: **no DEX, tokens, wallet tracking, OpenAI API, or automated X scraping.**

## Required paid accounts

- **Cursor Pro** — product development
- **ChatGPT Pro** — manual research / verification (never called via API)

No other paid account is required for the core product.

Clarifications:

- Public GitHub API works without a token (lower rate limits); an optional personal token is not a paid service
- Hugging Face public data works without a paid plan
- X core path is **manual / semi-manual ingest** — missing X automation is never negative hype evidence
- No OpenAI API key
- No paid SaaS dependency for core monitoring

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

## Historical replay

Frozen local fixtures only — normal replay never hits today's internet.

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\replay_case.py synth-naming-first
.\.venv\Scripts\python ..\..\scripts\replay_batch.py
```

UI: `/replay` registry and `/replay/[case_id]` checkpoint view.

Real historical cases stay `NEEDS_RESEARCH` until verified timestamps + source URLs are frozen locally.

## Research bundle (ChatGPT Pro handoff)

On `/hype/[id]`:

1. **Export research bundle** → writes `exports/hype_<id>_<slug>_research_bundle.md`
2. Copies a ChatGPT research prompt (no API call)

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
| `/hype-radar` | Daily Hype Radar (grouped; no opaque score) |
| `/hype/[id]` | Stage / direction / pattern + trend timeline + export |
| `/candidate-inbox` | Review OPEN signals |
| `/replay` | Historical replay registry |
| `/replay/[case_id]` | Checkpoint reconstruction |
| `/x-ingest` | Manual X post ingest |
| `/accounts` | Account Universe browser |
| `/discovery` | GitHub / HF search |
| `/entities/[id]` | Entity metric history |
| `/events` | Raw events (+ Create Candidate) |
| `/source-health` | Adapter health (X = manual coverage) |

## Smoke scripts

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\discovery_smoke.py "vibe coding"
.\.venv\Scripts\python ..\..\scripts\candidate_smoke.py
.\.venv\Scripts\python ..\..\scripts\replay_batch.py
```

## Tests

```powershell
cd apps\api
.\.venv\Scripts\python -m pytest -q
```

## Product boundary

Ends at Technology Hype & Trend Intelligence. Do not add DEX / token inventory, OpenAI/LLM APIs, or automated X scraping.
