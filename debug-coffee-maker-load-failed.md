# [OPEN] Debug Session: coffee-maker-load-failed

## Problem

- Symptom: asking "coffee maker适用的所有标准" ends up showing `load failed`.
- Goal: reproduce the full upload -> summary -> chat chain with a non-confidential workbook, identify the failing stage, and then apply a minimal fix based on runtime evidence.

## Initial Hypotheses

1. The frontend `load failed` comes from the summary or chat HTTP request timing out before the model returns.
2. The router or answer model call fails because the uploaded workbook has not generated a valid summary, so chat has no routable document context.
3. The running backend returns a server error during chat because the LLM response is malformed or not valid JSON for one of the stages.
4. The failure is caused by the current frontend flow, while the backend chain itself still works through direct API calls.
5. The uploaded workbook content or size causes the answer stage to exceed current model/runtime limits, and the UI reduces that to a generic `load failed`.

## Evidence Plan

- Start from a clean manual chain with a non-confidential sample workbook.
- Upload the workbook through the live backend.
- Generate summary, create session, run route and answer APIs separately.
- Compare API behavior with the frontend symptom and inspect runtime logs from the failing stage.

## Evidence Collected

- Manual upload of `/private/tmp/sanitized_chain_test_20260605.xlsx` succeeded.
- Summary generation succeeded with `HTTP 200`, but took `57.8s`.
- Session creation succeeded with `HTTP 200`.
- Route succeeded with `HTTP 200` in `7.35s`, but selected three active documents:
  - the sanitized test workbook (`6` rows)
  - `Copy of 6. 欧标-标准版本升级表_副本.xls` (`963` rows)
  - `4. HA-Price list - 数据for AI.xlsx` (`596` rows)
- Answer succeeded both through the backend directly and through the frontend Vite proxy:
  - direct backend call: `141.4s`
  - frontend proxy call: `81.1s`
- The answer quality is degraded because unrelated active files are included; citations and claims are pulled from unrelated documents instead of staying focused on the sanitized workbook.

## Hypothesis Status

1. Frontend request timeout before the model returns: not confirmed in this reproduction.
2. Summary missing causes routing failure: rejected.
3. LLM stage returns malformed JSON or backend 500: rejected in this reproduction.
4. Backend chain works but frontend path fails: not reproduced; proxy call also succeeded.
5. Large active-document scope causes unstable/slow answer stage: confirmed.

## Current Conclusion

- The exact `load failed` symptom was not reproduced during this manual run.
- The dominant runtime risk is that chat currently routes across all active summaries, which attached two unrelated large workbooks and pushed the answer stage into long, variable runtimes.
- This same condition is a plausible trigger for intermittent browser-side fetch failures or generic `Load failed` errors, especially when model latency varies upward.
