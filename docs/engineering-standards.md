# Engineering Standards

## Architecture Boundaries

- Keep route handlers thin. HTTP routes translate request/response DTOs and delegate business behavior to application services.
- Keep application services independent of concrete infrastructure. They depend on ports/protocols and domain models.
- Keep persistence in repository adapters. SQL and migration logic belong in `backend/app/adapters/repositories/`.
- Keep frontend API calls in `frontend/src/api/`, shared shapes in `frontend/src/types/`, and UI state inside the component that owns the workflow.

## Persistence Rules

- SQLite is the source of truth for workbook metadata, summaries, chat sessions, chat turns, citation snapshots, attached documents, and workspace model preferences.
- Persist user-visible history as immutable turn snapshots. A chat turn must keep its question, answer blocks, selected documents, attached document snapshot, citations, warnings, timings, and creation time together.
- Preserve historical evidence snapshots even if the underlying workbook is later deleted. Future attachments may be removed, but past chat answers must remain readable and internally consistent.
- Add schema changes through ordered migrations only. Do not edit already-applied migration text; add a new migration version.
- Use JSON columns only for bounded nested snapshots owned by a single aggregate, such as a chat turn's citations or timings.

## State Consistency

- Use stable IDs as correlation keys: `session_id`, `turn_id`, `file_id`, `version_id`, `sheet_id`, `row_id`, and `evidence_id`.
- Avoid relying on frontend memory for durable state. Refreshing the page or switching sessions must reload persisted state from the backend.
- Protect async UI loading from stale responses. A later session selection must not be overwritten by an earlier request finishing late.
- Validate model/provider combinations before saving preferences or sending model requests.

## Frontend UI

- Reuse existing visual language before adding new patterns: white cards, subtle borders, compact section headers, restrained shadows, and stable grid dimensions.
- Keep file-management inspection surfaces visually aligned: Summary, Data Preview, and Schema should use the same card density, header treatment, metrics, and list row styling.
- Keep controls explicit and close to the data they affect. Provider/model selectors save workspace preferences; chat history loads by active session.
- Avoid global CSS changes when a narrower file-workspace override can satisfy the request.

## Testing And Verification

- Backend persistence changes require repository/API tests for migration, write, read, and compatibility behavior.
- Chat changes must test both real-time answer responses and history reload responses.
- Frontend changes must pass `vue-tsc` and production build checks.
- After each completed task round, restart backend and frontend dev servers so the latest behavior is available for manual inspection.
