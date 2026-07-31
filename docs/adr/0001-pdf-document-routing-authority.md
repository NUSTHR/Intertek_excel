# ADR 0001: PDF Document Routing Authority

## Status

Accepted.

## Context

PDF chat supports three user scopes:

- one selected PDF;
- one or more selected file or folder nodes;
- all PDF sources.

The scope is a hard authorization and availability boundary. Document routing is
the only component allowed to choose documents from a multi-document candidate
set. Chunk budgeting and answer construction happen only after document
selection and must not add documents.

## Decision

1. A PDF candidate must be active, visible to the current user, and in READY
   processing state.
2. A selected PDF resolves only to itself.
3. A selected folder resolves only to visible READY PDF descendants.
4. All PDF sources resolves to every visible READY PDF available to the current
   user.
5. Zero candidates produce an empty routing decision.
6. One candidate skips the document router and selects that candidate directly.
7. Two or more candidates must be passed to the PDF document router.
8. The router may select at most nine documents for one turn.
9. Router output is validated against the hard candidate set. Unknown,
   inaccessible, non-READY, hidden, deleted, and out-of-scope IDs are discarded.
10. Duplicate-content fingerprints are router metadata only. They must not be
    used by application code to remove candidates before routing or to rewrite a
    router decision afterwards.
11. Previous turns and prior attachments may help the router resolve a
    follow-up, but they never broaden the current hard scope.
12. Context allocation may truncate chunks from selected documents. It must
    never select a new document.

## Consequences

- Multi-document selection remains explainable through one authoritative
  document router.
- Folder and file permissions remain deterministic application rules.
- A request for all documents can still be limited by the nine-document policy;
  the API must expose incomplete coverage instead of claiming full coverage.
- Future batching or catalog caching is allowed only when every document choice
  is still made by the PDF router.

## Compatibility

The public PDF chat paths remain under `/api/pdf`. The removed
`/api/pdf/retrieval/search` endpoint is not part of the supported contract.
