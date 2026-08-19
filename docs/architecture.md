# Excel Workspace Architecture

Excel Workspace is designed as a standalone product domain inside the current
repository. The directory can be split into a new repository without carrying
RAGFlow code or the existing frontend application.

## Goals

- Manage Excel files as versioned assets.
- Preserve original Excel files as evidence.
- Export each sheet to raw CSV with stable row identifiers.
- Store row-level provenance for future citation and highlighting.
- Keep the backend and frontend isolated from legacy RAGFlow code.

## Backend Layers

```text
api/          HTTP routes and DTOs
domain/       pure dataclasses and enums
application/  upload, versioning, preview, lookup use cases
ports/        repository, storage, workbook reader interfaces
adapters/     SQLite, filesystem, openpyxl implementations
core/         configuration, IDs, errors, time helpers
```

`application/` depends on `ports/`, not on concrete infrastructure. This keeps
storage, database, and workbook parsing replaceable.

PDF knowledge application behavior is split by use case while retaining
`PdfKnowledgeService` as a compatibility facade for the API and background
workers:

```text
pdf_knowledge/
  library_service.py   file access, metadata mutation, visibility, and inspection
  upload_service.py    upload, reparse, retry, cancellation, and batch lifecycle
  parsing_service.py   parser execution, indexing, diagnostics, and recovery
  summary_service.py   summary generation and durable summary-task lifecycle
  settings_service.py  persisted PDF provider/model settings
  parser_profiles.py   configured parser registry and active-profile selection
  service.py           compatibility facade and application-service composition
```

The PDF HTTP surface follows the same feature boundary. The legacy
`api/routes/pdf_knowledge.py` module remains as a compatibility import, while
the router implementation is composed from:

```text
api/routes/pdf/
  files.py         library files, metadata, detail, and chunks
  uploads.py       upload tasks and upload batches
  parsing.py       parser status, profile selection, and reparse
  summaries.py     summary tasks and summary generation
  chat.py          PDF chat and chat-session lifecycle
  settings.py      PDF model settings
  mappers.py       domain-to-API response mapping
  dependencies.py shared authenticated service dependencies
```

All subrouters are mounted below the existing `/api/pdf` prefix. Route paths,
status codes, request models, response models, and permission dependencies are
treated as compatibility contracts during refactoring.

PDF document selection follows
[`ADR 0001`](adr/0001-pdf-document-routing-authority.md). Multi-document
candidates are selected only by the PDF document router. Application code owns
the hard visible/READY scope and validates router output. Up to four router
candidates pass through unchanged. Larger candidate sets are retrieved and
reranked in full, then reduced to four; retrieval cannot introduce a document
outside the router result. The answer stage receives every parsed chunk of the
four final documents. A configured hard capacity is checked before the answer
request; overflow fails closed instead of truncating a selected document.

Vector projections are derived state. SQLite owns a monotonic per-file
generation and a tombstone flag, while Qdrant points carry the same generation.
Searches always filter by the current READY generation and delete tasks may
remove only generations at or below their own fence. Vector tasks use the
explicit lifecycle `pending -> running -> retry_wait -> succeeded`, with
`dead_letter` and `cancelled` as terminal alternatives. A periodic reconciler
backfills missing or stale projections but deliberately leaves matching dead
letters for an auditable manual requeue.

Projection production has an independent release state from online ranking.
`PDF_VECTOR_INDEXING_ENABLED=true` with ranking disabled is the supported
shadow-backfill state. Ranking cannot be enabled unless indexing is enabled.
When ranking is active, an unavailable model, missing collection, stale index,
or incomplete reranker response fails closed; it never reduces the router
result by accident. Four-or-fewer candidate requests do not touch any vector
dependency and remain available during a Qdrant or model-provider outage.

SiliconFlow supplies embedding and reranking inference over HTTPS. The local
Qdrant service is accessed over loopback REST and persists only derived data in
a dedicated Docker volume. Development may bootstrap its collection
automatically. Production runtime is validate-only: collection creation and
payload-index creation happen through the deployment preflight command. SQLite
READY state combined with a missing collection is treated as data loss and
requires an explicit full rebuild.

API DTOs follow the same bounded-context rule:

```text
api/schema_models/
  common.py       cross-feature chat-session request and response models
  pdf.py          PDF library, parsing, retrieval, summary, and chat models
api/schemas.py    compatibility exports plus the remaining Excel/auth models
```

Feature routers import their bounded-context schema module directly. Existing
imports from `app.api.schemas` remain valid through explicit compatibility
exports; schema class names and generated OpenAPI components are contract
boundaries.

## Dialogue Workflow

Chat orchestration is isolated behind `ports/chat_workflow.py`. The production
dependency graph injects `adapters/dialogue/langgraph_chat_workflow.py`, which
uses LangGraph to run the full `route -> answer` chain while preserving the
existing HTTP API and the standalone route/answer endpoints.

The workflow layer coordinates stages only. Excel loading, document attachment,
LLM calls, citation verification, and session persistence remain in the
application service and existing adapters.

## Frontend Boundary

The frontend is a separate Vue/Vite app. It owns its API client, types, and UI
state. It does not use `D_ass/src/lib`, `D_ass/src/composables`, or legacy
RAGFlow types.

## Versioning Rule

Replacing a file creates a new version. Old versions remain stored. The active
version is switched only after the new version has been parsed successfully.
Processing failure must not affect the previous active version.
