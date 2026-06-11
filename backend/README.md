# Excel Workspace Backend

Independent FastAPI service for Excel asset versioning and row-level
provenance. It also owns authentication, document summaries, session-based
chat, LLM model preferences, and SQLite-backed runtime state.

## Structure

```text
app/api/          FastAPI routes and schemas
app/application/  business services and chat policies
app/domain/       framework-free dataclasses
app/ports/        repository, storage, workbook, LLM, and workflow protocols
app/adapters/     SQLite, filesystem, workbook reader, LLM, and LangGraph adapters
app/core/         config, auth helpers, IDs, errors, time, model catalog
```

SQLite internals are split under `app/adapters/repositories/sqlite/`:

- `schema.py`: ordered migrations
- `policies.py`: connection and retention defaults
- `maintenance.py`: checkpoint/cleanup support

## Run

macOS/Linux:

```bash
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

## Quality Checks

macOS/Linux:

```bash
./.venv/bin/python -m ruff check app tests
./.venv/bin/python -m pytest
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m ruff check app tests
.\.venv\Scripts\python -m pytest
```

## Storage

By default runtime files are written under:

```text
excel_workspace/storage/
```

Override with `EXCEL_STORAGE_ROOT` and `EXCEL_DATABASE_PATH`.

Long-running controls:

```text
LLM_ANSWER_MAX_ROWS=20000
MAINTENANCE_INTERVAL_SECONDS=300
MAINTENANCE_AUTH_SESSION_RETENTION_DAYS=30
MAINTENANCE_PASSWORD_RESET_TOKEN_RETENTION_DAYS=7
```

## LLM Providers

The backend can expose SiliconFlow and DeepSeek Official side by side. Stage
selectors use provider IDs:

```text
siliconflow
deepseek
```

SiliconFlow credentials:

```text
LLM_API_BASE_URL=https://api.siliconflow.cn/v1
LLM_API_KEY=...
```

DeepSeek Official credentials:

```text
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=...
```

Use `LLM_SUMMARY_PROVIDER`, `LLM_ROUTER_PROVIDER`, and `LLM_ANSWER_PROVIDER`
to choose the default provider for each stage. The UI can still override the
provider and model per request.

Current default stage policy:

```text
summary: deepseek / deepseek-v4-pro
router:  siliconflow / Qwen/Qwen3.6-35B-A3B
answer:  deepseek / deepseek-v4-pro
```
