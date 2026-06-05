# Project Inspection: Excel Workspace / Document Assistant

Date: 2026-06-05  
Workspace root: `/Users/intertek/Desktop/Intertek-dev/Document-Assistant`  
Main implementation directory: `excel_workspace/`

## 1. Executive Summary

This project is being turned into a trustworthy enterprise Excel question-answering system.

The direction has deliberately moved away from generic document RAG for Excel. The current architecture treats Excel as structured enterprise data:

- Deterministic backend preprocessing reads Excel files, splits sheets, injects stable row IDs, writes raw CSV artifacts, builds row mappings, and creates structured profiles.
- LLMs are used only where appropriate: document description, document routing, and natural-language answer synthesis.
- Original files and row-level provenance remain the source of truth.
- Answers must cite backend-verified row IDs so the frontend can highlight the exact source row.

The current implementation is a real runnable MVP, not a fake demo. It supports upload, versioned replacement, sheet preview, profile/artifacts APIs, document summary generation, chat sessions, multi-turn file attachment state, full-row context loading, and row-level citation lookup.

## 2. Product Goal

The intended product is:

> Excel file version management + deterministic structured conversion + document description + lightweight model routing + controlled Excel answer generation + row-level source highlighting.

Business-level interpretation:

- The chat product is a knowledge-base Q&A experience over uploaded Excel workbooks, not merely a "current spreadsheet tab" assistant.
- The user may ask questions that naturally span multiple uploaded workbooks. The router exists to choose relevant document versions from document descriptions before the answer model sees rows.
- A selected file/version in the UI is primarily a preview and inspection context.
- The current implementation still routes across active document summaries in the knowledge base. It should not be assumed that chat is restricted to only the workbook currently previewed in the UI.

User workflow:

1. User uploads Excel files in the knowledge-base/file-management area.
2. Backend parses Excel deterministically.
3. Backend generates a lightweight workbook profile.
4. A large model generates a document description from the profile only.
5. Later, user opens the chat area and asks a question.
6. A fast model chooses relevant document versions from document descriptions.
7. Backend attaches selected file versions to the chat session.
8. Backend sends attached file rows and chat history to the analysis model.
9. Model returns answer blocks with row IDs.
10. Backend verifies row IDs.
11. Frontend shows the answer, citations, and highlights source rows in a web table.

## 3. Current Technical Stack

Backend:

- Python 3.12
- FastAPI
- SQLite
- openpyxl for `.xlsx`
- xlrd for legacy `.xls`
- pydantic-settings
- ruff
- pytest

Frontend:

- Vue 3
- TypeScript
- Vite
- Native CSS

LLM provider:

- SiliconFlow-compatible chat completions endpoint
- Supported selectable models:
  - `deepseek-ai/DeepSeek-V4-Pro`
  - `Pro/deepseek-ai/DeepSeek-V3.2`
  - `Qwen/Qwen3.6-27B`
  - `Qwen/Qwen3.6-35B-A3B`
  - `inclusionAI/Ling-flash-2.0`
- Default summary model: `deepseek-ai/DeepSeek-V4-Pro`
- Default router model: `inclusionAI/Ling-flash-2.0`
- Default answer model: `deepseek-ai/DeepSeek-V4-Pro`
- Fake LLM adapter exists for local tests only

Do not commit real API keys. Backend `.env` is ignored and must remain local.

## 4. Repository Layout

Important paths:

```text
excel_workspace/
  README.md
  backend/
    app/
      api/
        routes/
          excel_assets.py
          document_summaries.py
          chat.py
          health.py
        schemas.py
        dependencies.py
      application/
        excel_assets/
          service.py
          profile.py
          models.py
        document_summaries/
          service.py
        chat/
          service.py
      adapters/
        workbook/
          openpyxl_reader.py
        repositories/
          sqlite_repository.py
        storage/
          filesystem_storage.py
        llm/
          siliconflow_client.py
          fake_llm_client.py
      domain/
        models.py
      ports/
        repository.py
        llm_client.py
        storage.py
        workbook_reader.py
      core/
        config.py
        errors.py
        ids.py
        time.py
    tests/
    pyproject.toml
  frontend/
    src/
      app/
        ExcelWorkspaceApp.vue
      components/
        ChatPanel.vue
        CitationPanel.vue
        SourceTracePanel.vue
      api/
        excel-assets-api.ts
        document-summaries-api.ts
        chat-api.ts
      types/
        excel-assets.ts
        document-summary.ts
        chat.ts
      style.css
    package.json
    vite.config.ts
  docs/
  contracts/
```

The `excel_workspace` directory is currently the main project area. At the time of inspection, the directory appears untracked from Git's perspective in the parent repository, so the next engineer should review Git state before committing.

## 5. Backend Architecture

The backend is organized around clean boundaries:

- `domain/models.py`: immutable dataclass domain objects.
- `ports/`: protocols for repositories, storage, workbook reading, and LLM clients.
- `adapters/`: concrete SQLite, filesystem, workbook reader, and LLM implementations.
- `application/`: business services.
- `api/`: FastAPI route handlers and pydantic schemas.

This structure should be preserved. Avoid putting SQL, filesystem, or LLM prompt construction directly into route handlers.

## 6. Core Domain Model

Excel assets:

- `ExcelFile`
- `ExcelFileVersion`
- `ExcelSheet`
- `ExcelArtifact`
- `ExcelRowMapping`
- `WorkbookProfile`
- `SheetProfile`

Document descriptions:

- `DocumentSummary`
- `SheetSummary`

Chat:

- `ChatSession`
- `AttachedDocument`
- `ChatTurn`
- `SelectedDocument`
- `DraftChatAnswer`
- `ExcelCitation`
- `ChatAnswer`
- `ChatRouteResult`
- `ChatStageTiming`

The most important design decision is that user-visible file replacement is internally implemented as a new version. Old versions and row references remain addressable.

## 7. Database / Persistence

SQLite repository:

`backend/app/adapters/repositories/sqlite_repository.py`

The repository currently handles:

- Excel files
- File versions
- Sheets
- Artifacts
- Row mappings
- Document summaries
- Sheet summaries
- Chat sessions
- Attached chat-session documents
- Chat turns

Key tables:

```text
excel_files
excel_file_versions
excel_sheets
excel_artifacts
excel_row_mappings
document_summaries
document_sheet_summaries
chat_sessions
chat_session_documents
chat_turns
```

Summary persistence was added because the earlier summary service was memory-only. A generated document summary now survives backend restarts.

Default database path:

```text
excel_workspace/storage/excel-workspace.sqlite3
```

This can be overridden:

```text
EXCEL_DATABASE_PATH=/path/to/file.sqlite3
EXCEL_STORAGE_ROOT=/path/to/storage
```

These overrides were used during isolated safety testing.

## 8. File Upload And Excel Processing

Upload service:

`backend/app/application/excel_assets/service.py`

API route:

`backend/app/api/routes/excel_assets.py`

Current behavior:

1. Validates Excel upload extension.
2. Enforces upload size limit.
3. Detects duplicate display name.
4. If duplicate and `replace_existing=false`, returns `409` with `requires_confirmation=true`.
5. If duplicate and `replace_existing=true`, creates a new version.
6. Parses workbook sheets.
7. Writes original file artifact.
8. Writes one raw CSV per sheet.
9. Adds stable row IDs in the first column:

```text
S001_R1
S001_R2
S002_R1
```

10. Writes row mapping CSV.
11. Writes workbook profile JSON.
12. Marks the new version as active only after processing succeeds.

Supported formats:

- `.xlsx`
- `.xls`
- also accepted by frontend: `.xlsm`, `.xltx`, `.xltm`

The backend workbook reader uses openpyxl for modern workbooks and xlrd for legacy `.xls`.

## 9. Workbook Profile

Profile is deterministic and does not require the model.

Profile includes:

- file ID
- version ID
- original filename
- file hash
- sheet list
- sheet code
- sheet name
- row count
- column count
- candidate header
- sample rows

API:

```text
GET /api/excel/versions/{version_id}/profile
```

This profile is sent to the large model for document summary generation. The raw full workbook is not sent during summary generation.

## 10. Document Summary Generation

Service:

`backend/app/application/document_summaries/service.py`

Adapter:

`backend/app/adapters/llm/siliconflow_client.py`

API:

```text
POST /api/excel/versions/{version_id}/summary/generate
GET  /api/excel/versions/{version_id}/summary
```

Current behavior note:

- Summary generation supports a per-request model override.
- The frontend exposes separate model selectors for summary, router, and answer stages.

The summary prompt instructs the model to return strict JSON with:

- summary text
- business domain
- key topics
- suitable questions
- unsuitable questions
- per-sheet summaries
- important columns
- likely question types

Important: generated summaries are now persisted in SQLite.

## 11. Chat / Q&A Flow

API route:

`backend/app/api/routes/chat.py`

Application service:

`backend/app/application/chat/service.py`

Primary APIs:

```text
POST /api/excel/chat
POST /api/excel/chat/sessions
GET  /api/excel/chat/sessions/{session_id}
POST /api/excel/chat/sessions/{session_id}/messages
POST /api/excel/chat/sessions/{session_id}/route
POST /api/excel/chat/sessions/{session_id}/answer
```

`/messages` runs both route and answer.

`/route` and `/answer` split the process for better frontend progress indicators:

- `/route` calls the router model, attaches new documents, and returns selected/attached documents.
- `/answer` uses the versions selected for the current turn when they are supplied and calls the answer model.

The frontend currently uses the session-oriented flow through `chat-api.ts`.

## 12. Multi-Turn Chat Session Logic

The current multi-turn design:

1. Frontend creates a `session_id` on first question.
2. Router model receives:

```text
current question
all user questions in this session
recent chat turns
already attached documents
candidate new document summaries
```

3. Router model must not receive Excel rows.
4. Router model can see recent assistant answer text through previous turn records.
5. If router selects a file version not yet attached to this session, backend records it in `chat_session_documents`.
6. If router selects the same version again, backend does not attach a duplicate.
7. Answer model receives:

```text
current question
previous chat turns
selected documents for the current turn
rows for those selected documents
```

8. Backend verifies row IDs returned by the model against attached document rows.

Important nuance:

The project uses stateless chat-completions APIs. Even though the backend tracks "already attached" files, rows still have to be included in later model calls if the model needs to see them. The current session state prevents duplicate attachment records and duplicate file-context construction in backend state, but it does not eliminate token cost unless the provider supports server-side sessions or prompt/context caching.

Current implementation note:

- Chat request schemas now also accept request-level router/answer model overrides.
- Summary generation accepts a request-level summary model override.
- The router currently considers active document summaries in the knowledge base.
- The frontend does not currently pass any explicit chat file scope to the backend.

## 13. Current LLM Prompt Stages

Prompts live in:

`backend/app/adapters/llm/siliconflow_client.py`

Stages:

1. `DOCUMENT_SUMMARY_SYSTEM_PROMPT`
   - Generates structured metadata summary from deterministic workbook profile only.

2. `DOCUMENT_ROUTER_SYSTEM_PROMPT`
   - Uses a conservative routing strategy.
   - Prefers reusing already attached documents before expanding to new ones.
   - Selects relevant document versions from attached/candidate summaries.
   - Does not answer the user question.
   - Does not see Excel rows.

3. `ANSWER_SYSTEM_PROMPT`
   - Answers using provided Excel rows only.
   - Must return strict JSON.
   - Must cite row IDs from provided rows only.

The response JSON is parsed and validated. Unknown file/version IDs from router output are filtered. Invalid citation row IDs from the answer stage are discarded with warnings.

## 14. Citation And Highlighting

The model returns evidence row IDs such as:

```text
S001_R89
S002_R95
```

The backend converts verified row IDs into citation IDs:

```text
C1
C2
```

Frontend displays `[C1]`, `[C2]`.

Clicking a citation should:

1. Switch to the citation's file/version if needed.
2. Switch to the citation's sheet.
3. Lookup row by row ID.
4. Scroll the table to the row.
5. Highlight the row.

Lookup API:

```text
GET /api/excel/sheets/{sheet_id}/rows/{row_id}
```

Preview API:

```text
GET /api/excel/sheets/{sheet_id}/preview?offset=0&limit=250
```

Rows API:

```text
GET /api/excel/sheets/{sheet_id}/rows?offset=0&limit=500
```

## 15. Frontend State

Main app:

`frontend/src/app/ExcelWorkspaceApp.vue`

The UI is split into:

- File management / knowledge-base view
- Chat analysis view

Key features:

- Upload workbook
- Duplicate upload replacement confirmation
- File table
- Version and sheet selection
- Summary generation
- Spreadsheet preview
- Row lookup by row ID
- Chat session creation
- Question submission
- Citation display
- Source trace display

Chat component:

`frontend/src/components/ChatPanel.vue`

Chat API:

`frontend/src/api/chat-api.ts`

Types:

`frontend/src/types/chat.ts`

The frontend has been styled with native CSS in:

`frontend/src/style.css`

No Tailwind runtime or external icon library is required.

Recent frontend improvements:

- Chat history is now preserved across turns instead of showing only the latest answer.
- The UI now exposes per-stage model selection for summary, router, and answer.
- File deletion is available from the UI with explicit confirmation before hard deletion.

Known frontend issue:

- Data Chat citations/source trace can still crowd the right column and make the input area less comfortable than desired during long answer sessions:
  - keep input fixed at the bottom,
  - make chat history independently scrollable,
  - make citation/source panels collapsible or independently scrollable.

## 16. API Summary

Health:

```text
GET /health
```

Excel assets:

```text
POST /api/excel/files
GET  /api/excel/files
DELETE /api/excel/files/{file_id}
GET  /api/excel/files/{file_id}/versions
GET  /api/excel/files/{file_id}/active
GET  /api/excel/versions/{version_id}/sheets
GET  /api/excel/versions/{version_id}/profile
GET  /api/excel/versions/{version_id}/artifacts
GET  /api/excel/sheets/{sheet_id}/preview
GET  /api/excel/sheets/{sheet_id}/rows
GET  /api/excel/sheets/{sheet_id}/rows/{row_id}
```

Document summary:

```text
POST /api/excel/versions/{version_id}/summary/generate
GET  /api/excel/versions/{version_id}/summary
```

Chat:

```text
GET  /api/excel/llm/options
POST /api/excel/chat
POST /api/excel/chat/sessions
GET  /api/excel/chat/sessions/{session_id}
POST /api/excel/chat/sessions/{session_id}/messages
POST /api/excel/chat/sessions/{session_id}/route
POST /api/excel/chat/sessions/{session_id}/answer
```

## 17. Environment Configuration

Backend settings:

`backend/app/core/config.py`

Important environment variables:

```text
APP_HOST
APP_PORT
APP_CORS_ORIGINS
EXCEL_DATABASE_PATH
EXCEL_STORAGE_ROOT
EXCEL_PREVIEW_MAX_ROWS
EXCEL_MAX_UPLOAD_BYTES
LLM_PROVIDER
LLM_API_BASE_URL
LLM_API_KEY
LLM_SUMMARY_MODEL
LLM_ROUTER_MODEL
LLM_ANSWER_MODEL
LLM_REQUEST_TIMEOUT_SECONDS
LLM_SUMMARY_MAX_PROFILE_ROWS
LLM_CHAT_ROWS_PER_SHEET
```

Note:

- `LLM_CHAT_ROWS_PER_SHEET` is now legacy-ish. The chat service was changed to load all attached document rows in pages. It still exists in settings but should be removed or repurposed later to avoid confusion.
- Never commit real `LLM_API_KEY`.

Frontend settings:

`frontend/.env.example`

Important variables:

```text
VITE_EXCEL_WORKSPACE_API_BASE_URL
VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS
VITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS
```

## 18. How To Run Locally

Backend:

```bash
cd /Users/intertek/Desktop/Intertek-dev/Document-Assistant/excel_workspace/backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Frontend:

```bash
cd /Users/intertek/Desktop/Intertek-dev/Document-Assistant/excel_workspace/frontend
PATH=/private/tmp/node-v24.14.0-darwin-arm64/bin:$PATH npm run dev -- --host 127.0.0.1 --port 5174
```

URLs:

```text
Backend health: http://127.0.0.1:8090/health
Frontend:       http://127.0.0.1:5174/
```

The local Node path above was used in the current Codex environment. On a normal workstation, system Node/npm may be fine if versions satisfy `package.json`.

## 19. How To Test

Backend:

```bash
cd /Users/intertek/Desktop/Intertek-dev/Document-Assistant/excel_workspace/backend
./.venv/bin/python -m ruff check app tests
./.venv/bin/python -m pytest
```

Frontend:

```bash
cd /Users/intertek/Desktop/Intertek-dev/Document-Assistant/excel_workspace/frontend
PATH=/private/tmp/node-v24.14.0-darwin-arm64/bin:$PATH npm run build --cache /private/tmp/npm-cache
```

Latest recorded status:

```text
ruff: passed
pytest: 22 passed
npm run build: passed
```

## 20. Real Chain Validation Performed

A real end-to-end test was performed with a sanitized workbook generated specifically for testing. It did not use the user's original Excel as model input.

Sanitized file:

```text
/private/tmp/sanitized_chain_test_20260605.xlsx
```

It contained small constructed rows like:

```text
coffee maker / IEC / IEC 60335-2-15:2012+A1:2016
pot coffee-maker / EN / EN 60335-2-15:2016+A11:2018
kettle / AS/NZS / AS/NZS 60335.2.15:2013+A1:2016
```

Verified in an isolated backend with separate SQLite and storage:

```text
EXCEL_DATABASE_PATH=/private/tmp/excelai-isolated-chain.sqlite3
EXCEL_STORAGE_ROOT=/private/tmp/excelai-isolated-storage
```

Validated:

- upload
- parse
- profile
- summary generation using SiliconFlow
- chat session creation
- first-turn Q&A
- second-turn Q&A
- file attachment de-duplication
- citation row lookup
- sheet preview

Example first-turn answer:

```text
Question: coffee maker适用的标准
Answer: coffee maker适用的标准是 IEC 60335-2-15:2012+A1:2016
Citations: S001_R2, S002_R2
```

Example second-turn behavior:

```text
Question: EN区域呢？
newly_attached_documents: []
Citation: S001_R3
```

This proved that the model chain works with sanitized data and that session attachment de-duplication works.

## 21. Important Safety Finding

During testing, a critical behavior was discovered:

The router currently considers all active document summaries in the knowledge base. If both a sanitized file and a real/original file are active and semantically relevant, the router can select both. Then the answer model receives rows from both attached files.

This is correct for general multi-file knowledge-base search, but unsafe for tests or user flows that intend to restrict Q&A to one file or a defined subset.

Recommended next fix:

Add explicit chat file scope so the router can be limited when product or test flows require it. The frontend should expose the active scope clearly to the user. This is also necessary for future enterprise access control.

## 22. Known Technical Risks

1. Large context cost

The current MVP sends all rows for attached files to the answer model. This satisfies the current requirement but will not scale to very large workbooks.

Future mitigation:

- prompt/context cache
- provider-side session cache if available
- DuckDB/SQL query layer
- row filtering before answer model
- chunked retrieval with deterministic row IDs

2. Stateless LLM APIs

Chat-completions APIs are stateless. Session state is managed by the backend, but any rows needed by the model must still be included in the request unless provider-level caching exists.

3. Model latency

Recorded sanitized tests showed:

- route model often returns in a few seconds
- answer model can take 25-70+ seconds

Frontend should show route/answer progress separately. Split route/answer APIs already exist to support this.

Recent local runtime observations:

- route for `coffee maker用什么做lvd`: about `4.57s`
- answer with `deepseek-ai/DeepSeek-V4-Pro`: about `85.2s`

4. Model context limits

Runtime debugging confirmed a real current limit: `Pro/deepseek-ai/DeepSeek-V3.2` can fail at the answer stage with a provider `400` when the selected-document rows are too large for that model's prompt-token limit. One reproduced failure showed:

- selected documents: `2`
- row count: `1559`
- provider error: `number of input tokens (241964) has exceeded max_prompt_tokens (163840) limit`

5. Citation quality

The backend verifies that row IDs exist, but it does not yet prove that the cited row semantically supports the exact claim. This is acceptable for MVP, but future versions should add stricter claim/evidence validation.

6. Excel complexity

Real Excel files may have:

- title blocks
- empty rows
- merged cells
- formulas
- multi-table sheets
- hidden sheets
- display formatting important to interpretation

Current raw grid handling is row-level and display-text oriented. It does not attempt visual Excel reconstruction.

7. Frontend source panel layout

Citation/source panels can crowd the chat input area. Needs UI refinement.

## 23. Immediate Next Development Priorities

Recommended order:

1. Add chat file scope

This is the most important next backend feature. It prevents unintended file selection and is a foundation for permissioning.

2. Add context-size guardrails

If selected rows exceed a safe character/token budget for the chosen answer model, the backend should fail clearly or shrink context deterministically instead of relying on provider-side `400` errors.

3. Improve frontend chat layout

Make the input always reachable and make citations/source trace collapsible or independently scrollable.

4. Remove or rename legacy `LLM_CHAT_ROWS_PER_SHEET`

It is misleading now that all attached rows are loaded.

5. Add integration tests if scoped routing is introduced

Once file scope exists, add tests proving a relevant but out-of-scope file is not selected or sent.

6. Add better session inspection API

Current `GET /chat/sessions/{session_id}` returns only session metadata. Future API should expose:

```text
attached documents
turn list
last citations
timings
```

7. Improve timing/observability

`ChatStageTiming` exists and timings are returned. Next step is structured logging and perhaps a lightweight trace ID.

## 24. Suggested Engineering Principles Going Forward

- Keep deterministic parsing separate from LLM behavior.
- Keep row IDs backend-generated only.
- Never trust model-generated citations without backend verification.
- Preserve file/version identity in every derived artifact.
- Avoid hiding truncation. Either send all intended rows or return a clear limit error.
- Do not put SQL or LLM prompt logic in route handlers.
- Prefer API-level tests for behavioral guarantees.
- Treat all workbook-derived rows as potentially sensitive data.
- Use isolated test storage/database when testing against external LLM providers.

## 25. Handoff Checklist

Before the next engineer starts feature work:

1. Confirm `.env` exists locally and contains the intended LLM provider settings.
2. Confirm no real API key is committed.
3. Run:

```bash
cd excel_workspace/backend
./.venv/bin/python -m ruff check app tests
./.venv/bin/python -m pytest
```

4. Run:

```bash
cd excel_workspace/frontend
npm run build
```

5. Start backend/frontend.
6. Upload or select a test workbook.
7. Generate summary.
8. Create a chat session.
9. Ask a test question.
10. Click citations and confirm row highlight.

## 26. Current Status In One Sentence

The project has a real working Excel QA MVP with versioned uploads, deterministic row-level provenance, persistent summaries, configurable SiliconFlow model selection, session-aware multi-turn chat, conservative router prompts, verified citations, document deletion, and a Vue testing UI; the next critical backend tasks are explicit chat file scope and answer-stage context guardrails.
