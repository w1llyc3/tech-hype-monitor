# Tech Hype Monitor — Phase 0–2

Local-first tech hype monitoring: collect Hacker News + Official RSS, track GitHub / Hugging Face entities with **historical metric observations**, browse raw events, and use Discovery search.

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

## Optional tokens

In `.env`:

```text
GITHUB_TOKEN=          # optional — improves GitHub API rate limits
HF_TOKEN=              # optional — Hugging Face Hub auth for higher limits
```

Public mode works without either token. Discovery results are **not** hype judgments.

## Pages

| Path | Purpose |
|------|---------|
| `/` | Dashboard (sources, tracked entities, recent activity) |
| `/discovery` | GitHub / HF Models / Spaces / Datasets search |
| `/entities/[id]` | Entity detail + per-metric history charts |
| `/events` | Raw event browser (Apply-triggered filters) |
| `/source-health` | Adapter health (+ GitHub rate-limit fields) |

## Discovery smoke

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\discovery_smoke.py "vibe coding"
```

## Tests

```powershell
cd apps\api
.\.venv\Scripts\python -m pytest -q
```

## Phase boundary

Phase 2 stops here. Do not add X scraping, DEX, LLM scoring, or Candidate Engine without approval.
