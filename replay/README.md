# Historical Replay

Frozen local evidence only. Normal replay **must not** query today's internet.

## Layout

```text
replay/cases/           # case manifests (JSON)
replay/fixtures/        # optional extra frozen bundles
replay/README.md
```

## Case statuses

- `READY` — verified frozen events with timestamps + URLs (or explicit synthetic fixtures for tests)
- `PARTIAL` — some events frozen, coverage gaps => `INCOMPLETE_EVIDENCE`
- `NEEDS_RESEARCH` — registry placeholder; research manually with ChatGPT Pro

## CLI

```powershell
cd apps\api
.\.venv\Scripts\python ..\..\scripts\replay_case.py vibe-coding
.\.venv\Scripts\python ..\..\scripts\replay_case.py vibe-coding --cutoff 2025-02-06T12:00:00Z
.\.venv\Scripts\python ..\..\scripts\replay_batch.py
```

## Evaluation block

`evaluation.reference_pattern` is **evaluation-only**. The detection/trend engine loads a stripped view without this block. Comparison happens only after inference.

## Workflow for real cases

1. Keep registry metadata (`NEEDS_RESEARCH`)
2. Research with ChatGPT Pro (manual)
3. Save verified events into the case JSON
4. Mark `READY` only with timestamp + source URL
