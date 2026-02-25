# ACPs Personalized Reading Recsys

## mTLS Development Setup (P7)

### 1) Generate local dev certificates

- Windows (PowerShell):

```powershell
./scripts/gen_dev_certs.ps1
```

- Linux/Mac:

```bash
bash ./scripts/gen_dev_certs.sh
```

Both scripts generate certificates under `certs/` by default:
- `ca.crt`, `ca.key`
- `reading_concierge_001.crt/.key`
- `reader_profile_agent_001.crt/.key`
- `book_content_agent_001.crt/.key`
- `rec_ranking_agent_001.crt/.key`
- plus `reader_profile`, `book_content`, `rec_ranking` cert pairs for existing example config files.

### 2) Enable mTLS startup

Set environment variables before launching any service:

```powershell
$env:AGENT_MTLS_ENABLED = "true"
$env:AGENT_MTLS_CERT_DIR = "<absolute_path_to>/certs"
```

Optional per-service config path overrides:
- `READING_CONCIERGE_MTLS_CONFIG_PATH`
- `READER_PROFILE_MTLS_CONFIG_PATH`
- `BOOK_CONTENT_MTLS_CONFIG_PATH`
- `REC_RANKING_MTLS_CONFIG_PATH`

### 3) Run services directly (uvicorn from module `__main__`)

```powershell
python -m reading_concierge.reading_concierge
python -m agents.reader_profile_agent.profile_agent
python -m agents.book_content_agent.book_content_agent
python -m agents.rec_ranking_agent.rec_ranking_agent
```

When `AGENT_MTLS_ENABLED=true`, services start with TLS and require client certs.

### 4) Verify HTTPS endpoint with dev CA

Example check (replace host/port as needed):

```bash
curl --cacert certs/ca.crt https://localhost:8100/demo/status
```

If mutual TLS client auth is required by the service, also provide client cert/key:

```bash
curl --cacert certs/ca.crt --cert certs/reader_profile.crt --key certs/reader_profile.key https://localhost:8211/acs
```
