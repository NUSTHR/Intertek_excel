# [OPEN] Debug Session: delete-api

## Problem

- Symptom: delete API is reported as unusable.
- Example target: `sanitized_chain_test_20260605.xlsx`.
- Goal: reproduce the failure, collect runtime evidence, identify the root cause, and then apply a minimal fix if needed.

## Initial Hypotheses

1. The frontend is calling the delete API with the wrong file identifier or stale state after list refresh.
2. The backend delete route is returning a confirmation or validation response that the frontend does not handle as expected.
3. The target workbook is not represented by the display name the user expects, so the attempted deletion is hitting a different record or no record at all.
4. The backend delete flow fails while cleaning related rows or filesystem artifacts for files that have summaries or chat-session attachments.
5. The running backend instance is not using the latest code, causing the UI to hit an older server without the delete endpoint behavior we added.

## Evidence Plan

- Inspect current persisted file records to locate the target workbook.
- Reproduce deletion through HTTP against the running backend.
- Capture backend runtime behavior around delete request, confirmation branch, and cascade cleanup.
- Compare observed response with frontend expectations.

## Evidence Collected

- The target workbook exists in the active SQLite database as:
  - `display_name = sanitized_chain_test_20260605.xlsx`
  - `file_id = file_966ba71868344e8aafb57b8b215be4c5`
- Hitting the currently used backend on `127.0.0.1:8090` returns:
  - `DELETE /api/excel/files/{file_id}` -> `405 Method Not Allowed`
  - `Allow: GET`
- OpenAPI comparison:
  - `8090` exposes `/api/excel/files/{file_id}` with only `get`
  - `8091` exposes `/api/excel/files/{file_id}` with `get` and `delete`
- Running the current code on `127.0.0.1:8091` proves the new delete route works:
  - without confirmation -> `409` with `requires_confirmation = true`
  - with `confirm_delete=true` -> `200 OK`

## Hypothesis Status

1. Frontend is sending the wrong file ID: rejected.
2. Backend confirmation response is malformed: rejected for current code on `8091`.
3. Target workbook mapping is wrong: rejected.
4. Cascade cleanup fails for this workbook: rejected in the current code path on `8091`.
5. Running backend instance is outdated: confirmed.

## Root Cause

- The backend instance serving `127.0.0.1:8090` has not been restarted with the latest code, so it does not include the new `DELETE /api/excel/files/{file_id}` route.
