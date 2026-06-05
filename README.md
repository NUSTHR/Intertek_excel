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

## Project Plan

This section is the working implementation plan for the Excel Workspace product.
Future engineers should treat it as the local roadmap and keep it updated as
features move from planned to complete.

### Product Objective

Excel Workspace is the source-of-truth system for Excel-based reference assets.
It should let users upload workbooks, preserve every original version, inspect
sheets as normalized tabular data, locate rows with stable IDs, and later cite
those rows from document-assistant answers or comparison workflows. The system
must remain independently runnable while it lives in this repository.

The first production-grade use case is a standards-version workbook with
multiple sheets, old `.xls` format support, Chinese and English cell content,
dates, remarks, test requirements, and version-specific notes. The product must
handle that class of workbook without manual conversion.

### Current Implementation Baseline

- Backend app: FastAPI service under `backend/app`, exposed on port `8090`.
- Frontend app: Vue/Vite app under `frontend/src`, exposed on port `5174`.
- Storage: local filesystem under `excel_workspace/storage/`, ignored by Git.
- Database: SQLite file under the storage root by default.
- Workbook parsing: adapter-based reader that currently supports Open XML
  workbooks through `openpyxl` and legacy `.xls` workbooks through `xlrd`.
- Upload behavior: duplicate display names require explicit replacement.
- Version behavior: replacement creates a new version; the active version is
  switched only after parsing succeeds.
- Sheet export: each parsed sheet is written to raw CSV with a stable row ID
  prepended to every row.
- Row provenance: each row ID maps back to the original sheet and original row
  number.
- Preview behavior: a sheet can be previewed by row window; a row can be looked
  up by public row ID such as `S002_R13`.

### Non-Goals For This Module

- Do not store Excel assets in RAGFlow.
- Do not import or reuse frontend code from `D_ass`.
- Do not import backend code from `ragflow_integration_service`.
- Do not build standard comparison, clause extraction, chat, or RAG behavior
  inside `excel_workspace/`.
- Do not mutate uploaded source workbooks. All normalization must be written as
  derived artifacts.

### Target Architecture

The backend must keep the existing ports-and-adapters shape:

```text
api/          HTTP routes, request DTOs, response DTOs, error mapping
domain/       pure dataclasses, enums, no framework dependencies
application/  use cases: upload, versioning, preview, lookup, profiling
ports/        repository, storage, workbook-reader protocols
adapters/     SQLite, filesystem, workbook readers, future search/index stores
core/         config, IDs, time, expected application errors
```

Application services should depend on `ports/`, not concrete adapters. New
storage, parser, search, indexing, or database choices should be added as
adapters first, then wired in `api/dependencies.py`.

The frontend should remain a separate Vue application. It owns its API client,
types, screens, state, and styling. Shared code with other repository apps is
not allowed unless this module is later promoted into a shared package by an
explicit architecture decision.

### Data Model

The existing domain objects are the required base model:

- `ExcelFile`: logical file identity and display name.
- `ExcelFileVersion`: immutable uploaded version, hash, status, activation time,
  and failure message.
- `ExcelSheet`: parsed sheet metadata, generated sheet code, dimensions, and raw
  CSV path.
- `ExcelArtifact`: original workbook, raw CSV, profile JSON, row mapping CSV,
  and future derived artifacts.
- `ExcelRowMapping`: stable row ID to original row number and raw CSV row number.
- `WorkbookProfile`: workbook-level profile with per-sheet samples and candidate
  headers.

Rules to preserve:

- `file_id` is stable across replacements.
- `version_id` is new for every upload attempt.
- `sheet_id` is new per version and sheet.
- `sheet_code` is deterministic inside one version: `S001`, `S002`, etc.
- `row_id` is deterministic inside one sheet: `S001_R1`, `S001_R2`, etc.
- Public row IDs are readable but not globally unique. Use `version_id`,
  `sheet_id`, and `row_id` together for stable backend lookups.
- Failed versions must remain auditable but must not replace the active version.

### Storage Layout

Keep all runtime files under `excel_workspace/storage/` unless overridden with
environment variables:

```text
storage/
  excel-workspace.sqlite3
  files/
    {file_id}/
      {version_id}/
        original/{uploaded_filename}
        raw/{sheet_code}.csv
        mappings/row_mappings.csv
        profile/profile.json
```

Implementation notes:

- Original file names must be sanitized before being written to disk.
- CSV files must be written with UTF-8 with BOM (`utf-8-sig`) so Excel users can
  open Chinese text safely.
- Derived artifacts should be recreated from the original workbook whenever
  possible rather than hand-edited.
- Any future binary previews, thumbnails, search indexes, or normalized JSON
  exports should be stored as new `ExcelArtifactType` values instead of being
  mixed into the raw CSV files.

### Public API Plan

Existing endpoints:

```text
GET  /health
POST /api/excel/files/check-name
POST /api/excel/files
GET  /api/excel/files
GET  /api/excel/files/{file_id}
GET  /api/excel/files/{file_id}/versions
POST /api/excel/files/{file_id}/versions/{version_id}/activate
GET  /api/excel/versions/{version_id}/sheets
GET  /api/excel/sheets/{sheet_id}/preview
GET  /api/excel/sheets/{sheet_id}/rows/{row_id}
```

Near-term endpoints to add:

```text
GET  /api/excel/versions/{version_id}/profile
GET  /api/excel/versions/{version_id}/artifacts
GET  /api/excel/sheets/{sheet_id}/rows
GET  /api/excel/sheets/{sheet_id}/search
GET  /api/excel/files/{file_id}/active
DELETE /api/excel/files/{file_id}
POST /api/excel/files/{file_id}/restore
```

Endpoint behavior requirements:

- All expected application failures should return structured JSON with a
  user-readable `detail`.
- Duplicate-name uploads must return `409` with `requires_confirmation: true`.
- Invalid workbook uploads must return `400` and store a failed version record.
- Preview and search endpoints must cap row counts to prevent accidental very
  large responses.
- Any endpoint returning rows must include row IDs in the first column until a
  richer row DTO is introduced.
- API response DTOs in `backend/app/api/schemas.py` and frontend TypeScript
  types in `frontend/src/types/excel-assets.ts` must stay in sync.

### Workbook Parsing Plan

Supported formats:

- `.xlsx`, `.xlsm`, `.xltx`, `.xltm`: parse through `openpyxl`.
- `.xls`: parse through `xlrd`.

Parsing requirements:

- Preserve visible text, numbers, booleans, dates, and formula cached values.
- Convert date values to ISO strings (`YYYY-MM-DD` for date-only values).
- Convert datetimes to `YYYY-MM-DD HH:MM:SS`.
- Convert integer-like floats to integer strings.
- Preserve multiline text in CSV fields.
- Trim trailing empty rows and trailing empty cells so very wide workbooks do not
  create unusable CSV previews.
- Do not drop empty cells in the middle of a row.
- Keep parser failures wrapped in `InvalidExcelFileError`.

Future parser work:

- Add tests using small real fixture workbooks for `.xlsx` and `.xls`.
- Record workbook parser metadata in `profile.json`, including parser name,
  parser version when available, source extension, sheet count, and parse time.
- Add optional formula metadata if future workflows need formula auditing.
- Add a repair strategy for workbooks that third-party parsers cannot decode but
  desktop Excel can open.

### Backend Roadmap

#### Phase 1: Harden Current Upload And Preview

Tasks:

- Add integration tests that upload real `.xlsx` and `.xls` fixture workbooks.
- Add tests for duplicate upload, failed upload, replacement activation, and
  row lookup across versions.
- Add maximum upload size validation.
- Add file extension validation in the API route before processing.
- Add explicit profile endpoint.
- Add artifact listing endpoint.
- Add consistent pagination metadata to sheet preview responses.
- Add logging around upload start, parse success, parse failure, and activation.

Acceptance criteria:

- `pytest` passes for service, repository, reader, and API route tests.
- A legacy `.xls` workbook with Chinese text imports without conversion.
- A failed replacement does not change `active_version_id`.
- Raw CSV, mapping CSV, profile JSON, and original workbook are all present for
  a successful version.

#### Phase 2: Search And Row Discovery

Tasks:

- Add a simple SQLite-backed row search table populated from raw CSV.
- Index `version_id`, `sheet_id`, `row_id`, normalized row text, and selected
  header-derived fields.
- Implement `/api/excel/sheets/{sheet_id}/search`.
- Support exact match, case-insensitive contains, and optional column-limited
  search.
- Return row ID, original row number, sheet metadata, and matching row cells.
- Add frontend search controls inside the sheet preview view.

Acceptance criteria:

- Users can search for a standard code and jump to its row.
- Search results preserve row provenance.
- Search handles Chinese text and mixed English/Chinese rows.
- Large sheets can be searched without reading all CSV rows into the frontend.

#### Phase 3: Version Comparison

Tasks:

- Add version-to-version comparison at sheet and row level.
- Compare sheets by sheet name first, then fallback to sheet index.
- For each sheet, classify rows as added, removed, unchanged, or changed.
- For changed rows, report changed column indexes and old/new values.
- Add comparison artifacts as JSON files under the version storage directory.
- Add frontend version selector and comparison result view.

Acceptance criteria:

- Users can compare two versions of the same file.
- The comparison result links every changed row to row provenance.
- Large comparison results are paginated or artifact-backed.
- Failed comparisons do not affect active version state.

#### Phase 4: Review Workflow And Human Notes

Tasks:

- Add user notes tied to `file_id`, `version_id`, `sheet_id`, and optional
  `row_id`.
- Add review status fields for files and versions.
- Support row-level flags such as "needs confirmation", "verified", and
  "obsolete".
- Add API endpoints for notes and review status.
- Add frontend panels for version notes and row notes.

Acceptance criteria:

- Review notes survive version switches.
- Row notes can be exported with row provenance.
- Review state is visible in file and version lists.

#### Phase 5: Export And Downstream Integration

Tasks:

- Add exports for normalized CSV bundle, profile JSON, row mapping CSV, and
  search-ready JSONL.
- Add a controlled integration boundary for downstream tools to consume active
  version artifacts without importing application code.
- Add an artifact manifest per version.
- Add CLI scripts for batch import and export.

Acceptance criteria:

- Engineers can consume active Excel assets through files or HTTP without
  coupling to internal classes.
- Exported row IDs match API lookup behavior.
- The module can still run independently from the rest of the repository.

### Frontend Roadmap

Current screen responsibilities:

- Upload an Excel workbook.
- Confirm duplicate-name replacement.
- List files and versions.
- List sheets.
- Preview rows.
- Lookup and highlight a row by row ID.

Near-term frontend tasks:

- Add upload validation for supported extensions before sending files.
- Add visible upload progress and parse status.
- Add an empty state with clear next action.
- Add sheet search once the backend search endpoint exists.
- Add a profile summary panel showing sheet count, row counts, candidate header,
  and sample rows.
- Add version details, including hash, status, created time, activated time, and
  parse error message for failed versions.
- Add artifact download links once artifact listing is exposed.
- Add keyboard-friendly row lookup and search interactions.
- Add stable table dimensions and horizontal scrolling for wide sheets.

Frontend design requirements:

- Keep the UI operational and information-dense rather than marketing-oriented.
- Do not import `D_ass` components, composables, or styles.
- Keep API code in `frontend/src/api`.
- Keep shared response types in `frontend/src/types`.
- Treat backend error responses as user-facing status messages, not raw stack
  traces.

### Quality And Testing Plan

Backend checks:

macOS/Linux:

```bash
cd excel_workspace/backend
./.venv/bin/python -m ruff check app tests
./.venv/bin/python -m pytest
```

Windows PowerShell:

```powershell
Set-Location ".\excel_workspace\backend"
.\.venv\Scripts\python -m ruff check app tests
.\.venv\Scripts\python -m pytest
```

Frontend checks:

macOS/Linux:

```bash
cd excel_workspace/frontend
npm run build
```

Windows PowerShell:

```powershell
Set-Location ".\excel_workspace\frontend"
npm run build
```

Required test coverage:

- Workbook readers for `.xlsx` and `.xls`.
- Upload success path.
- Upload failure path.
- Duplicate file conflict.
- Replacement activation.
- Sheet preview pagination.
- Row lookup.
- Repository persistence across service instances.
- API error mapping.
- Frontend build and API type usage.

Manual validation checklist:

1. Start the backend on `127.0.0.1:8090`.
2. Start the frontend on `127.0.0.1:5174`.
3. Upload a workbook with multiple sheets.
4. Confirm file, version, sheet, and row counts.
5. Preview a sheet with Chinese and English text.
6. Lookup a known row ID such as `S002_R13`.
7. Upload the same display name again without replacement and confirm `409`.
8. Confirm replacement and verify a new version is created.
9. Force an invalid upload and verify the previous active version remains active.

### Configuration

Environment variables:

- `APP_NAME`: FastAPI app name.
- `APP_ENV`: deployment environment label.
- `APP_HOST`: default backend host.
- `APP_PORT`: default backend port.
- `APP_CORS_ORIGINS`: comma-separated frontend origins.
- `EXCEL_DATABASE_PATH`: optional absolute or user-expanded SQLite path.
- `EXCEL_STORAGE_ROOT`: optional absolute or user-expanded storage root.
- `EXCEL_PREVIEW_MAX_ROWS`: default preview row cap.

Rules:

- Local development can rely on default storage.
- Production-like deployments should set explicit database and storage paths.
- Secrets should not be required for this module until external integrations are
  added.

### Operational Notes

- `excel_workspace/storage/` is ignored by Git and may contain user data.
- Do not delete storage during normal development unless explicitly resetting
  local state.
- SQLite is acceptable for local and first internal use. If concurrent writes or
  multi-user deployment becomes important, add a repository adapter for a server
  database without changing application services.
- Keep migrations simple until the schema stabilizes. When schema changes become
  frequent, add a migration tool and document upgrade steps here.

### Handoff Notes For Future Engineers

When continuing development:

1. Read this README first, then `docs/architecture.md`,
   `docs/processing-pipeline.md`, and `docs/api-design.md`.
2. Keep changes inside `excel_workspace/` unless the task explicitly says to
   integrate with another module.
3. Add or update backend tests before changing parsing, versioning, repository,
   or storage behavior.
4. Keep frontend API types synchronized with backend schemas.
5. Run backend tests, backend lint, and frontend build before handing off.
6. Record any changed roadmap decisions in this section so the next engineer can
   pick up the work without reverse-engineering intent from code.
