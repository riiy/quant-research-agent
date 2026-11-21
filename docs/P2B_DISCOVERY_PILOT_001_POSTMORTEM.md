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
- `_model_get()` does **not** read the `HTTPError` response body. The result JSON only captures exception type/string; the provider-specific reason was subsequently recovered from an already-existing LiteLLM Proxy error log (see below). It is not evidence that the economic hypothesis was wrong, that the model reasoned and abstained, or that the gateway charged for an inference.

## Frozen decision

1. **Do not retry**: the one-attempt gate and one model call are used. Preserve `attempt.claim`, source-selection, raw DOI evidence, model-request, outbound-claims log, and the terminal result unchanged. Do not delete/rename files, remove the claim marker, change the model, or reuse this experiment ID.
2. **No alpha/science result**: `P2B_PASS_PROTOCOL_DISCOVERY=NOT_MET`; `NO_NEW_FEASIBLE_MECHANISM` is **not** established; there were no backtests, account simulations, trades or sealed-holdout access.
3. **Resolved root cause from existing gateway logs**: LiteLLM Proxy rejected the request with HTTP 400 and the error text: `/responses: Invalid model name passed in model=chatgpt/gpt6.2-sol.` The owner reports the available route is `chatgpt/gpt6.1-sol` (note the different version AND punctuation). The rejected model alias is the concrete cause of this HTTP 400; there is no basis to blame the JSON Schema or reasoning parameters.
4. **Remaining unknowns**: the first approved request never produced a mechanism proposal. Actual gateway billing for this rejected attempt and the compatibility of the reported `chatgpt/gpt6.1-sol` with the exact structured Responses payload are not independently established.
5. **Potential next pilot, not authorized**: register a new `P2B_DISCOVERY_PILOT_002` with a separate single-call budget and explicit owner-approved `chatgpt/gpt6.1-sol` model and pricing. Prefer reusing the already archived verified DOI evidence, subject to hash/DOI revalidation and predeclared no-cherry-pick selection, instead of new Crossref queries. Implement and review an offline evidence-replay adapter with no backtests or code execution only if the owner requests another pilot. No permission to reuse `P2B_DISCOVERY_PILOT_001` or clear its claim.

**Recommended stop condition:** if the existing logs cannot identify the bad request field, archive this as an interface compatibility failure and stop P2-B interface work. Do not pay for a broad sequence of probing requests to reverse-engineer the gateway. No changes to P0/P1, trading flags or research-code execution.


## Root-cause update from the owner's existing LiteLLM Proxy log (2026-11-21)

The user supplied a LiteLLM HTTP 400 error log that explicitly says `/responses: Invalid model name passed in model=chatgpt/gpt6.2-sol`. They confirmed their actual offered gateway alias is `chatgpt/gpt6.1-sol`. **Root cause established: unavailable gateway model route**, rather than unidentified JSON-schema incompatibility. The first pilot remains frozen.

The earlier owner assertion that `chatgpt/gpt6.2-sol` was the available route is superseded by this newer evidence. Do not mutate the historical approved request to pretend it used GPT-6.1; retain both for auditability. The scientific question is still untested. Any replacement trial requires a separate ID, scope/budget/code approval and owner review.
