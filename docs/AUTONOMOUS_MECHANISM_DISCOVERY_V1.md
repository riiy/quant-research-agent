# AUTONOMOUS_MECHANISM_DISCOVERY_V1 — P2-A offline gate (PR proposal)

## Decision, scope and evidence

P2 is **not accepted** yet. Current implementation tests the trust boundary *after* an external mechanism-proposal JSON exists. It does **not** generate that JSON, call an LLM, discover a new DOI, prove novelty, run research code, change the P0/P1 controller, or touch the sealed holdout. The offline synthetic inventory-capacity example is **not** a validated or deliberately selected real scientific discovery.

This separation is intentional: no new model provider/API/budget, wider search query, unreviewed code executor or market dataset has been approved. Passing Python tests is not genuine autonomous inference from unseen external sources.

## Input and proof

Run offline using an already archived P1 DOI-enrichment report and separately produced **untrusted** model-proposal JSON. Source reports must be under runtime/agent/reports/abstract-evidence-v1-<hash>.json. The gate verifies the report digest, provider's DOI-matched raw JSON, SHA256, abstract digest and title consistency. Missing or tampered artifacts block review. Only P1's Crossref/OpenAlex provider responses are accepted. No network requests.

The contract is defined by exact nested field sets in src/quant_research_agent/mechanism_discovery.py:

| Object | Fields |
| --- | --- |
| Root | schema_version=1, doi, mechanism_id, mechanism, source_quotes, novelty, protocol, execution_authorized=false |
| mechanism | name, family, actors, friction_or_incentive, causal_chain, conditions, why_not_indicator, counterevidence |
| source_quotes | 1–3 items with quote, interpretation; quote must occur verbatim in the DOI-bound abstract; interpretation is **not** certified as a source fact |
| novelty | closest_archived, shared_features, economic_difference, relabel_risk |
| protocol | hypothesis, null, falsifier, target, predictor, data, sample, baseline, method, oos, metrics, pass_rule, stop_rule, leakage_checks, costs_and_execution, budget, human_escalation |
| target | market, instrument, variable, frequency, horizon |
| predictor | variable, proxy, available_at, publication_lag |
| each data entry | name, provider, availability, point_in_time, timestamp_rule |
| sample | calibration, evaluation, sealed_holdout_excluded=true |
| budget | max_research_hours <= 8, max_new_network_requests=0, max_model_calls=0, max_spend_usd=0 |

No generated code, shell commands, arbitrary tool invocation or sealed holdout route exists in the schema. Every dataset availability must be UNVERIFIED or OPERATOR_VERIFICATION_REQUIRED. A model cannot self-certify the data.

The gate rejects known archived mechanism names and high-confidence synonym families: trend/momentum/breakout, vol exposure, perpetual funding/leverage, search attention, weekday/calendar, liquidity reversal. **It does not prove unrecognized language is novel**. Even a valid unknown channel ends as NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW, never NOVEL_CONFIRMED.

The P1 scope detector is reused only as a conservative warning/rejection for a known stock-return target mismatch or a derivatives/high-frequency-to-spot/daily transfer. Intraday source data does not automatically render a mechanism worthless; a separate target and protocol could be defensible.

## Offline commands

    python -m pip install -e .
    python -m unittest discover -s tests -v

    # No proposal: safe abstention, no model call.
    quant-mechanism --home runtime \
      --evidence-report agent/reports/abstract-evidence-v1-34ec01bb674b.json

    # Only after an independently produced proposal has been inspected:
    quant-mechanism --home runtime \
      --evidence-report agent/reports/abstract-evidence-v1-34ec01bb674b.json \
      --proposal agent/proposals/unreviewed-mechanism.json

Output is content-addressed under runtime/agent/mechanism_discovery/. It records proposal digest, original source DOI/provider/raw digest, scope classification, review reasons, and zero model/network/experiment calls. Existing P1 reports and databases remain read-only; PAUSED prevents work. No proposal returns NO_MODEL_PROPOSAL_UNDER_CURRENT_PERMISSIONS, not a fake candidate.

## P2-B real autonomous acceptance (separate authorization)

1. Pre-register an **outcome-independent selection policy** over previously unseen DOI evidence. The five weekday-ranked P1 papers cannot be taken as evidence of general mechanism discovery. Limit to 1–3 sources and one model-proposed candidate for the first test.
2. Obtain owner permission for the exact provider, token/cost ceilings, prompt, structure, query and allowable external sources. Current P2-A budget is zero additional model calls and zero additional network calls.
3. Present source evidence and archived-mechanism summaries to the model without preselecting its preferred mechanism or Kill Test; archive model identifier, prompt, output and usage.
4. Run the independent offline gate. Human reviews source target/predictor/direction, novel causal channel versus archived mechanisms, point-in-time data, null/baseline, falsifier, OOS plan, cost/latency and concrete stop rule.
5. Accept autonomy only if an independently reviewed real candidate is both genuinely different and falsifiable. Safe NO_NEW_FEASIBLE_MECHANISM when none qualifies is a valid negative result, **not** P2's positive discovery acceptance.
6. No execution of novel research tests or generated code until a new separate human authorization. Trading, account simulation, sealed holdout and tickets remain prohibited.

**Stop condition:** If 1–3 independent genuine sources and one separately approved bounded model attempt yield only old-family relabels, unsupported causal claims or non-time-consistent data, document failure and stop. Do not add a multi-agent platform or more paper classifiers to manufacture throughput.
