# Tech Hype Monitor — Phase 0 + Phase 1

Local-first tech hype monitoring: collect Hacker News + Official RSS into SQLite, browse raw events, and inspect source health. No paid APIs. No X/DEX/LLM yet.

## Requirements

- Python 3.12+
- Node.js 20+
- Windows: PowerShell 5.1+ (or use `scripts/dev.sh` on macOS/Linux)

## Quick start

```powershell
# From repo root
Copy-Item .env.example .env   # if needed
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

Or:

```bash
make dev
# equivalent: bash scripts/dev.sh
```

This will:

1. Create `apps/api/.venv` and install Python deps (first run)
2. Run Alembic migrations → `data/tech_hype.db` (WAL)
3. Seed sources (HN + Official RSS enabled; GitHub/HF stubs disabled)
4. Start API at http://localhost:8000
5. Install web deps if needed and start Next.js at http://localhost:3000

## Manual setup

```powershell
cd apps\api
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m app.db.seed
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
cd apps\web
npm install
npm run dev
```

## Tests

```powershell
cd apps\api
.\.venv\Scripts\python -m pytest -q
```

## Import accounts (CSV)

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\import_accounts.py path\to\accounts.csv
```

Expected CSV columns (extra columns ignored):

`platform,handle,display_name,primary_bucket,secondary_role,universe_tier,monitor_priority,preferred_trigger,economic_exposure,conflict_risk,reverse_test_status,tech_to_crypto_relevance,enabled`

## Pages

| Path | Purpose |
|------|---------|
| `/` | Dashboard shell |
| `/events` | Raw event browser |
| `/source-health` | Adapter health |

## API

- `GET /health`
- `GET /api/sources`
- `GET /api/sources/health`
- `GET /api/events`
- `GET /api/events/{id}`
- `GET /api/accounts`
- `GET /api/hype-candidates`
- `POST /api/sources/{id}/poll`
- `POST /api/system/poll-all`

## Phase boundary

Phase 1 stops here. Candidate engine, X automation, DEX, embeddings, and cloud deploy are Phase 2+.
