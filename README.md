# Excel Workspace

Excel Workspace is a standalone Excel and PDF knowledge-base and Q&A product
area. It combines authenticated workbook management, deterministic Excel
preprocessing, PDF knowledge ingestion, persisted document summaries,
multi-turn chat, model routing, backend-verified row-level citations, and
PDF-grounded citations.

This module intentionally stays isolated from the legacy `D_ass` frontend and
`ragflow_integration_service` backend. It can keep evolving inside this
repository or be split into its own repository later without bringing legacy
RAGFlow code with it.

## What This Project Does

Excel Workspace is not just an Excel preview page. The current implementation
is a runnable MVP for enterprise Excel Q&A, with an independent PDF knowledge
module on the `add_pdf` branch:

1. Users authenticate into a workspace.
2. Admin users upload Excel workbooks into a shared library.
3. The backend parses each workbook deterministically.
4. The backend preserves original files and writes derived raw artifacts.
5. The backend assigns stable sheet codes and row IDs.
6. The backend stores workbook metadata, versions, sheets, row mappings, chat
   sessions, auth state, summaries, and LLM preferences in SQLite.
7. A model can generate a document summary from the deterministic workbook
   profile.
8. During chat, a router model chooses relevant workbook versions from active
   document summaries.
9. The answer model receives selected workbook rows and returns answer blocks
   with row IDs.
10. The backend verifies cited row IDs before returning citations to the
    frontend.
11. The frontend shows the answer, source rows, and row highlights.
12. Admin users can upload PDF folders into a separate PDF knowledge area.
13. The backend preserves PDF folder hierarchy, creates upload tasks, parses
    supported files through the configured PDF parser, stores searchable
    chunks, and exposes PDF citations for chat answers.

The most important product rule is that original workbooks, PDF source files,
backend row provenance, and PDF chunk provenance remain the source of truth.
LLM output is used for description, routing, and natural-language synthesis,
not for inventing row identity or PDF evidence.

## Applications

```text
backend/    FastAPI service, default port 8090
frontend/   Vue 3 + Vite app, default port 5174
contracts/  API contract notes and future OpenAPI exports
docs/       architecture and processing documentation
storage/    runtime SQLite database and generated artifacts, ignored by Git
```

Default local URLs:

```text
Frontend:      http://127.0.0.1:5174
Backend:       http://127.0.0.1:8090
Health check:  http://127.0.0.1:8090/health
Readiness:     http://127.0.0.1:8090/ready
```

The frontend dev server proxies `/api` and `/health` to the backend on
`127.0.0.1:8090`.

## Current Technical Stack

Backend:

- Python `3.11+`; the current local virtual environment has been verified with
  Python `3.12`.
- FastAPI.
- Uvicorn.
- SQLite with ordered migrations.
- `openpyxl` for `.xlsx`, `.xlsm`, `.xltx`, and `.xltm`.
- `xlrd` for legacy `.xls`.
- `pydantic-settings`.
- Configurable PDF parser backend: local fake parser for tests/development or
  MinerU command-line parsing for PDF knowledge ingestion.
- LangGraph for the route -> answer workflow adapter.
- `pytest` and `ruff` for checks.

Frontend:

- Vue 3.
- TypeScript.
- Vite 7.
- Native CSS.
- Browser `localStorage` for small local UI preferences such as pinned files.

Runtime services:

- SQLite database under `storage/` by default.
- Filesystem artifact storage under `storage/` by default.
- Optional external LLM providers for summary, router, and answer stages.
- Optional MinerU runtime for production-like PDF parsing.

## Product Boundary Rules

- Do not import code from `D_ass`.
- Do not import code from `ragflow_integration_service`.
- Do not register Excel assets in RAGFlow.
- Keep backend contracts, frontend API clients, and frontend TypeScript types
  synchronized inside this project.
- Treat `storage/` as runtime data; it may contain user uploads and should not
  be casually deleted.
- Never commit real LLM API keys or production credentials.

## Current Features

Authentication:

- Register.
- Login.
- Cookie and bearer-token authentication support.
- Logout.
- Password reset endpoints.
- Automatic admin user initialization from backend settings.
- Admin/member role distinction.
- Login rate limiting.
- CSRF protection for cookie-authenticated unsafe methods.

Workspace and file management:

- Admin upload of Excel workbooks.
- Durable upload task flow for long-running parsing.
- Duplicate display-name check.
- Replacement confirmation.
- Versioned replacement under the same `file_id`.
- Failed replacements do not activate over the previous ready version.
- File list and file lookup.
- File rename.
- File visibility toggles for member access.
- File deletion with explicit confirmation.
- Active-version lookup.
- Version list.
- Manual version activation.
- Local file pinning in the frontend.

Deterministic Excel processing:

- Supported extensions are configurable and default to
  `.xls,.xlsx,.xlsm,.xltx,.xltm`.
- Original workbook artifact is preserved.
- Each sheet receives a stable sheet code such as `S001`.
- Each exported row receives a readable row ID such as `S001_R25`.
- Raw CSV is written per sheet.
- Row mappings preserve original row numbers and raw CSV row numbers.
- Workbook profile JSON is generated without model calls.
- The active version is switched only after parsing succeeds.

Sheet inspection:

- Sheet list by version.
- Paged sheet preview.
- Paged row listing.
- Workbook-level search across all sheets in a version.
- Sheet-level search.
- Bounded search limits.
- Matched-column reporting.
- Row lookup by `sheet_id + row_id`.
- Frontend row highlighting and citation jump-through.
- Preview CSV export from the frontend.
- Schema/profile inspection tab.

Document summaries:

- Summary generation from workbook profile only.
- Summary persistence in SQLite.
- Per-request provider/model override for generation.
- Manual summary editing after generation.
- Per-sheet summary fields.
- Routing terms and exact identifiers for later chat routing.

Chat:

- Direct one-shot chat endpoint.
- Session-based chat endpoint.
- Split route and answer endpoints.
- Chat request cancellation.
- Chat session create/list/get/rename/pin/delete.
- Chat turn listing.
- Router stage sees question, recent chat turns, attached documents, and
  candidate document summaries.
- Router stage does not receive Excel rows.
- Answer stage receives selected workbook rows and recent chat context.
- Attached document reuse is tracked per session.
- Backend verifies cited row IDs.
- Responses include answer blocks, citations, warnings, follow-up suggestions,
  selected documents, newly attached documents, and attached documents.

LLM preferences:

- Authenticated users can read available provider/model options.
- Admin users can save workspace model preferences.
- Summary, router, and answer stages have independent provider/model choices.
- Deep-thinking controls are exposed only where supported.

Frontend workspace:

- Authenticated shell.
- Admin-aware and member-aware navigation.
- Admin file-management workflow.
- Member chat-first workflow with shared file inspection.
- Role-specific default avatars.
- Floating non-blocking operation feedback.
- File search.
- Sheet search in preview and chat workspaces.
- Summary viewing and editing.
- LLM model preference controls.
- Chat session rail with pin, rename, and delete.
- Resizable chat and table surfaces.

PDF knowledge module:

- Independent PDF workspace under the main app's `PDF AI` navigation item.
- Admin folder upload flow using browser folder selection.
- Folder hierarchy preservation for supported PDF knowledge files.
- PDF upload tasks with stage diagnostics: queued, claimed, parsing, indexing,
  ready, and failed.
- Parser backend diagnostics, error codes, retry counters, and stale-task
  failure marking for PDF upload tasks.
- Configurable parser backend with `fake` for tests/development and `mineru`
  for real PDF parsing.
- PDF file list, detail, preview blocks, schema items, tags, and searchable
  chunks persisted in SQLite.
- PDF retrieval endpoint over indexed chunks.
- PDF chat endpoint that answers from retrieved chunks and returns PDF
  citations.
- PDF model settings for summary, router, and chat engines.
- Frontend PDF management and PDF chat surfaces styled to coordinate with the
  Excel workspace.

## Architecture

The backend uses a ports-and-adapters shape:

```text
backend/app/
  api/          FastAPI routes, schemas, dependencies, exception handlers
  application/  auth, upload, summary, preview, search, chat, PDF knowledge, preferences
  domain/       framework-free dataclasses and enums
  ports/        repository, storage, workbook reader, PDF parser, LLM, chat workflow protocols
  adapters/     SQLite, filesystem, workbook reader, PDF parser, LLM, LangGraph workflow
  core/         config, IDs, auth helpers, logging, model catalog, errors, time
```

Important backend ownership:

- `app/main.py` creates the FastAPI app and registers routes/middleware.
- `app/core/config.py` owns environment settings and production safety checks.
- `app/core/llm_catalog.py` owns supported provider/model catalogs.
- `app/api/dependencies.py` wires concrete adapters into application services.
- `app/adapters/repositories/sqlite/schema.py` owns ordered migrations.
- `app/adapters/repositories/sqlite_repository.py` owns SQLite persistence.
- `app/adapters/repositories/sqlite/policies.py` owns SQLite connection and
  retention defaults.
- `app/adapters/repositories/sqlite/maintenance.py` owns periodic cleanup and
  optimization.
- `app/application/excel_assets/search.py` owns search normalization and
  match policy.
- `app/application/pdf_knowledge/` owns PDF upload tasks, parsing orchestration,
  indexing, retrieval, and PDF-grounded chat.
- `app/adapters/pdf/` owns the fake parser and MinerU parser adapter.
- `app/application/chat/policy.py` owns chat runtime guardrails.
- `app/adapters/dialogue/langgraph_chat_workflow.py` owns the production
  route -> answer workflow orchestration.

The frontend owns its own API clients, types, components, and workspace state:

```text
frontend/src/
  api/          typed HTTP clients
  app/          workspace shell and shared workspace utilities
  components/   reusable UI panels and controls
  features/     file-management and pdf-knowledge feature components/composables
  styles/       CSS split by surface
  types/        frontend API/domain types
```

## Data Model And Runtime Storage

Default runtime data lives under:

```text
storage/excel-workspace.sqlite3
storage/files/
storage/pdf-knowledge/files/
storage/pdf-knowledge/upload-tasks/
storage/logs/
```

The default database path and storage root can be overridden. Leave them empty
for the project-relative defaults above. If a relative value is supplied, it is
resolved from the project root, not from the shell's current working directory:

```text
EXCEL_DATABASE_PATH=runtime/excel-workspace.sqlite3
EXCEL_STORAGE_ROOT=runtime/storage
```

Absolute values are still accepted for deliberate external volumes or server
mounts, but the application does not require absolute paths to run. Persisted
Excel artifact references are stored relative to `EXCEL_STORAGE_ROOT`
(`files/...`, `upload-tasks/...`) and resolved through the storage adapter at
runtime. This keeps uploads, previews, row lookups, search, and profile loading
portable when the project directory is moved.

Schema migration `13`, `normalize_storage_artifact_references`, converts older
Mac/Linux or Windows-style absolute artifact rows into storage-relative
references during backend startup.

Key SQLite areas:

- schema migrations
- Excel files
- Excel file versions
- Excel sheets
- Excel artifacts
- Excel row mappings
- document summaries
- document sheet summaries
- chat sessions
- chat session documents
- chat turns
- upload tasks
- PDF files
- PDF upload tasks
- PDF document summaries
- PDF preview blocks
- PDF schema items
- PDF document tags
- PDF document chunks
- PDF model settings
- shared chat cancellation state
- LLM preferences
- user accounts
- auth sessions
- password reset tokens

Important invariants:

- `file_id` stays stable across replacement uploads.
- `version_id` changes with every uploaded version.
- `sheet_id` is tied to a workbook version and sheet.
- `row_id` is deterministic within a sheet.
- Failed version processing must not change the active version.
- Citations are accepted only after backend row-ID verification.
- PDF folder hierarchy is preserved through `parent_id` relationships.
- PDF upload tasks use stage diagnostics and must not remain stuck in
  processing after stale-task recovery.
- PDF chat answers must be grounded in indexed chunks visible to the current
  user role.
- Admin users manage file mutation and model preferences.
- Member users can authenticate, inspect visible shared files, and manage their
  own chat sessions.

## LLM Providers And Models

The backend currently supports these provider IDs:

- `siliconflow`
- `deepseek`
- `volcengine_ark`

SiliconFlow models:

- `inclusionAI/Ling-flash-2.0`
- `deepseek-ai/DeepSeek-V4-Pro`
- `Pro/deepseek-ai/DeepSeek-V3.2`
- `Qwen/Qwen3.6-27B`
- `Qwen/Qwen3.6-35B-A3B`

DeepSeek Official models:

- `deepseek-v4-pro`
- `deepseek-v4-flash`

Volcengine Ark models:

- `doubao-seed-2-0-pro-260215`
- `doubao-seed-2-0-lite-260428`
- `doubao-seed-2-0-mini-260428`
- `doubao-seed-2-0-lite-260215`
- `doubao-seed-1-8-251228`
- `deepseek-v4-pro-260425`
- `deepseek-v4-flash-260425`
- `deepseek-v3.2`

Default stage policy:

```text
summary: deepseek / deepseek-v4-pro
router:  siliconflow / Qwen/Qwen3.6-35B-A3B
answer:  deepseek / deepseek-v4-pro
```

Important notes:

- The backend can start without API keys in development.
- Upload, authentication, preview, search, and deterministic parsing do not
  require LLM keys.
- Summary generation and chat answer generation require valid keys for the
  providers selected by the relevant stage.
- `LLM_PROVIDER=fake` is available for local tests without external network
  calls, but production safety checks reject fake provider usage.
- The backend validates provider/model combinations against
  `app/core/llm_catalog.py`.
- Deep-thinking request fields are sent only for known supported provider/model
  combinations.
- DeepSeek Official supports JSON response format handling.

## Backend Environment

Create `backend/.env` from `backend/.env.example`.

Core app settings:

```text
APP_NAME=excel-workspace-backend
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8090
APP_CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174
```

Excel and storage settings:

```text
EXCEL_DATABASE_PATH=
EXCEL_STORAGE_ROOT=
EXCEL_PREVIEW_MAX_ROWS=500
EXCEL_MAX_UPLOAD_BYTES=52428800
EXCEL_SUPPORTED_EXTENSIONS=.xls,.xlsx,.xlsm,.xltx,.xltm
```

Upload task settings:

```text
UPLOAD_TASK_WORKER_ENABLED=true
UPLOAD_TASK_WORKER_POLL_INTERVAL_SECONDS=0.5
UPLOAD_TASK_STALE_PROCESSING_MINUTES=60
```

PDF knowledge task and parser settings:

```text
PDF_UPLOAD_TASK_WORKER_ENABLED=true
PDF_UPLOAD_TASK_WORKER_POLL_INTERVAL_SECONDS=0.5
PDF_UPLOAD_TASK_STALE_PROCESSING_MINUTES=60
PDF_PARSER_BACKEND=fake
MINERU_COMMAND=mineru
MINERU_TIMEOUT_SECONDS=300
```

`PDF_PARSER_BACKEND=fake` is intended for local development and automated
tests. Use `PDF_PARSER_BACKEND=mineru` only when the MinerU command is
installed and available to the backend process. The `/api/pdf/parser/status`
endpoint reports whether the configured parser appears available.

Chat cancellation and guardrails:

```text
CHAT_CANCELLATION_RETENTION_SECONDS=300
LLM_REQUEST_TIMEOUT_SECONDS=60
LLM_SUMMARY_MAX_PROFILE_ROWS=10
LLM_ANSWER_MAX_ROWS=20000
```

Provider credentials:

```text
LLM_PROVIDER=siliconflow
LLM_API_BASE_URL=https://api.siliconflow.cn/v1
LLM_API_KEY=

DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=

VOLCENGINE_ARK_API_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VOLCENGINE_ARK_API_KEY=
```

Stage defaults:

```text
LLM_SUMMARY_PROVIDER=deepseek
LLM_SUMMARY_MODEL=deepseek-v4-pro
LLM_ROUTER_PROVIDER=siliconflow
LLM_ROUTER_MODEL=Qwen/Qwen3.6-35B-A3B
LLM_ANSWER_PROVIDER=deepseek
LLM_ANSWER_MODEL=deepseek-v4-pro

DEEPSEEK_SUMMARY_MODEL=deepseek-v4-pro
DEEPSEEK_ROUTER_MODEL=deepseek-v4-flash
DEEPSEEK_ANSWER_MODEL=deepseek-v4-pro

VOLCENGINE_ARK_SUMMARY_MODEL=doubao-seed-2-0-pro-260215
VOLCENGINE_ARK_ROUTER_MODEL=doubao-seed-2-0-lite-260428
VOLCENGINE_ARK_ANSWER_MODEL=deepseek-v4-pro-260425
```

Auth settings:

```text
AUTH_ADMIN_EMAIL=admin@qq.com
AUTH_ADMIN_PASSWORD=admin
AUTH_SESSION_TTL_HOURS=336
AUTH_PASSWORD_RESET_TTL_MINUTES=30
AUTH_PASSWORD_HASH_ITERATIONS=260000
AUTH_EXPOSE_RESET_TOKEN=true
AUTH_LOGIN_RATE_LIMIT_MAX_FAILURES=5
AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
AUTH_COOKIE_NAME=excelai_session
AUTH_CSRF_COOKIE_NAME=excelai_csrf
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
```

Logging:

```text
LOG_LEVEL=INFO
LOG_FILE_PATH=
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

Production safety:

- Set `APP_ENV=production`.
- Change `AUTH_ADMIN_PASSWORD`.
- Set `AUTH_EXPOSE_RESET_TOKEN=false`.
- Set `AUTH_COOKIE_SECURE=true` when serving over HTTPS.
- Use `AUTH_COOKIE_SAMESITE=lax`, `strict`, or `none`.
- If `AUTH_COOKIE_SAMESITE=none`, `AUTH_COOKIE_SECURE` must be true.
- Set real non-localhost `APP_CORS_ORIGINS`.
- Do not use `APP_CORS_ORIGINS=*` in production.
- Do not use `LLM_PROVIDER=fake` in production.
- Do not rely on `PDF_PARSER_BACKEND=fake` for production PDF parsing.
- If PDF ingestion is enabled in production, install MinerU and set
  `PDF_PARSER_BACKEND=mineru`.
- Configure API keys for any provider selected by summary, router, or answer
  stages.

## Frontend Environment

Create `frontend/.env` from `frontend/.env.example`.

```text
VITE_EXCEL_WORKSPACE_API_BASE_URL=
VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS=30000
VITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS=300000
```

Local development usually keeps `VITE_EXCEL_WORKSPACE_API_BASE_URL` empty so
the browser calls the same origin and Vite proxies `/api` and `/health` to the
backend.

For static deployments behind nginx, keep it empty when nginx proxies `/api`
and `/health` on the same domain.

For a separately hosted frontend that calls an API on another origin, set:

```text
VITE_EXCEL_WORKSPACE_API_BASE_URL=https://your-api-domain.example
```

Then ensure the backend `APP_CORS_ORIGINS` includes the frontend origin.

## Local Startup

This section is written for direct copy/paste. Use two terminal windows: one
for the backend and one for the frontend.

### Prerequisites

Install:

- Python `3.11` or newer.
- Node.js `18` or newer.
- npm.

If the repository already contains `backend/.venv` and `frontend/node_modules`,
you can usually reuse them. Reinstall only when dependencies are missing or
outdated.

### macOS / Linux Backend

From the project root:

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

For day-to-day development outside restricted sandboxes, you can use reload:

```bash
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

If `--reload` fails with a filesystem watch permission error, run without
`--reload`.

Expected backend output:

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8090
```

### macOS / Linux Frontend

Open a second terminal from the project root:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The Vite config currently uses:

```text
host: 0.0.0.0
port: 5174
strictPort: true
allowedHosts: .trycloudflare.com
proxy: /api and /health -> http://127.0.0.1:8090
```

Expected frontend output:

```text
VITE ready
Local:   http://localhost:5174/
Network: http://your-lan-ip:5174/
```

Open:

```text
http://127.0.0.1:5174
```

### Windows Backend

From the project root in PowerShell:

```powershell
Set-Location .\backend
Copy-Item .env.example .env -Force
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

For reload development:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

### Windows Frontend

Open a second PowerShell from the project root:

```powershell
Set-Location .\frontend
Copy-Item .env.example .env -Force
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5174
```

### Verify Local Startup

Backend health:

```bash
curl http://127.0.0.1:8090/health
```

Expected:

```json
{"status":"ok"}
```

Backend readiness:

```bash
curl http://127.0.0.1:8090/ready
```

Expected:

```json
{"status":"ready","checks":{"storage":"ok","database":"ok"}}
```

Frontend proxy to backend:

```bash
curl http://127.0.0.1:5174/health
```

Expected:

```json
{"status":"ok"}
```

On Windows PowerShell:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8090/health | Select-Object -ExpandProperty Content
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5174/health | Select-Object -ExpandProperty Content
```

## Login And Roles

On first backend initialization, the backend ensures an admin user exists using:

```text
AUTH_ADMIN_EMAIL
AUTH_ADMIN_PASSWORD
```

If these are not set in `backend/.env`, the development defaults in
`app/core/config.py` apply. For a real shared demo, set explicit values in
`backend/.env` before starting the backend.

Users can also register from the login page. Self-registered users are members.

Role behavior:

- Admin users can upload, replace, rename, delete, and change visibility of
  workbooks.
- Admin users can update workspace LLM preferences.
- Member users can authenticate, see files visible to members, inspect data,
  search sheets, and use chat.
- Chat sessions belong to the current user.

For a friend demo, the safer path is usually:

1. Start backend, frontend, and tunnel.
2. Send the public URL.
3. Ask the friend to click `Create account`.
4. Keep admin credentials private unless they need file-management access.

## Sharing Over The Same LAN

When Vite prints a network URL such as:

```text
Network: http://192.168.3.65:5174/
```

devices on the same Wi-Fi or LAN may be able to open that address directly.

Requirements:

- The frontend process must stay running.
- The backend process must stay running.
- The other device must be able to reach your machine on the LAN.
- Local firewall settings must allow inbound access to port `5174`.

The browser should use the frontend URL only. Do not ask users to open backend
port `8090` directly except for health checks.

## Sharing Over The Internet With Cloudflare Quick Tunnel

Use this when a friend is outside your LAN and you only need a temporary demo
URL.

This project currently supports Cloudflare Quick Tunnel through Vite's
`allowedHosts` setting:

```ts
allowedHosts: ['.trycloudflare.com']
```

That line is required because Vite 7 validates the `Host` header. Without it,
requests from a generated `*.trycloudflare.com` domain may be blocked even
though the tunnel itself is working.

### Important Limitations

Cloudflare Quick Tunnel is temporary:

- The URL changes each time you start a new quick tunnel.
- The URL stops working when `cloudflared` stops.
- The URL stops working when the frontend stops.
- The app stops working when the backend stops.
- Your computer must stay awake and online.
- Account-less quick tunnels have no uptime guarantee and are intended for
  development/testing, not production.

The command used here follows Cloudflare's documented Quick Tunnel pattern:

```bash
cloudflared tunnel --url http://127.0.0.1:5174
```

Cloudflare documentation:

- Quick Tunnel:
  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/
- Cloudflared downloads:
  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

### Install Or Download cloudflared

If `cloudflared` is already installed:

```bash
cloudflared --version
```

If it is not installed on macOS with Apple Silicon, one direct temporary
download flow is:

```bash
curl -L -o /tmp/cloudflared-darwin-arm64.tgz \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz
tar -xzf /tmp/cloudflared-darwin-arm64.tgz -C /tmp
chmod +x /tmp/cloudflared
/tmp/cloudflared --version
```

On macOS Intel, Linux, or Windows, download the matching binary from the
Cloudflare downloads page above.

### Start A Public Tunnel

First make sure backend and frontend are already running:

```bash
curl http://127.0.0.1:5174/health
```

Then start the tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:5174
```

Or, if using the temporary macOS Apple Silicon binary from `/tmp`:

```bash
/tmp/cloudflared tunnel --url http://127.0.0.1:5174
```

Wait for output like:

```text
Your quick Tunnel has been created! Visit it at:
https://example-words-here.trycloudflare.com
```

That `https://...trycloudflare.com` URL is the one to share.

### Verify The Public URL

Replace the URL with the one printed by `cloudflared`:

```bash
curl https://example-words-here.trycloudflare.com/health
```

Expected:

```json
{"status":"ok"}
```

Also check the page:

```bash
curl -I https://example-words-here.trycloudflare.com/
```

Expected:

```text
HTTP/2 200
```

### Current Demo URL From This Session

At the time this README was updated, the running tunnel URL was:

```text
https://gained-lined-comedy-randy.trycloudflare.com
```

This URL is not permanent. If it fails, restart backend, frontend, and
`cloudflared`, then use the new URL printed in the tunnel log.

### If The Public URL Does Not Work

Check these in order:

1. Is the backend still running?

   ```bash
   curl http://127.0.0.1:8090/health
   ```

2. Is the frontend still running?

   ```bash
   curl http://127.0.0.1:5174/health
   ```

3. Is `cloudflared` still running in its terminal?

4. Did `cloudflared` print a different new URL after restart?

5. Does the current public URL return health?

   ```bash
   curl https://your-current-url.trycloudflare.com/health
   ```

6. Does Vite allow the host?

   `frontend/vite.config.ts` should contain:

   ```ts
   allowedHosts: ['.trycloudflare.com']
   ```

7. Did your computer sleep, change networks, or lose outbound internet?

8. If `cloudflared` logs QUIC errors but keeps running, it may fall back to
   HTTP/2. If it does not recover, restart the tunnel.

For a stable long-term public URL, use a named Cloudflare Tunnel under a
Cloudflare account or deploy the app to a server with nginx and HTTPS.

## Public APIs

Most APIs require authentication. Admin-only endpoints are noted.

Health:

```text
GET    /health
GET    /ready
```

Workspace config:

```text
GET    /api/workspace/config
```

Auth:

```text
POST   /api/auth/register
POST   /api/auth/login
GET    /api/auth/me
POST   /api/auth/logout
POST   /api/auth/password/forgot
POST   /api/auth/password/reset
```

Excel assets:

```text
POST   /api/excel/files/check-name                         admin
POST   /api/excel/files                                    admin
POST   /api/excel/files/upload-tasks                       admin
GET    /api/excel/files/upload-tasks/{task_id}             admin
GET    /api/excel/files
GET    /api/excel/files/{file_id}
PATCH  /api/excel/files/{file_id}                          admin
PATCH  /api/excel/files/{file_id}/visibility               admin
DELETE /api/excel/files/{file_id}?confirm_delete=true      admin
GET    /api/excel/files/{file_id}/active
GET    /api/excel/files/{file_id}/versions
POST   /api/excel/files/{file_id}/versions/{version_id}/activate  admin

GET    /api/excel/versions/{version_id}/sheets
GET    /api/excel/versions/{version_id}/profile
GET    /api/excel/versions/{version_id}/artifacts          admin
GET    /api/excel/versions/{version_id}/search?query=...&limit=50

GET    /api/excel/sheets/{sheet_id}/preview?offset=0&limit=500
GET    /api/excel/sheets/{sheet_id}/rows?offset=0&limit=500
GET    /api/excel/sheets/{sheet_id}/search?query=...&limit=50
GET    /api/excel/sheets/{sheet_id}/rows/{row_id}
```

Document summaries:

```text
POST   /api/excel/versions/{version_id}/summary/generate
GET    /api/excel/versions/{version_id}/summary
PATCH  /api/excel/versions/{version_id}/summary
```

Chat and LLM:

```text
GET    /api/excel/llm/options
GET    /api/excel/llm/preferences
PATCH  /api/excel/llm/preferences                          admin

POST   /api/excel/chat
POST   /api/excel/chat/cancel

POST   /api/excel/chat/sessions
GET    /api/excel/chat/sessions
GET    /api/excel/chat/sessions/{session_id}
GET    /api/excel/chat/sessions/{session_id}/turns
PATCH  /api/excel/chat/sessions/{session_id}
PATCH  /api/excel/chat/sessions/{session_id}/pin
DELETE /api/excel/chat/sessions/{session_id}

POST   /api/excel/chat/sessions/{session_id}/messages
POST   /api/excel/chat/sessions/{session_id}/route
POST   /api/excel/chat/sessions/{session_id}/answer
```

PDF knowledge:

```text
GET    /api/pdf/files
GET    /api/pdf/parser/status
POST   /api/pdf/files/upload-tasks                       admin
GET    /api/pdf/files/upload-tasks                       admin
GET    /api/pdf/files/upload-tasks/{task_id}             admin
GET    /api/pdf/files/{file_id}/detail
GET    /api/pdf/files/{file_id}/chunks
POST   /api/pdf/chat
POST   /api/pdf/files/{file_id}/summary/generate
GET    /api/pdf/model-settings
PATCH  /api/pdf/model-settings/{setting_id}
```

FastAPI also exposes a generated OpenAPI schema while the backend is running:

```text
http://127.0.0.1:8090/openapi.json
http://127.0.0.1:8090/docs
```

## Quality Checks

Backend lint:

```bash
cd backend
./.venv/bin/python -m ruff check app tests
```

Backend tests:

```bash
cd backend
./.venv/bin/python -m pytest
```

PDF-focused backend tests:

```bash
cd backend
./.venv/bin/python -m pytest tests/test_pdf_knowledge_api.py tests/test_pdf_parser_factory.py tests/test_mineru_parser.py
```

On Windows, if pytest cannot access its default temp directory, run the same
PDF-focused tests with a project-local base temp directory:

```powershell
.\.venv\Scripts\python -m pytest tests/test_pdf_knowledge_api.py tests/test_pdf_parser_factory.py tests/test_mineru_parser.py --basetemp pytest-tmp -p no:cacheprovider
```

Frontend typecheck:

```bash
cd frontend
npm run typecheck
```

Frontend build:

```bash
cd frontend
npm run build
```

Latest recorded local status in the repository previously documented:

```text
backend ruff: passed
backend pytest: 57 passed
backend PDF pytest subset: 19 passed
frontend vue-tsc: passed
frontend vite build: passed
```

Run the checks again after meaningful code changes.

## Single-Server Deployment With nginx

Recommended deployment shape:

- Ubuntu 22.04 or 24.04.
- Backend served by `systemd` running Uvicorn on `127.0.0.1:8090`.
- Frontend built with `npm run build`.
- nginx serves `frontend/dist`.
- nginx proxies `/api` and `/health` to the backend.
- Add TLS with your normal certificate process for public use.

### Deployment Target

Example project path:

```text
/opt/excel-workspace
```

Expected structure:

```text
/opt/excel-workspace/backend
/opt/excel-workspace/frontend
/opt/excel-workspace/contracts
/opt/excel-workspace/docs
```

### Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Configure Backend

```bash
cd /opt/excel-workspace/backend
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[dev]'
```

Edit `backend/.env` for deployment:

```text
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8090
APP_CORS_ORIGINS=https://your-domain.example
AUTH_ADMIN_EMAIL=your-admin@example.com
AUTH_ADMIN_PASSWORD=replace-with-a-strong-password
AUTH_EXPOSE_RESET_TOKEN=false
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
LLM_API_KEY=your-siliconflow-key-if-used
DEEPSEEK_API_KEY=your-deepseek-key-if-used
VOLCENGINE_ARK_API_KEY=your-ark-key-if-used
```

If you are initially deploying only upload/preview/search without LLM features,
you can leave unused provider keys empty, but any provider selected by summary,
router, or answer stage must have a key for those features to work.

### Test Backend Manually

```bash
cd /opt/excel-workspace/backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

In another terminal:

```bash
curl http://127.0.0.1:8090/health
curl http://127.0.0.1:8090/ready
```

Stop the manual server with `Ctrl+C`.

### Create systemd Service

```bash
sudo tee /etc/systemd/system/excel-workspace-backend.service > /dev/null <<'EOF'
[Unit]
Description=Excel Workspace Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/excel-workspace/backend
ExecStart=/opt/excel-workspace/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
Restart=always
RestartSec=3
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
EOF
```

Make sure `www-data` can read the app and write runtime storage:

```bash
sudo mkdir -p /opt/excel-workspace/storage
sudo chown -R www-data:www-data /opt/excel-workspace/storage
sudo chown -R www-data:www-data /opt/excel-workspace/backend
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable excel-workspace-backend
sudo systemctl start excel-workspace-backend
sudo systemctl status excel-workspace-backend --no-pager
```

Logs:

```bash
journalctl -u excel-workspace-backend -f
```

### Build Frontend

```bash
cd /opt/excel-workspace/frontend
cp .env.example .env
printf "VITE_EXCEL_WORKSPACE_API_BASE_URL=\nVITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS=30000\nVITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS=300000\n" > .env
npm install
npm run build
```

Output:

```text
/opt/excel-workspace/frontend/dist
```

### Configure nginx

```bash
sudo tee /etc/nginx/sites-available/excel-workspace > /dev/null <<'EOF'
server {
    listen 80;
    server_name your-domain.example;

    root /opt/excel-workspace/frontend/dist;
    index index.html;

    client_max_body_size 60m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ready {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

Enable site:

```bash
sudo ln -sf /etc/nginx/sites-available/excel-workspace /etc/nginx/sites-enabled/excel-workspace
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

Verify:

```bash
curl http://127.0.0.1/health
curl http://your-domain.example/health
```

Open:

```text
http://your-domain.example/
```

For public production usage, configure HTTPS and then update:

```text
APP_CORS_ORIGINS=https://your-domain.example
AUTH_COOKIE_SECURE=true
```

Restart backend after changing `.env`:

```bash
sudo systemctl restart excel-workspace-backend
```

### Updating A Deployment

Backend code update:

```bash
cd /opt/excel-workspace/backend
./.venv/bin/python -m pip install -e '.[dev]'
sudo systemctl restart excel-workspace-backend
```

Frontend code update:

```bash
cd /opt/excel-workspace/frontend
npm install
npm run build
sudo systemctl restart nginx
```

Environment-only update:

```bash
sudo systemctl restart excel-workspace-backend
```

## Troubleshooting

### The public Cloudflare URL cannot be opened

Most common cause: the earlier quick tunnel process stopped. Quick Tunnel URLs
are temporary and tied to the running `cloudflared` process.

Fix:

```bash
curl http://127.0.0.1:8090/health
curl http://127.0.0.1:5174/health
cloudflared tunnel --url http://127.0.0.1:5174
```

Use the new `https://...trycloudflare.com` URL printed in the latest terminal.

### The old trycloudflare URL worked before but not now

This is expected if the tunnel was restarted or the process ended. Account-less
quick tunnels generate random hostnames and do not preserve the old URL.

### Vite returns a blocked-host page through Cloudflare

Confirm `frontend/vite.config.ts` contains:

```ts
allowedHosts: ['.trycloudflare.com']
```

Restart the frontend dev server after changing the config.

### Page opens, but it stays on "Checking session"

Check that the backend is reachable through the frontend proxy:

```bash
curl http://127.0.0.1:5174/health
curl https://your-current-url.trycloudflare.com/health
curl -i https://your-current-url.trycloudflare.com/api/auth/me
```

`/api/auth/me` should return `401` when not logged in. That means the API path
is reachable and the UI should fall through to the sign-in page.

### Backend starts but summary/chat fails

Upload, preview, search, and auth do not require LLM keys. Summary generation
and chat do. PDF chat also requires an answer-stage LLM provider when indexed
PDF chunks are available.

Check:

```text
LLM_SUMMARY_PROVIDER
LLM_ROUTER_PROVIDER
LLM_ANSWER_PROVIDER
LLM_API_KEY
DEEPSEEK_API_KEY
VOLCENGINE_ARK_API_KEY
```

The selected provider for each stage must have a valid key.

### PDF upload stays queued or parsing

Check:

- `PDF_UPLOAD_TASK_WORKER_ENABLED=true`.
- The backend process was restarted after changing PDF worker settings.
- `/api/pdf/files/upload-tasks` shows the task `stage`, `parser_backend`, and
  `error_code`.
- Stale processing tasks are marked failed during backend startup and by the
  PDF worker stale-task cleanup path.

If the parser backend is `mineru`, also check:

```bash
mineru --version
```

or call:

```bash
curl http://127.0.0.1:8090/api/pdf/parser/status
```

### PDF parsing fails with MinerU unavailable or timeout

Check:

- `PDF_PARSER_BACKEND=mineru` only when MinerU is installed.
- `MINERU_COMMAND` matches the command available to the backend process.
- `MINERU_TIMEOUT_SECONDS` is high enough for the uploaded PDF.
- The PDF file is not empty, corrupted, unsupported, or above the upload size
  limit.

For local development without MinerU, use:

```text
PDF_PARSER_BACKEND=fake
```

### Backend reports `No module named uvicorn`

Install backend dependencies:

```bash
cd backend
./.venv/bin/python -m pip install -e '.[dev]'
```

Windows:

```powershell
cd backend
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

### Backend `--reload` fails with an operation-permitted error

Run without reload:

```bash
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

This can happen in restricted local environments where file-watch APIs are not
available.

### Frontend says port 5174 is already in use

Find the process using the port:

```bash
lsof -nP -iTCP:5174 -sTCP:LISTEN
```

Stop that process or change the Vite port. The checked-in config uses
`strictPort: true`, so Vite will fail instead of silently switching ports.

### Backend says port 8090 is already in use

```bash
lsof -nP -iTCP:8090 -sTCP:LISTEN
```

Stop the old backend process or start the new one on a different port and
update the frontend proxy accordingly.

### Upload fails for large files

Check:

- `EXCEL_MAX_UPLOAD_BYTES` in `backend/.env`.
- PDF knowledge uploads currently use a 50 MB per-file limit.
- `MINERU_TIMEOUT_SECONDS` if PDF parsing starts but does not finish.
- nginx `client_max_body_size` in production.
- Browser/network timeouts.
- Whether async upload task polling is enabled.

### Existing files list correctly, but preview returns 500 after moving the project

Current versions persist artifact references relative to `EXCEL_STORAGE_ROOT`,
so moving the project directory should not break existing uploads. The backend
also runs migration `13`, `normalize_storage_artifact_references`, during
startup to convert older absolute rows such as:

```text
/old/project/storage/files/...
C:/old/project/storage/files/...
```

into:

```text
files/...
upload-tasks/...
```

If this symptom appears after moving the project, restart the backend first so
the migration and the new storage resolver are definitely active:

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Then audit the runtime database. A healthy migrated database should report zero
absolute artifact references:

```bash
sqlite3 storage/excel-workspace.sqlite3 "
select count(*) as absolute_sheet_paths
from excel_sheets
where raw_csv_path like '/%' or raw_csv_path like '%:%';

select count(*) as absolute_artifact_paths
from excel_artifacts
where path like '/%' or path like '%:%';

select count(*) as absolute_upload_task_paths
from excel_upload_tasks
where staging_path like '/%' or staging_path like '%:%';
"
```

Also confirm the migration has been applied:

```bash
sqlite3 storage/excel-workspace.sqlite3 "
select version, name
from schema_migrations
where version = 13;
"
```

Do not repair normal path moves by replacing one project absolute path with
another project absolute path. That only moves the same portability problem to a
new directory. If legacy rows remain after restart, back up
`storage/excel-workspace.sqlite3`, inspect the rows, and normalize them to the
storage-relative form beginning with `files/` or `upload-tasks/`.

### Member cannot see a file

Admin users can toggle file visibility. Member users only see files marked
visible to members.

### Login is rate limited

Repeated failed logins are rate-limited. Wait for
`AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS` or change the value in development.

### Reset token is visible in development

`AUTH_EXPOSE_RESET_TOKEN=true` is for development. Production must set:

```text
AUTH_EXPOSE_RESET_TOKEN=false
```

## Current Risks And Known Gaps

- Chat routing still considers active document summaries across the accessible
  knowledge base; there is not yet an explicit per-chat file-scope selector.
- Answer-stage row loading is guarded by `LLM_ANSWER_MAX_ROWS`, but very large
  selected documents can still increase latency and cost.
- Backend citation verification proves cited row IDs exist and belong to the
  selected/attached data; it does not yet prove every natural-language claim is
  semantically entailed by the cited row.
- External model providers can reject prompts because of provider-specific
  token limits or model availability.
- Account-less Quick Tunnel is useful for demos but not stable enough for
  production.
- `ExcelWorkspaceApp.vue` and several CSS surfaces are still large and should
  continue being split into smaller components/composables.

## Current Priorities

- Add explicit chat file scope.
- Add retrieval or deterministic row narrowing before answer-stage model calls.
- Improve chat-stage observability and diagnostics.
- Continue splitting large frontend state and CSS modules.
- Extend session inspection APIs beyond metadata and turn listing if needed.
- Add production-grade tunnel/deployment instructions for named Cloudflare
  tunnels if the team chooses Cloudflare as the long-term sharing mechanism.

## Further Reading

- `backend/README.md`: backend-specific structure, APIs, checks, and storage.
- `frontend/README.md`: frontend-specific scope and run instructions.
- `docs/architecture.md`: architecture boundaries and versioning rule.
- `docs/processing-pipeline.md`: upload and row-provenance pipeline.
- `docs/api-design.md`: API namespace notes.
- `docs/engineering-standards.md`: engineering conventions.
- `project_inspection.md`: deeper implementation inspection and historical
  context.
