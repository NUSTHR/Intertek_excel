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

## Frontend Boundary

The frontend is a separate Vue/Vite app. It owns its API client, types, and UI
state. It does not use `D_ass/src/lib`, `D_ass/src/composables`, or legacy
RAGFlow types.

## Versioning Rule

Replacing a file creates a new version. Old versions remain stored. The active
version is switched only after the new version has been parsed successfully.
Processing failure must not affect the previous active version.
