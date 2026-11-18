# SOURCE_TO_HYPOTHESIS_RELEVANCE_GATE_v1

**Status:** a reviewable, conservative addition to the existing P1. It is a source-fit check, **not** a new BTC strategy, alpha screen, paper replication, or authorization to re-test the archived Monday hypothesis.

## What failed on 2026-11-18

The user's first P1 Crossref run classified DOI `10.1016/j.frl.2025.108661`, **“A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns”**, as an eligible title. Its dependent variable is **Monday stock returns**, with **weekend cryptocurrency returns** as an explanatory signal. The fixed P1 statistical template instead predicts **BTC spot daily returns** from a **Monday calendar dummy** and frozen price-only controls. The source-to-test fit failed. All four fixed historical information gates also failed; the original test and report must remain archived and cannot be re-run with an alternative paper, weekday, or tuning.

## New evidence-to-execution contract

A Crossref DOI record must satisfy, in order:

1. **Target / direction:** identify Bitcoin/BTC *returns as the predicted outcome*, not merely as an explanatory input for stock/equity returns. An explicit stock-return target is a hard veto.
2. **Market:** reject Bitcoin futures/perpetual/options market targets for the fixed BTC **spot** template.
3. **Predictor:** reject papers explicitly predicting returns *using weekend/lagged cryptocurrency returns, funding, sentiment or other signals* in place of the **known Monday or day-of-week indicator**. Merely containing the word “Monday” is not enough.
4. **Calendar scope:** require explicit Monday / weekday / day-of-the-week language, a calendar-effect concept, and explicit Bitcoin return target in the **title**.
5. **Abstract confirmation:** require the same outcome and calendar scope in a non-empty optional Crossref abstract. JATS/HTML tags are stripped as text, not executed. **If the abstract is absent or ambiguous, no automatic research run is authorized.**

This is a **high-precision, low-recall deterministic gate**; it does not understand all academic prose, read papers, verify peer review, or establish causality. Crossref abstracts are optional metadata and not full papers. Results may be: `ELIGIBLE_FOR_FROZEN_TEMPLATE`, `NEEDS_HUMAN_SOURCE_REVIEW`, `REJECT_TARGET_MISMATCH`, `REJECT_MARKET_MISMATCH`, `REJECT_PREDICTOR_MISMATCH`. A matching record is a **mechanism cue only**, not proof of a published finding or a valid trading strategy.

This gate deliberately trades missed candidates for fewer false-positive experimental starts. Do **not** adjust matching rules to turn the already selected DOI into a pass. Future broader source-to-hypothesis reasoning requires a separately reviewed proposal and a labeled benchmark of genuine scientific summaries.

## Offline audit of the archived 15 records

```bash
# Only after reviewing this PR; uses the original local runtime, no API request.
quant-research-loop --home runtime relevance-audit
```

`relevance-audit` opens the **existing P1 SQLite database read-only**, checks each stored DOI/title/year against original immutable `runtime/agent/evidence/crossref-poll-*.json` bytes and stored SHA256, and writes a new **content-addressed**, immutable report under `runtime/agent/reports/source-fit-audit-v1-<digest>.json`. It never modifies the original `papers.decision`, `studies`, `BTC_WEEKDAY_INFORMATION_v1.json` or the original evidence response. Missing, moved, modified or unverifiable bytes abort the audit rather than assign scores to untrusted source records. Run it twice: the output path and digest should be identical. 

**Important:** the actual 15 locally archived paper records have **not been available in this development environment**. Synthetic 15-record and known-negative DOI regression fixtures test the code, but **the real historical batch still needs to be audited locally**. With the initial Crossref query lacking an `abstract` field, many previous titles will correctly end in `NEEDS_HUMAN_SOURCE_REVIEW` rather than auto-eligibility.

## Integration and stop condition

- Future P1 metadata polls request the optional `abstract` field on the same fixed Crossref source. The existing policy schema/digest and one-request/day budget are unchanged.
- A newly discovered paper creates the frozen study **only after** `ELIGIBLE_FOR_FROZEN_TEMPLATE` is returned. Any previously queued `WAITING_DATA` task must also pass its own **archived-byte-verified** source-fit check before reading any spot prices.
- A terminal P1 study now causes `IDLE_TEMPLATE_SATURATED` and **zero subsequent Crossref requests**: the single approved template is spent and its hypothesis must not be rescued by a new DOI. The user's already completed STOP result remains terminal.
- The currently deployed P0 `quant-orchestrator.timer` is not touched. The separate P1 timer remains off; do not activate it for this archived template.
- Neither source-fit audit nor classifier accesses 2024/2025 spot data, runs a backtest, places trades or consumes LLM tokens.

**Acceptance:** CI passes; known counterexample DOI is rejected; a truly aligned Bitcoin spot/weekday title + abstract can pass; ambiguity and missing abstract cause review; the real 15-item offline audit verifies raw SHA256 and reports its reclassifications without changing the original report hash `d7c5963aa73340c1c8f9d8901c511d74ce0dbd9a8dca33ae04657f59d4d0fe99`. After audit, **stop this gate iteration**. Do not restart the already rejected Monday/BTC study.
