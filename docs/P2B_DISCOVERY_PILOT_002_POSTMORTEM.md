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

## Independent scientific review of the archived model-decision (owner supplied 2026-11-21)

The owner pasted the actual P2B-002 `model-decision.json` content (not the original file bytes) into the conversation. It has `decision=PROPOSE`, DOI `10.1002/fut.70089`, `mechanism_id=perp_clock_phase_spot_adjustment`, and `execution_authorized=false`. One data record uses the exact `availability` prose:

> Required local inputs are not confirmed. Stop unless complete spot and USD-M perpetual top-of-book histories and a common capture-time field are already on disk and readable with existing tools.

This is **cautious, not model self-certification**. The deterministic P2-A gate requires the literal enum `UNVERIFIED` or `OPERATOR_VERIFICATION_REQUIRED`, while the original response schema accepted arbitrary strings. Classification: **producer/consumer enum-contract validation failure**, not evidence of invented confirmed data. Preserve the historical failure, model response and exact string; do not patch the archived output.

### Source-fit and novelty assessment

Article: Andrei Shynkevich (2026), *Trading Periodicity and Algorithmic Divide in Cryptocurrency Markets*, Journal of Futures Markets 46(5), pp. 904–930, DOI 10.1002/fut.70089. Publisher abstract: https://onlinelibrary.wiley.com/doi/10.1002/fut.70089. The three proposed quotations are present in the publisher abstract. Abstract supports subsecond periodicity and price discovery around algorithmic liquidity-taking episodes in cryptocurrency spot/perpetual markets. It does NOT directly establish a particular one-second cycle, 100-ms phase, a 200-ms **perpetual-to-spot** lead, reliable signed taker identity from quote changes, or a tradable after-cost effect.

Proposed mechanism: one recurring high-perpetual-quote-change 100-ms bin per 1-s UTC cycle, fixed from Jan–Mar 2024, predicts larger same-direction Binance BTCUSDT spot midpoint response over next 200 ms than a +500-ms comparator bin; retrospective Apr–Jun 2024 evaluation. Its conditional cross-market transfer mechanism is economically more distinct than the archived unconditional weekday/funding/trend/reversal channels, **but novelty and causality remain provisional**. Quote-change intensity is not aggressor-side trade intent, and synchronized spot/perp receive timestamps can create false price leadership if feed latency, batching, or out-of-order delivery differ.

The proposed design includes a calibrated phase freeze, comparable-move baseline, mirrored negative-time diagnostic, no 2025 holdout, day-clustered CI, >=30 evaluation days and explicit stop conditions. It remains a retrospective test with unverified clock/measurement assumptions; its 1-s cycle and 200-ms horizon are hypotheses extrapolated from the paper, not confirmed paper parameters. Passing a positive coefficient would not show realizable trading alpha or net-cost profits.

### Feasibility kill test — before any code or new data work

**Highest-risk data dependency:** complete pre-existing Jan–Jun 2024 **both spot and USD-M BTCUSDT append-only BBO update streams** with original common-clock receiver timestamps and gap checks. A current/live endpoint, regular OHLCV, historical trades alone, post-hoc snapshots or file modification times do not meet the stated protocol.

Independent public archive warning: Binance public-data issue #334 (https://github.com/binance/binance-public-data/issues/334, opened May 13, 2024) reports USD-M `bookTicker` missing from Apr 1, 2024 onward, overlapping the **entire start of proposed evaluation**. The public archive therefore must not be assumed to fill gaps; this issue does not prove the owner has no suitable separate local recorder.

**Recommended action:** one read-only local inventory (at most 10–15 minutes) of any already collected 2024 spot/perp BBO source, capture clock provenance and available date range. If either venue, common-clock receive timestamps, or >=30 qualifying untouched evaluation UTC days is absent, immediately archive `perp_clock_phase_spot_adjustment` as `BLOCKED_DATA_NOT_AVAILABLE` and **STOP**. Do not purchase data, reconstruct millisecond books, deploy a recorder, change 2024 dates or run a backtest. If data clearly exists, request a separate human authorization for a narrow preregistered scientific method review; this already-closed P2B-002 does not authorize test execution.

**Scientific disposition now:** `ECONOMICALLY_DISTINCT_CANDIDATE / SOURCE_ABSTRACT_GROUNDED / DATA_UNVERIFIED / NOT_ACTIONABLE / P2B_PASS_NOT_MET`. The model produced a plausible idea, but no independently accepted feasible protocol, no strategy result and no alpha. A schema-only repair must not trigger another model call or hide the economics/data blocker.
