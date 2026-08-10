# Cross-domain file workspace

This package owns presentation contracts and reusable Vue components shared by
the Excel and PDF file-management surfaces. A feature adapts its domain record
to a shared view model; the shared package never imports feature entities or
API clients.

## Boundaries

- `components/`: domain-neutral UI primitives.
- `composables/`: presentation state with deterministic cleanup.
- `*-contract.ts`: stable view models and emitted-event contracts.
- `copy.ts`: common interface vocabulary and domain-noun templates.
- `features/*`: domain adapters, API calls, selection policy and persistence.

Similar operations must render the same component. Domain differences are
expressed through view-model fields, capability-driven rendering and slots—not
copied markup or feature-specific structural CSS.

## State rules

1. File-list precedence is initial loading, fatal error, search/empty state,
   then ready content. Refresh and mutation errors do not discard cached rows.
2. Selection is owned by the feature composable. Shared rows emit intent and
   never cache a second selection state.
3. Pagination uses `FILE_WORKSPACE_PAGE_SIZE` and always exposes a range label.
4. Async persistence ignores stale responses using a monotonic revision or a
   per-resource mutation chain.
5. Unsupported actions are omitted. Disabled controls are reserved for
   temporarily unavailable operations.
6. Dialogs receive presentation-only targets (`id`, `displayName`, `kindLabel`)
   and must not retain domain records.

## Verification

The project uses the Node test runner (`npm run test`), `vue-tsc` and the Vite
production build. Shared contract tests live in `frontend/tests/`; runtime
changes also require browser checks at desktop and compact breakpoints.
