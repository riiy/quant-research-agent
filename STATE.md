# Quant Research Agent — Project State

Last updated: 2026-11-16

## Objective

Prove the smallest auditable BTC spot daily strategy-discovery → backtest → validation → archive loop. **Not** to produce trading signals or replicate a full multi-market autonomous agent.

## Locked constraints

- Research-only; `trading_allowed: false`, `account_simulation_allowed: false`.
- Evidence-first, long-only spot; next-open execution; identical cost assumptions for buy-and-hold.
- No historical strategy resurrection, parameter search against final test, or claim of validated alpha.
- Python standard library first; no GPU dependency.
- 2025 sealed holdout requires explicit one-time `finalize` after 2024 screening.

## Current phase

`MVP_IMPLEMENTED_PENDING_REAL_WORLD_RUN`

## Minimum completion evidence

1. Unit/integration tests pass.
2. Real Binance archives downloaded and checksums validated.
3. API mode generates one compliant, source-grounded BTC hypothesis.
4. Both development and validation backtests run and archive results.
5. No order routing or unapproved account simulation.

## Explicitly deferred

Live literature search, autonomous code execution, multi-market agents, local GPU LLM, dashboard and account-level trading simulation.
