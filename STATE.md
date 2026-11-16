# Quant Research Agent — Project State

Last updated: 2026-11-16

## Objective

Prove the smallest auditable BTC spot daily strategy-discovery → backtest → validation → archive loop. **Not** to produce trading signals or replicate a full multi-market autonomous agent.

## Locked constraints

- Research-only; `trading_allowed: false`, `account_simulation_allowed: false`, `ticket_generation_allowed: false`.
- Evidence-first, long-only spot; signal from prior close, next-open execution; cost-adjusted buy-and-hold comparator.
- No historical strategy resurrection, parameter search against final test, or claim of validated alpha.
- Python standard library first; no GPU dependency.
- 2025 sealed holdout requires explicit one-time `finalize` after 2024 screening.
- Failed candidates remain archived; do not retune a failed setup to rescue its outcome.

## Current phase

`CORE_LOOP_NUMERICALLY_REPRODUCED_INDEPENDENT_EXECUTION_AUDIT_PENDING`

The first real-data/API research loop and archive completed. The saved metrics were recalculated using the same local BTC daily CSV, candidate, and project backtest implementation, matching every archived field (relative/absolute tolerance `1e-12` for floating-point fields). The saved validation status and reasons matched as well.

**Scope of evidence:** same-data/same-implementation numerical reproducibility is verified. This is **not** independent implementation verification, independent environment reproduction, verified alpha, or authorization to trade. The original run did not capture its Git commit SHA; do not claim code-version identity beyond the evidence available.

## First real experiment (archived)

```yaml
run_id: "13d17d479477"
candidate_fingerprint: "711cacf414bf684b"
market: "BTCUSDT spot"
timeframe: "1d"
direction: "long_or_cash"
family: "momentum"
params:
  lookback: 120
hypothesis_source: "moskowitz2012"
discovery_mode: "api"
data_source: "binance-public-data-spot-monthly"
data_sha256: "89d904a06e5daf3a0cb59ef87562d5b47da0cea786d82eb867bfbe2898f17be5"
strategy_status: "ARCHIVED_REJECTED_OR_INCONCLUSIVE"
numerical_reproduction: "PASSED"
independent_execution_audit: "PENDING"
holdout_evaluated: false
trading_allowed: false
account_simulation_allowed: false
```

### Frozen evaluation results

| Metric | Development (2018–2023) | Validation (2024) | Validation, double cost (2024) |
| --- | ---: | ---: | ---: |
| Net strategy return | +585.37% | +92.26% | +88.55% |
| Net buy-and-hold return | +207.83% | +120.97% | +120.64% |
| Net excess return (percentage points) | +377.55 | -28.71 | -32.10 |
| Max strategy drawdown | -52.53% | -20.62% | -22.04% |
| Entries / completed exits | 35 / 34 | 7 / 6 | 7 / 6 |

The 2024 initial screen rejected the strategy because its net return failed to outperform the cost-adjusted buy-and-hold benchmark under both base and doubled transaction costs. Positive absolute returns do **not** offset this relative failure under the locked protocol. Do **not** revisit the 120-day parameter or evaluate the 2025 sealed holdout for this archived candidate.

### Reproduction evidence

- Report: `runtime/reports/711cacf414bf684b.md` (and matching `.json`).
- User ran an offline, no-API recomputation of development, validation, and validation double-cost summaries with the archived candidate and historical CSV.
- Assertions passed for candidate fingerprint, rules, data SHA256, pre-holdout canonical data prefix hash, all persisted summary metrics, archive status, failure reasons, and absence of a holdout result.
- Reported terminal result: `REPRODUCTION PASSED`.
- Independent trade-by-trade verification has **not** yet been performed.

## Minimum completion evidence

1. Unit/integration tests pass: **PASSED** in project CI.
2. Real Binance historical data ingested with archived provenance and checksum manifest: **PASSED for the reported run**; independent archive-by-archive recheck is separate.
3. API mode generated one source-grounded BTC candidate: **PASSED** (constrained discovery, not autonomous literature research).
4. Development, validation and transaction-cost stress backtests executed and archived: **PASSED**.
5. Saved metrics re-calculated offline with identical data/rules: **PASSED**.
6. No broker order routing or account simulation permissions: **ENFORCED by MVP scope**.
7. Independent audit of 2024 entries/exits, next-open fills, fees and slippage: **PENDING**.

## Next action and stop condition

**One bounded audit:** independently recalculate the 2024 validation period's **7 entries and 6 completed exits**, checking prior-close signal availability, following-day open execution, and fee/slippage cash and position accounting.

- If consistent, mark the **MVP core loop** accepted, archive this strategy permanently, and return focus to economically distinct hypotheses. No broader infrastructure investment is required.
- If inconsistent, mark the affected historical result invalid, repair only the material execution defect, and rerun the frozen experiment before drawing conclusions.
- No need to call the LLM again, retune 120-day momentum, open the 2025 holdout or expand to multi-market research for this audit.

## Explicitly deferred

Live literature search, autonomous code execution, multi-market agents, local GPU LLM, dashboard and account-level trading simulation.
