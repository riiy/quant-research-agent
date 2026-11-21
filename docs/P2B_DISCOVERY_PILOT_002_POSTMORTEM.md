# P2B_DISCOVERY_PILOT_002 — terminal model proposal rejected by P2-A validation

Status: STOP_MODEL_OR_PROVENANCE_ERROR / FROZEN / ONE-SHOT USED / NO SCIENTIFIC PASS.

## User-reported host result (2026-11-21)

- Original local path: runtime/p2b/P2B_DISCOVERY_PILOT_002/result-8a2b5f3a4615.json
- User-reported result SHA256: 8a2b5f3a4615e0a223eeae2d47f1be2cf97c62367fb72d6e7c6f15f898ff3e60
- Status: STOP_MODEL_OR_PROVENANCE_ERROR
- Exception: ValueError: Model may not self-certify data availability
- network_requests=0, model_calls=1, experiments_executed=0
- The host artifact has not been uploaded or independently rehashed here. Do not infer the model's mechanism, exact dataset names or actual availability values from this summary alone.

## Root-cause boundary from committed code at main dc8fc58cd40ad97b9759f515d71aa4781899a70b

The P2B-002 runner first saves model-response.json, model-decision.json and model-usage.json, and on a PROPOSE decision saves its unchanged proposal under p2a-adapter/agent/proposal.json. It then calls the existing P2-A review function. P2-A validates protocol.data[].availability and permits only the two exact values UNVERIFIED and OPERATOR_VERIFICATION_REQUIRED. Any other availability string raises ValueError with the observed message. The top-level runner catches that exception and labels it STOP_MODEL_OR_PROVENANCE_ERROR. Thus the response successfully reached the deterministic gate; this is NOT another HTTP gateway/model routing failure.

A contract ambiguity exists: the original P2-B model prompt forbids fabricating data availability but does not explicitly spell out the two allowed enumeration values; the response JSON schema leaves availability as unrestricted string. Thus the failure is consistent with an under-specified producer/consumer contract. It does not prove the candidate asserted independently verified data, because the exact generated string has not been read. It also does not prove the economic hypothesis is sound.

## Scientific status and safe next step

- The model produced a structurally parsed PROPOSE candidate, but its protocol did not pass P2-A validation. It is NOT P2B_PASS_PROTOCOL_DISCOVERY and not an alpha result.
- The original approved P2B-002 model request is consumed. Keep its attempt.claim, model-request.json, raw response/decision/usage files, copied source evidence, terminal result and hashes unchanged; no repeat under the same ID, schema rewriting, synthetic acceptance or extra gateway calls.
- Only read the already stored model-decision.json and P2-A adapter proposal OFFLINE. Determine the exact value of each data availability entry, identify named providers, assess mechanism novelty/source relevance and cheapest falsifier. The gate could have further rejections after this first error, so an isolated edit to availability cannot be assumed to yield a pass.
- If the proposal is economically old, poorly grounded or lacks a feasible observable predictor, archive and STOP; do not authorize P2B-003 for the sake of green status.
- If it has a credible new economic mechanism, human review can document this as a candidate **without changing the archived model output**. A new protocol run or future schema alignment (enumerated availability + explicit prompt, structured validation outcome instead of generic exception) is a distinct, separately reviewed and approved change, not permitted by this closed attempt.
- No trading, simulation, account-order generation, backtesting, arbitrary generated research code or sealed holdout access.

## Offline read-only user artifact request

For scientific assessment, obtain the locally archived P2B-002 model-decision.json and relevant evidence excerpts, not a second model call. Do not share any secret environment values, bearer credentials or authorization logs. All claims about economic mechanism, dataset feasibility and source fit remain UNKNOWN until those original artifacts are examined.
