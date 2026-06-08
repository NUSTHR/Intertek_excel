# Excel Workspace

Excel Workspace is an independent Excel asset and version management system.
It is intentionally isolated from the existing `D_ass` frontend and
`ragflow_integration_service` backend so it can later be moved to a separate
repository or replace the legacy workflow.

## Applications

- `backend/`: FastAPI service on port `8090`.
- `frontend/`: Vue/Vite app on port `5174`.
- `contracts/`: API contract notes and future OpenAPI exports.
- `docs/`: architecture and pipeline documentation.
- `storage/`: local runtime artifacts, ignored by Git.

## Backend

macOS/Linux:

```bash
cd excel_workspace/backend
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

Windows PowerShell:

```powershell
Set-Location ".\excel_workspace\backend"
Copy-Item .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

## Frontend

macOS/Linux:

```bash
cd excel_workspace/frontend
cp .env.example .env
npm install
npm run dev
```

Windows PowerShell:

```powershell
Set-Location ".\excel_workspace\frontend"
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://127.0.0.1:5174`.

## Boundary Rules

- Do not import code from `D_ass`.
- Do not import code from `ragflow_integration_service`.
- Do not register Excel assets in RAGFlow.
- Treat `excel_workspace/` as a standalone product directory.

## Current Product

Excel Workspace is no longer only an Excel asset viewer. The current project is
a runnable Excel knowledge-base Q&A MVP with deterministic preprocessing and
row-level evidence.

Current scope:

- Upload Excel files and preserve version history.
- Parse `.xlsx` and legacy `.xls` deterministically.
- Write raw CSV artifacts, row mappings, and workbook profiles.
- Generate persisted document summaries with SiliconFlow models.
- Run session-based multi-turn chat with document routing and answer synthesis.
- Verify cited row IDs in the backend and let the frontend jump to source rows.
- Delete documents and their related derived artifacts with explicit confirmation.

This module must remain standalone, but chat and LLM behavior are now part of
the actual product and should be treated as first-class functionality.

## Architecture

The backend keeps a ports-and-adapters shape:

```text
api/          HTTP routes, request DTOs, response DTOs, error mapping
domain/       pure dataclasses, no framework dependencies
application/  use cases: upload, summary, chat, deletion, preview, lookup
ports/        repository, storage, workbook-reader, llm-client protocols
adapters/     SQLite, filesystem, workbook readers, SiliconFlow, fake LLM
core/         config, IDs, time, expected application errors
```

Application services should still depend on `ports/`, not concrete adapters.

## Current Features

- Upload and replacement confirmation:
  - duplicate display names return `409` until explicitly confirmed
  - replacement creates a new version and activates it only after success
- Deterministic parsing:
  - sheet CSV export
  - stable row IDs like `S001_R1`
  - row-to-original provenance mapping
  - workbook profile JSON
- File/version browsing:
  - file list
  - version list
  - sheet preview
  - row lookup by `row_id`
- Document summary:
  - persisted in SQLite
  - generated from workbook profile only
- Chat:
  - session creation
  - split `route` and `answer` APIs
  - multi-turn chat history in the UI
  - row-level citations and source trace
- LLM model selection:
  - separate selectable models for summary, router, and answer stages
- File deletion:
  - hard delete with explicit confirmation
  - removes related storage artifacts and database records

## Supported Models

The UI and backend currently support these SiliconFlow model IDs:

- `deepseek-ai/DeepSeek-V4-Pro`
- `Pro/deepseek-ai/DeepSeek-V3.2`
- `Qwen/Qwen3.6-27B`
- `Qwen/Qwen3.6-35B-A3B`
- `inclusionAI/Ling-flash-2.0`

Default stage models:

- summary: DeepSeek Official `deepseek-v4-pro`
- router: SiliconFlow `Qwen/Qwen3.6-35B-A3B`
- answer: DeepSeek Official `deepseek-v4-pro`

The backend applies a conservative compatibility strategy for "disable
thinking": it sends `enable_thinking=false` only for model families whose
support is known, and otherwise avoids sending unsupported parameters.

## Public APIs

Core endpoints:

```text
GET    /health

POST   /api/excel/files
GET    /api/excel/files
DELETE /api/excel/files/{file_id}
GET    /api/excel/files/{file_id}/versions
GET    /api/excel/files/{file_id}/active

GET    /api/excel/versions/{version_id}/sheets
GET    /api/excel/versions/{version_id}/profile
GET    /api/excel/versions/{version_id}/artifacts
POST   /api/excel/versions/{version_id}/summary/generate
GET    /api/excel/versions/{version_id}/summary

GET    /api/excel/sheets/{sheet_id}/preview
GET    /api/excel/sheets/{sheet_id}/rows
GET    /api/excel/sheets/{sheet_id}/rows/{row_id}

GET    /api/excel/llm/options
POST   /api/excel/chat
POST   /api/excel/chat/sessions
GET    /api/excel/chat/sessions/{session_id}
POST   /api/excel/chat/sessions/{session_id}/messages
POST   /api/excel/chat/sessions/{session_id}/route
POST   /api/excel/chat/sessions/{session_id}/answer
```

## Storage And Data Rules

Runtime data lives under `excel_workspace/storage/` unless overridden by env
vars.

Important invariants:

- `file_id` stays stable across replacements
- `version_id` changes on every new upload version
- `sheet_id` is per-version/per-sheet
- `row_id` is deterministic within each sheet
- failed versions must not replace the active version

## Current Risks

- Chat scope:
  - router still considers all active summaries in the knowledge base
  - there is no explicit per-chat file scope yet
- Context size:
  - answer stage still sends full selected-document rows to the model
  - this can cause high latency or provider failures on large contexts
- Confirmed runtime finding:
  - `Pro/deepseek-ai/DeepSeek-V3.2` can fail with provider `400` if answer-stage
    prompt tokens exceed that model's limit
- Citation semantics:
  - backend verifies cited row IDs exist
  - it does not yet prove the row semantically supports the exact claim
- UI layout:
  - citation and source panels can still crowd the chat area in long sessions

## Current Priorities

- Add explicit chat file scope
- Add answer-stage context/token guardrails
- Improve right-column chat layout
- Improve timing and observability around failed chat stages

## Verification Status

Latest recorded local checks:

```text
pytest: 22 passed
npm run build: passed
```

## Operational Notes

- `excel_workspace/storage/` is ignored by Git and may contain user data.
- Do not delete storage during normal development unless explicitly resetting
  local state.
- Keep frontend TypeScript types and backend schemas synchronized.
- Keep changes inside `excel_workspace/` unless a task explicitly requires
  cross-module integration.
- For a more detailed business and architecture handoff, read
  `project_inspection.md`.
