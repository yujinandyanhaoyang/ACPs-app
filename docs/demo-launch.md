# Demo System Launch Guide

This document explains how to launch and verify the ACPs personalized reading recommendation demo.

## 1) Prerequisites

- OS: Windows (PowerShell examples below)
- Python: 3.13 (project virtual environment already configured)
- Dependencies installed from `requirements.txt`

## 2) Open project root

```powershell
Set-Location "F:\Pythonfiles\work_files\work_project\school\ACPs-Demo-Project\ACPs-personalized-reading-recsys"
```

## 3) Activate virtual environment

```powershell
.\venv\Scripts\Activate.ps1
```

## 4) Start demo service (HTTP, no mTLS)

```powershell
$env:AGENT_MTLS_ENABLED = "false"
python -m reading_concierge.reading_concierge
```

Expected startup log:
- `Uvicorn running on http://0.0.0.0:8100`

> Keep this terminal running.

## 5) Verify service health

In a new PowerShell terminal:

```powershell
Set-Location "F:\Pythonfiles\work_files\work_project\school\ACPs-Demo-Project\ACPs-personalized-reading-recsys"
.\venv\Scripts\Activate.ps1
curl.exe -sS http://127.0.0.1:8100/demo/status
```

Expected response contains:
- `"service":"reading_concierge"`
- `"demo_page_available":true`

## 6) Open demo page in browser

- URL: `http://127.0.0.1:8100/demo`

## 7) Send a live recommendation request

Use PowerShell JSON (recommended on Windows):

```powershell
$payload = @{
  user_id = "demo_user_001"
  query = "Recommend thoughtful science fiction and history books"
  constraints = @{ scenario = "warm"; top_k = 5 }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Uri "http://127.0.0.1:8100/user_api" -Method Post -ContentType "application/json" -Body $payload | ConvertTo-Json -Depth 8
```

Expected behavior:
- `/user_api` requires non-empty `user_id` and `query`.
- Profile/history/reviews are loaded from local persistent store.

### Optional debug payload injection (nonproduction)

Manual profile/history injection is only supported via `/user_api_debug`.

```powershell
$debugPayload = @{
  query = "Recommend thoughtful science fiction and history books"
  user_profile = @{ preferred_language = "en" }
  history = @(
    @{ title = "Dune"; genres = @("science_fiction"); rating = 5; language = "en" },
    @{ title = "Sapiens"; genres = @("history", "nonfiction"); rating = 4; language = "en" }
  )
  reviews = @(
    @{ rating = 5; text = "I like idea-driven books with social depth" }
  )
  constraints = @{ scenario = "warm"; top_k = 5; debug_payload_override = $true }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Uri "http://127.0.0.1:8100/user_api_debug" -Method Post -ContentType "application/json" -Body $debugPayload | ConvertTo-Json -Depth 8
```

Check key fields in response:
- `state` (expected: `completed` or `needs_input`)
- `recommendations` (non-empty list for successful recommendation)
- `metric_snapshot` (`avg_diversity`, `avg_novelty`)

## 8) Run benchmark performance evaluation

```powershell
python .\scripts\phase4_benchmark_compare.py `
  --cases .\scripts\phase4_cases.json `
  --out .\scripts\phase4_benchmark_report.json `
  --summary-out .\scripts\phase4_benchmark_summary.json `
  --md-out .\scripts\phase4_benchmark_report.md `
  --pretty
```

Output files:
- `scripts/phase4_benchmark_report.json`
- `scripts/phase4_benchmark_summary.json`
- `scripts/phase4_benchmark_report.md`

## 9) Optional: launch with mTLS

If you need HTTPS/mTLS demo startup:

1. Generate certs:
```powershell
.\scripts\gen_dev_certs.ps1
```

2. Start service with mTLS:
```powershell
$env:AGENT_MTLS_ENABLED = "true"
$env:AGENT_MTLS_CERT_DIR = (Resolve-Path .\certs).Path
python -m reading_concierge.reading_concierge
```

3. Verify HTTPS:
```powershell
curl.exe -v --ssl-no-revoke --cacert .\certs\ca.crt https://localhost:8100/demo/status
```

## 10) Stop demo service

In the service terminal, press:
- `Ctrl + C`

---

## Troubleshooting

- Port in use (`[WinError 10048]`):
  - Stop the old process using port `8100`, then restart.
- Empty recommendations:
  - Try broader query text and verify the user has persisted events/profile context.
- HTTP 422 on `/user_api`:
  - Ensure both `user_id` and `query` are non-empty.
  - Use `/user_api_debug` only for explicit nonproduction payload injection.
- Slow first run:
  - Initial embedding/model load can take longer than subsequent calls.
