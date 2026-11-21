# P2B_DISCOVERY_PILOT_002 — owner-approved one-call replay

Status: OWNER APPROVED EXPERIMENT SCOPE, IMPLEMENTATION PR PENDING, NOT RUN.

## Frozen evidence and mechanism test

P2B-001 ended with model HTTP 400 because it sent the invalid LiteLLM alias chatgpt/gpt6.2-sol. Owner-supplied proxy YAML lists the intended route chatgpt/gpt-6.2-sol. Original terminal report SHA256: bf07acbb0d831fa4893209eee3bb00073e52debf1c1b33ac6ad13cfe9e98e66e.

P2B-002 is a distinct, separately owner-approved experiment. It makes ZERO new Crossref/OpenAlex requests and no research-code, simulation, trading, tickets or sealed-holdout access. It reuses the exact previous literature and model prompt, with only two controlled changes to the old model request: the model alias is corrected to chatgpt/gpt-6.2-sol, and the embedded experiment ID becomes P2B_DISCOVERY_PILOT_002. No extra human-picked source, changed mechanism seed, paper replacement, extra inference calls, prompt tuning or retry.

## Offline evidence verification before any model request

Command after installing the new version: quant-p2b-replay --home runtime approval-template.

The reader requires the frozen original terminal result full SHA, original attempt.claim, original raw Crossref search and selected DOI list, ordered DOI/title/publication-date agreement, unique content-addressed P2B_EVIDENCE_ADAPTER_V1 report, DOI-verified raw Crossref/OpenAlex response SHA and reconstructed abstract SHA. It regenerates the original one-shot model request from that trusted evidence and requires exact byte equality with archived P2B-001 model-request.json. Tampering or source loss stops before any external model request. P2B-001 files are never written. The new adapter copies verified source bytes into the separate P2B-002 output tree for P2-A to review.

The approval template binds exact evidence fingerprints (original report, source selection, raw search, old model request, DOI lists), code SHA256, replay model request SHA256, instruction SHA, gateway endpoint/model/user agent and the new ID. Never copy the old approval file. Regenerate after each reviewed code version.

## Strict one-call budget and manual approval

- Model alias: chatgpt/gpt-6.2-sol, with operator-configured HTTPS BASE_URL ending /v1, LLM_API_STYLE=responses, LLM_API_KEY set, no endpoint fallback or redirects.
- Source HTTP requests: 0. Model requests: <=1. No retry even if proxy responds HTTP 400 or network timeout.
- Full JSON request body <=12,000 UTF-8 bytes; max_output_tokens=4,500. Preserved original strict JSON schema, reasoning setting and zero tools.
- Owner-attested input/output gateway parity with OpenAI GPT-6.2 Sol Standard pricing: USD 2 / USD 10 per million tokens; calculated upper request-model token charge <=USD 0.075 under 1.25x full-input premium. Maximum authorized experiment spend: USD 10. Actual gateway billing is not independently observed and must be checked by the operator.
- Independent local owner-approval JSON required at runtime/p2b/P2B_DISCOVERY_PILOT_002/owner-approval.json. Fields approved=true, unique approval_reference, approved_at_utc and pricing_verified_at_utc no older than 24 UTC hours, nonplaceholder pricing_reference, exact model and endpoint, fresh code/evidence/request hashes, all trading/execution permissions false and budget unchanged.
- The runner durably creates runtime/p2b/P2B_DISCOVERY_PILOT_002/attempt.claim before any external call. A failed call consumes the one-shot allowance. Do not delete the claim or modify P2B-001 to rerun.

## Decision criteria

AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW: real model proposal passed the offline P2-A gate to review stage; NOT evidence of novelty or positive alpha.
NO_NEW_FEASIBLE_MECHANISM: model abstained or P2-A rejected an old/infeasible mechanism; a documented negative result, not acceptance.
STOP_MODEL_OR_PROVENANCE_ERROR: one-shot attempt failed, archive and stop.
STOP_P2B_002_PRECHECK: local evidence, approval or budget mismatch; no model/network call.
Only an independent human reviewing source/predictor/target scope, mechanism novelty against archived channels, point-in-time data, cheapest falsifier, baseline, out-of-sample, costs and leakage can grant scientific protocol discovery. No research experiment is authorized by a candidate protocol.

## Operator actions, after explicit review and merge of implementation PR

1. Preserve original runtime/p2b/P2B_DISCOVERY_PILOT_001/ unchanged including attempt.claim and source artifacts.
2. Set local LLM_MODEL=chatgpt/gpt-6.2-sol and existing BASE_URL, LLM_API_STYLE=responses, LLM_API_KEY without committing secrets. Model-list configuration alone does not prove active proxy/key routing; inspect existing proxy records if necessary, not a new smoke call.
3. Run quant-p2b-replay --home runtime approval-template (local evidence verification, zero HTTP calls) and review frozen DOIs and checksums. Complete the new P2B-002 local approval document.
4. Manually invoke quant-p2b-replay --home runtime run at most ONCE. Keep output JSON, request/response, P2-A report and checksum intact. Do not retry on any failure.

No P0/P1 service, existing strategy, account permissions or scientific conclusion changes as part of this PR.
