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

`MVP_CORE_LOOP_ACCEPTED_RESEARCH_ONLY`

The first real-data/API research loop, report archive, same-implementation numerical reproduction, and independently coded execution reconstruction **all passed**. The bounded 2024 execution audit finished on 2026-11-16 with `INDEPENDENT EXECUTION RECONSTRUCTION PASSED`. **The MVP acceptance goal is met; stop further execution-infrastructure work unless a material error is discovered.**

**Scope of evidence:** same historical CSV, archived JSON summaries, and a separately implemented 2024 execution replay. The original per-trade fills were not recorded, so no direct fill-by-fill reconciliation was possible. Independent source-level market-data verification is not claimed. Clean-environment reproduction on Ubuntu and macOS was reported by the user; environment versions and raw command logs were not provided. The original experiment did not record its Git commit SHA. None of these results establishes alpha, authorizes simulation, or permits trading.

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
independent_execution_audit: "PASSED_RECONSTRUCTION"
cross_environment_reproduction: "PASSED_USER_REPORTED_UBUNTU_MACOS"
mvp_core_loop: "ACCEPTED"
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
- On 2026-11-16, user executed the standalone `audit_btc120_execution.py --root runtime`. It does not call the production `backtest.simulate` or `signal` implementation.
- The audit independently reconstructed all **7 entries and 6 completed exits** in 2024, verified the prior-close / next-open chronology and fee/slippage/cash identities across **13 events**, and matched **all 12 saved summary fields** in each of the base-cost and double-cost validation scenarios.
- Audit outcomes: base net return **92.2594%**, base net excess **-28.7148%**; doubled-cost net return **88.5470%**, doubled-cost net excess **-32.0964%**.
- Audit output: `runtime/audits/13d17d479477_2024_trade_ledger.csv` (local generated evidence, not included in this Git commit).
- Terminal evidence: `INDEPENDENT EXECUTION RECONSTRUCTION PASSED` (user-reported from local execution).
- **Limit:** the original experiment contains summary results, not original per-trade fills. The audit independently reconstructed trades against the same CSV and compared summary metrics; it did not directly compare two independently captured trade ledgers.
- On 2026-11-16, the user additionally reported successful clean-Python-environment reproduction on **Ubuntu** and **macOS**, with matching results. This is user-reported evidence; independent logs, Python/package versions, exact Git SHAs and hashes of inputs in both environments have not been supplied.

## Minimum completion evidence

1. Unit/integration tests pass: **PASSED** in project CI.
2. Real Binance historical data ingested with archived provenance and checksum manifest: **PASSED for the reported run**; independent archive-by-archive recheck is separate.
3. API mode generated one source-grounded BTC candidate: **PASSED** (constrained discovery, not autonomous literature research).
4. Development, validation and transaction-cost stress backtests executed and archived: **PASSED**.
5. Saved metrics re-calculated offline with identical data/rules: **PASSED**.
6. No broker order routing or account simulation permissions: **ENFORCED by MVP scope**.
7. Independent 2024 trade-event reconstruction, next-open timing, cash and fee identities: **PASSED**.
8. Clean-environment cross-OS reproduction (Ubuntu and macOS): **PASSED, user-reported** (raw logs and environment manifests not attached).
9. Independent upstream market-data verification: **NOT IN SCOPE** for this minimum MVP acceptance.

## Next action and stop condition

**Close this MVP validation task.** Keep the 120-day momentum candidate archived as `ARCHIVED_REJECTED_OR_INCONCLUSIVE`, and do **not** use the sealed 2025 holdout for it. Do not retune its lookback or reopen the failed setup.

For any subsequent research cycle, prioritize **a genuinely different, evidence-grounded economic mechanism**, not more pipeline engineering or parameter variations. Only revisit this MVP's execution infrastructure if a concrete material defect is discovered. Live trading, simulation, autonomous code execution, and multi-market features remain out of scope.

## Repository change and merge authority

**Mandatory workflow from 2026-11-16 onward:**

- Never commit or push repository changes directly to `main`.
- For every proposed code, test, configuration, or project-state/documentation change, create a dedicated branch from the latest `main`.
- Commit and push the change only to that branch, then open a pull request targeting `main`.
- The assistant may prepare the branch, explain the diff, run/check CI, and request review. The assistant must **never merge** the pull request or otherwise update `main`.
- The repository owner/user retains the sole decision and authority to approve and merge. A pull request is a proposal, not permission to merge.
- If `main` moves while work is in progress, rebase/update the feature branch and re-run relevant checks; do not bypass the PR workflow.
- This rule applies to future work. It does not retroactively alter commits already present on `main` before this policy was recorded.

## Explicitly deferred

Live literature search, autonomous code execution, multi-market agents, local GPU LLM, dashboard and account-level trading simulation.

## Discovery funnel v2 — improvement scoped after MVP acceptance (2026-11-16)

`discovery_upgrade: IMPLEMENTED_OFFLINE_TESTED_REAL_API_PENDING`

- A source registry contains six manually verified academic references with DOIs, study universes, and transfer limitations (including contrary evidence for illiquid-asset reversal in a BTC-only market).
- Fixed screening checks **economic mechanism, source relevance, data availability, predeclared falsifier and mechanism-level novelty**. The numeric score is triage only, not estimated alpha.
- SMA, momentum and channel breakout are grouped as `trend_persistence`; after an archived real trend experiment, legacy `quant-agent run-once --mode api` refuses additional trend variants before data loading/model calls.
- `quant-ideas preview` and `quant-ideas sources` are offline; `quant-ideas discover --mode seed` is a non-persisting demo. A paid `quant-ideas discover --mode api` can propose **one** nontrend, OHLCV-feasible idea per mechanism and archives its evidence/kill test separately from historical backtests.
- Current first eligible mechanism: `volatility_exposure`, with Moreira–Muir evidence explicitly marked as **traditional factor market transfer**, no demonstrated BTC spot alpha, and execution state `RULE_NOT_IMPLEMENTED`.
- Investor attention is blocked without external signal data; cross-sectional reversal is blocked due to BTC transfer mismatch. No 2025 holdout, simulated trades, parameter tuning or execution engine changes.
- The discovery funnel has only offline/mocked tests thus far; real paid gateway behavior and the quality of any generated idea are **not yet verified**.

**Next bounded action:** run `quant-ideas preview`, then at most one `quant-ideas discover --mode api` call. Evaluate whether the returned idea has a genuinely distinct, executable economic mechanism, a risk/exposure-matched benchmark, and a kill test. Stop if it does not. Do not expand the infrastructure to fabricate more candidates.

