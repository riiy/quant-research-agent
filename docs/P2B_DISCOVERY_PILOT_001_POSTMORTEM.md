# P2B_DISCOVERY_PILOT_001 — first real attempt, terminal HTTP 400

Status: **STOP_MODEL_OR_PROVENANCE_ERROR / FROZEN / NO RE-RUN AUTHORIZED**.

## Evidence (owner-supplied, 2026-11-21)

- Local artifact: `runtime/p2b/P2B_DISCOVERY_PILOT_001/result-bf07acbb0d83.json`
- User-reported result full SHA256: `bf07acbb0d831fa4893209eee3bb00073e52debf1c1b33ac6ad13cfe9e98e66e`
- `status=STOP_MODEL_OR_PROVENANCE_ERROR`, `reason_type=HTTPError`, `reason="HTTP Error 400: Bad Request"`.
- `network_requests=4` (source requests counted by the runner; do **not** misread as four papers), `model_calls=1` (an **attempt**, not verified successful inference/billing), `experiments_executed=0`.
- These artifacts are on the owner's host, not in GitHub. Their bytes and the full original source selection/model payload have not been independently inspected here. The full SHA is owner-supplied, not independently recomputed.

## Where it stopped (confirmed from merged implementation at main 9bcaa35ff3b0f9580047409b2e85daf21c188cdc)

- `run()` only sends a model request after at least one source abstract has been verified and its adapter evidence stored. At least one verified abstract therefore **must have been available** to reach this point; exact DOI count and relevance are not established by this result JSON.
- `prepare_request()` sends a fixed strict JSON schema in `text.format`, `reasoning.effort=low`, `store=false`, `tools=[]`, and the local gateway model alias. A POST with `HTTP 400` was attempted.
- `_model_get()` does **not** read the `HTTPError` response body. The result JSON only captures exception type/string, so the provider-specific reason is **unknown**. It is not evidence that the economic hypothesis was wrong, that the model reasoned and abstained, or that the gateway charged for an inference.

## Frozen decision

1. **Do not retry**: the one-attempt gate and one model call are used. Preserve `attempt.claim`, source-selection, raw DOI evidence, model-request, outbound-claims log, and the terminal result unchanged. Do not delete/rename files, remove the claim marker, change the model, or reuse this experiment ID.
2. **No alpha/science result**: `P2B_PASS_PROTOCOL_DISCOVERY=NOT_MET`; `NO_NEW_FEASIBLE_MECHANISM` is **not** established; there were no backtests, account simulations, trades or sealed-holdout access.
3. **Minimum offline diagnosis**: inspect only `model-request.json` metadata and `outbound-claims.jsonl`, and query **already retained** gateway-side HTTP 400 logs (error JSON, request ID, received model/route, and timestamp) without another request. Redact tokens, authorization headers, personal metadata and full paper abstracts before sharing. If no gateway error body/log exists, classify exact cause as `UNDETERMINED`.
4. Common *possibilities*, not proven root causes: gateway model-alias routing, unsupported `reasoning.effort`, unsupported `text.format.json_schema` or strict schema features, or another provider validation error. No speculative code edits should be treated as a fix.
5. A different real run requires a **new** preregistered ID, specific owner approval, fresh single-use budget and code review. Do not authorize one until an existing HTTP 400 error log or equally strong existing gateway evidence identifies an actionable incompatibility.

**Recommended stop condition:** if the existing logs cannot identify the bad request field, archive this as an interface compatibility failure and stop P2-B interface work. Do not pay for a broad sequence of probing requests to reverse-engineer the gateway. No changes to P0/P1, trading flags or research-code execution.
