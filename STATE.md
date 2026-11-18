# Quant Research Agent — Project State

Last updated: 2026-11-18

## Objective

**Long-term North Star:** 7×24 unattended AI Quant Research Agent. **Humans set research goals, budget, approved methods and safety boundaries; the agent discovers, executes, falsifies, archives and iterates within them.** No trading or sealed holdout access without separate human authorization.

**Completed milestone:** the auditable BTC spot daily discovery → backtest → validation → archive MVP. That accepted MVP was intentionally narrower than an autonomous agent. Do not rewrite its validated engine.

## Locked constraints

- Research-only; `trading_allowed: false`, `account_simulation_allowed: false`, `ticket_generation_allowed: false`.
- Evidence-first, long-only spot; signal from prior close, next-open execution; cost-adjusted buy-and-hold comparator.
- No historical strategy resurrection, parameter search against final test, or claim of validated alpha.
- Python standard library first; no GPU dependency.
- 2025 sealed holdout requires explicit one-time `finalize` after 2024 screening.
- Failed candidates remain archived; do not retune a failed setup to rescue its outcome.

## Current phase

`P1_FIRST_REAL_CYCLE_COMPLETED_SOURCE_FIT_REVIEW_REQUIRED` — PR #8 merged; a user-run real Crossref-to-frozen-test-to-archive cycle completed on 2026-11-18. The specific statistical hypothesis failed all four predeclared gates. **However the selected DOI predicts Monday STOCK returns using weekend CRYPTO returns, whereas the frozen test predicts Monday BTC returns: source-to-test relevance failed.** P1 engineering path was demonstrated; P1 scientific relevance acceptance is not met. P0 manual service test and timer activation were user-reported on 2026-11-17; its seven-day unattended acceptance is still pending.

Prior completed milestone: `MVP_CORE_LOOP_ACCEPTED_RESEARCH_ONLY`.

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

`discovery_upgrade: VOLATILITY_MECHANISM_KILL_TEST_FAILED_ARCHIVE_PROPOSED`

- A source registry contains six manually verified academic references with DOIs, study universes, and transfer limitations (including contrary evidence for illiquid-asset reversal in a BTC-only market).
- Fixed screening checks **economic mechanism, source relevance, data availability, predeclared falsifier and mechanism-level novelty**. The numeric score is triage only, not estimated alpha.
- SMA, momentum and channel breakout are grouped as `trend_persistence`; after an archived real trend experiment, legacy `quant-agent run-once --mode api` refuses additional trend variants before data loading/model calls.
- `quant-ideas preview` and `quant-ideas sources` are offline; `quant-ideas discover --mode seed` is a non-persisting demo. A paid `quant-ideas discover --mode api` can propose **one** nontrend, OHLCV-feasible idea per mechanism and archives its evidence/kill test separately from historical backtests.
- `volatility_exposure` was the first idea-only mechanism; its fixed 2018–2023 mechanism Kill Test has now **failed**. It is to be archived, not retuned or backtested. Moreira–Muir remains transfer-only evidence from non-crypto factors.
- Investor attention is blocked without external signal data; cross-sectional reversal is blocked due to BTC transfer mismatch. No 2025 holdout, simulated trades, parameter tuning or execution engine changes.
- The discovery funnel completed one real API generation (idea `4b7cb9282852`), but idea generation is not evidence of strategy quality or tradable alpha.

**Latest v2 evidence:** the user ran one real API discovery on 2026-11-16 and reported idea `4b7cb9282852` (`volatility_exposure`), originally `AWAITING_RULE_DESIGN_NOT_BACKTESTED`. The subsequent read-only mechanism Kill Test was executed locally and reported failure. Its output does not constitute a trading-strategy backtest.

### Volatility exposure Kill Test — failed, archive decision (2026-11-17)

The user supplied the local mechanism-test JSON `runtime/ideas/4b7cb9282852_volatility_mechanism_kill_v1.json` (the report is **not** committed here). The original report status is `STOP_INSUFFICIENT_MECHANISM_EVIDENCE`; the research decision below maps this to `FAILED` and `ARCHIVE` in project state.

```yaml
idea_id: "4b7cb9282852"
mechanism_id: volatility_exposure
kill_test:
  period: "2021-2023"
  status: FAILED
  risk_ratio: 1.493224
  bootstrap_lower_95: 1.291403
  failed_gate: HIGH_VOL_REWARD_COMPENSATION
decision: ARCHIVE
strategy_backtest_allowed: false
holdout_evaluated: false
```

- Protocol: `btc-vol-mechanism-kill-v1-frozen-2026-11-16`; **2018–2020** used to freeze the 30-day realized volatility median threshold (`0.03262698645975258`), **2021–2023** used for the mechanism check (`1095` observations). No 2024 or 2025 data used.
- The high/low next-day mean absolute log-return ratio `1.4932242289511706` exceeded the predeclared `1.20` materiality threshold; the 14-day block-bootstrap one-sided 95% lower bound `1.2914030975158188` exceeded `1.0`; both regimes met the 100-day minimum (`501` high, `594` low).
- **Failed gate:** high-volatility reward per unit mean absolute return `0.02955883943559558` was greater than low-volatility reward per unit mean absolute return `-0.0034058117622033823`; this violates the frozen condition `high <= low`. The result **does not support** the proposed "high volatility → cash" mechanism under the predeclared protocol. It does **not** establish that the mean-return difference itself is statistically significant.
- **Decision and stop condition:** archive this idea, do not develop an execution rule, do not run strategy backtests, do not optimize the 30-day window or median threshold, and do not inspect 2024/2025 for this candidate. No trading or account simulation authorization.
- Evidence scope: user-provided JSON only; local report and underlying data were not independently recomputed in this PR, and the local `ideas.sqlite3` record was **not** mutated.

**Next action:** stop this candidate and avoid further model calls for the same volatility mechanism. Reconsider new economic mechanisms or additional data only if a specific decision-relevant hypothesis can be stated.


## BTC perpetual funding pressure — Phase 0 data audit proposed (2026-11-17)

```yaml
research_id: BTC_PERP_FUNDING_PRESSURE_v1
mechanism: derivatives_leverage_pressure
market: BTCUSDT USD-M perpetual funding (signal source), BTCUSDT spot (later target)
phase: DATA_PROVENANCE_AND_TIME_QUALITY_GATE
status: DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED
history_range: "2020-01..2023-12"
strategy_implemented: false
strategy_backtest_allowed: false
holdout_evaluated: false
trading_allowed: false
```

**Why distinct:** periodic funding payments proxy futures premium and potential leveraged-demand pressure, unlike the archived BTC trend and binary volatility rules. They are not observations of open interest, position sizes, forced liquidation or leverage themselves. Kim (2026), `10.1016/j.jempfin.2026.101779`, finds incremental information for *BTC volatility*, not net BTC spot return predictability.

**Bounded Phase 0:** `quant-funding audit` fetches exactly 48 monthly Binance USD-M `BTCUSDT` funding archives and SHA256 checksums for 2020–2023; validates documented ZIP fields `calc_time,funding_interval_hours,last_funding_rate`, UTC millisecond settlement times, 8-hour grid (00/08/16 UTC), duplicates, missing slots, unexpected intervals and archive chronology. It does not impute or silently repair. Expected 1461 days / 4383 settlements; if archive differs, diagnose rather than assume a complete dataset. It produces immutable local CSV and audit JSON only on successful coverage checks, with failed coverage reported separately. Eight offline synthetic tests passed; **real Binance v2 audit was subsequently run by the user and reported passing; the assistant has not independently downloaded/recomputed the archive**.

**Gate:** any unresolved provenance or timestamp inconsistency -> stop mechanism testing. If data passes, freeze a distinct, preregistered *mechanism-only* test: calibrate extreme positive funding using 2020–2021, evaluate 2022–2023 post-settlement BTC spot returns/downside risk against lagged-price/volatility controls. Must verify time availability and avoid 2024/2025 data. Predicting volatility is insufficient to grant backtest or trading permission.

**Repository authority:** implement on a feature branch and PR only; owner alone decides merge. No direct `main` write.

### 2026-11-17 timestamp-grid diagnosis — audit protocol v2 proposed

The user ran an independent **read-only diagnostic** on all locally cached 2020–2023 BTCUSDT funding archives. Its reported results:

- **4,383 raw records**; exact 4,383 unique nominal 8-hour slots; `missing_nominal_slots=0`, `extra_nominal_slots=0`, `slot_collisions=0`.
- Raw settlement timestamp offsets relative to nominal UTC 00:00/08:00/16:00: **2,150 exactly on the slot, 2,233 positive offsets of +1 to +47 milliseconds**; `negative_offsets=0`, `maximum_absolute_offset_ms=47`.
- The original v1 audit incorrectly treated each millisecond shift as *both* a missing nominal slot and an unexpected raw timestamp, yielding three linked issue counts of 2,233. This is a **strict-equality audit artifact**, not evidence of 2,233 missing settlements.
- **Auditing rule correction**, not a trading/model parameter: compare to nominal slot with a fixed **0–100 ms post-slot tolerance**; check duplicates on **both original raw timestamp and nominal slot**, full coverage, non-8h intervals, chronology, monthly SHA256 and CSV contract. Preserve original `calc_time` in the canonical export and never infer availability before actual publication.
- Retain old failed `BTCUSDT-funding-2020-2023.audit.json` unchanged; new v2 outputs `BTCUSDT-funding-2020-2023.audit.v2.json` and `BTCUSDT-funding-2020-2023.v2.csv` (only if clean).
- **Historical v2 pre-recheck status:** `TIMESTAMP_JITTER_DIAGNOSED_AUDIT_V2_SYNTHETIC_TESTED_REAL_RECHECK_PENDING`. Eleven offline unittest cases passed in the development environment (including 47ms allowed, 100ms boundary, 101ms rejected, negative offset and nominal-slot collision). The subsequent **user-run real-data v2 audit passed**; see the completed gate below.
- **Historical next action (completed):** the operator ran `quant-funding audit --offline` and submitted the **v2** audit JSON. A separate, preregistered mechanism test may now be prepared for review; no automatic strategy backtest or holdout use.

### Phase 0 actual Binance archive audit v2 — passed (user report, 2026-11-17)

**Evidence**: user-uploaded `BTCUSDT-funding-2020-2023.audit.v2.json`; protocol `BTC_PERP_FUNDING_PRESSURE_v2_timestamp_jitter_audit_2020_2023`. This is a **data quality/provenance check**, not mechanism efficacy, predictive validation, strategy simulation or alpha evidence.

```yaml
research_id: BTC_PERP_FUNDING_PRESSURE_v1
mechanism: derivatives_leverage_pressure
phase: DATA_PROVENANCE_AND_TIME_QUALITY_GATE
status: DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED
archive_months: 48
period: "2020-01-01..2023-12-31"
expected_settlements: 4383
observed_settlements: 4383
unique_raw_settlement_times: 4383
unique_nominal_settlement_slots: 4383
issues: []
max_timestamp_delay_ms: 47
canonical_csv_sha256: "159050d8818298c777f9ac1290530aecc01a01859d209df9d39c306a4b5eb977"
strategy_implemented: false
strategy_backtest_allowed: false
holdout_evaluated: false
trading_allowed: false
```

- Checks include 48 monthly ZIP archives / SHA256, strict CSV schema, 8h funding interval / nominal UTC slots and bounded 0–100ms post-slot offset; no imputations or silent repairs.
- User-run audit reports **2,150 on-grid timestamps**, **2,233 timestamps offset +1..+47ms**, no negative delays, no missing or collided nominal slots, no issues. By year: 2020 = 1,098; 2021–2023 = 1,095 each.
- Funding sign distribution: 3,793 positive settlements and 590 negative; these are **funding events**, not independent trading signals, and do not prove leverage crowding or spot return predictability.
- Local canonical CSV itself and its source ZIPs were **not uploaded** in this review; SHA256 is a provenance identifier from the audit JSON, not an independently reproduced hash.
- **Decision:** close Phase 0 data remediation. The next *separately reviewed* task may test whether extreme positive *settled and known* funding predicts **future BTC spot direction/downside beyond trailing return and volatility**, using 2020–2021 for fixed calibration and 2022–2023 for evaluation. Audit timestamps do not prove data publication latency: any joined signal must use a conservative, causal availability lag.
- **Stop rules:** if Phase 1 lacks independent regime/event counts, useful incremental evidence, or properly causal timestamp joins, stop/archive. Do not optimize thresholds, reopen archived trend/volatility mechanisms, unseal 2024/2025, or perform a strategy backtest under this audit approval.

## BTC_PERP_FUNDING_PRESSURE_v1 — Phase 1 mechanism test proposed (2026-11-17)

```yaml
research_id: BTC_PERP_FUNDING_PRESSURE_v1
mechanism: derivatives_leverage_pressure
phase: PHASE_1_INCREMENTAL_INFORMATION_KILL_TEST
status: STOP_INSUFFICIENT_INCREMENTAL_INFORMATION
calibration: "2020-01-01..2021-12-31"
evaluation: "2022-01-01..2023-12-31"
funding_provenance_sha256: "159050d8818298c777f9ac1290530aecc01a01859d209df9d39c306a4b5eb977"
strategy_implemented: false
strategy_backtest_allowed: false
holdout_evaluated: false
trading_allowed: false
```

**Economic mechanism under test:** funding is a *proxy* for BTC perp premium/potential leveraged-long crowding, not open interest or leverage itself. Distinct from archived momentum/trend and volatility-exposure families. Prior papers linking funding to volatility do **not** prove incremental next-day spot return or tail-risk predictability.

**Frozen preregistration:** `docs/FUNDING_PHASE1_PROTOCOL.md` in this feature PR. No hyperparameter tuning, no trading simulation and no 2024/2025 accesses.

- Daily funding = mean of all three verified settlements for UTC day; extreme positive iff the **t−2 day** mean exceeds the **2020–2021 nearest-rank 90th percentile** (strict >, positive-only threshold).
- For outcome day `t` in 2022–2023, the signal **and** price control features stop at `t−2` (full calendar-day availability margin); target is BTC spot `log(close[t]/close[t−1])`. Spot 7-day trailing log return and 30-day realized log-return standard deviation are binned by calibration-only tertile boundaries. **3×3 price bins crossed with evaluation year** yield within-year event/non-event comparisons. This matching is retrospective, not investable.
- Test two predeclared endpoints with **Bonferroni one-sided alpha 0.025 each**: adjusted daily log-return difference <= -0.003 with 97.5% block-bootstrap upper <0; OR increased probability of daily log-return <= -0.02 by >=0.05 with 97.5% lower >0. Fixed 14-day circular block bootstrap ×1000, seed 20261117, at least 950 valid draws; the matching effect must have correct sign **in both 2022 and 2023**.
- Minimum 40 extreme event days, 10 in each year, eight distinct 14-day blocks, and 10 contemporaneous non-event controls per event/year×price stratum. Sparse or unstable evidence => `STOP_INSUFFICIENT_INCREMENTAL_INFORMATION`, archive without threshold/lookback/horizon rescues.
- The mechanism test is reproducible through immutable local `runtime/funding/BTCUSDT-funding-phase1-mechanism-v1.json`. **The user subsequently ran the real 2022–2023 Phase 1 evaluation, resulting in zero extreme-positive funding events and a frozen protocol stop.** Fourteen synthetic unit tests and GitHub CI passed; the original spot/funding CSVs were not independently re-evaluated in this PR.
- Mechanism-only pass => `PASS_INCREMENTAL_INFORMATION_ONLY`, **not** trade alpha or strategy permission. Explicit separate owner review required for any later cost-, exposure- and risk-matched strategy research.

### Phase 1 real-data Kill Test — no event support; archive the fixed rule (2026-11-17)

The user executed `quant-funding-kill` on their local verified 2020–2023 data and supplied `BTCUSDT-funding-phase1-mechanism-v1.json`. This report is local and **not** committed. The result follows the unmodified, previously frozen Phase 1 protocol.

```yaml
research_id: BTC_PERP_FUNDING_PRESSURE_v1
mechanism: derivatives_leverage_pressure
phase: PHASE_1_MECHANISM_ONLY
protocol: BTC_PERP_FUNDING_PRESSURE_v1_mechanism_frozen_2026-11-17
calibration: "2020-01-01..2021-12-31"
evaluation: "2022-01-01..2023-12-31"
calibration_extreme_positive_funding_threshold: 0.0006289833333333333
evaluation_days: 730
event_days: 0
event_days_by_year: {"2022": 0, "2023": 0}
event_14day_calendar_blocks: 0
valid_bootstrap_replicates: 0
adjusted_log_return_diff: null
adjusted_downside_probability_diff: null
phase1_status: STOP_INSUFFICIENT_INCREMENTAL_INFORMATION
decision: ARCHIVE_FIXED_EXTREME_POSITIVE_FUNDING_CANDIDATE
strategy_implemented: false
strategy_backtest_allowed: false
holdout_evaluated: false
trading_allowed: false
```

- **Failure mode:** the fixed, calibration-only nearest-rank 90th percentile threshold of mean daily funding was **never exceeded** in the 730 evaluation days. The frozen 40 total events, 10 per year and eight separate 14-day blocks gates all fail. Price/volatility-adjusted outcomes, year stability and bootstrap confidence intervals are **not estimable**, rather than negative or statistically insignificant.
- The funding CSV SHA256 supplied in the report is `159050d8818298c777f9ac1290530aecc01a01859d209df9d39c306a4b5eb977`, matching the previously frozen Phase 0 canonical digest. Spot 2020–2023 prefix SHA256 in this report: `fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def`. Neither dataset was independently recomputed here.
- **Interpretation:** zero events show inadequate out-of-period *support* and possible funding-regime distribution shift. This does **not** establish the absence of all funding predictive information or refute leverage-pressure economics; it refutes the *testability* of this frozen absolute-threshold candidate in 2022–2023.
- **Stop:** archive the **exact candidate and protocol**. Do not lower the percentile, switch to rolling quantiles, reverse the sign, change horizons, extend the evaluation interval or peek at 2024/2025 to rescue it. Do not implement strategy trading or historical P&L. Revisit the broader derivatives-pressure mechanism only on genuinely new, independently sourced economic evidence and a separately preregistered research question—not by retuning this failed experiment.

## BTC_ATTENTION_DEMAND_v1 — frozen retrospective Kill Test proposed (2026-11-17)

```yaml
research_id: BTC_ATTENTION_DEMAND_v1
mechanism: investor_attention_demand
phase: PHASE_1_RETROSPECTIVE_INCREMENTAL_INFORMATION
status: STOP_INSUFFICIENT_INCREMENTAL_INFORMATION
calibration: "2020-2021"
evaluation: "2022-2023"
primary_signal: "Google Trends Bitcoin Cryptocurrency Topic /m/05p0rrx"
primary_csv_sha256: "99b33105242c99e2b9580de04413c269c38d1988a1fa3a6fd26987d05a341a5f"
robustness_signal: "Google Trends bitcoin Search term"
robustness_csv_sha256: "8eb882a7984d96bdd4033010263710fc404c0d7add9b77d6d8181a4f82d6e8fe"
spot_2020_2023_prefix_sha256: "fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def"
point_in_time_search_history: UNVERIFIED
strategy_implemented: false
strategy_backtest_allowed: false
holdout_evaluated: false
trading_allowed: false
```

**Independent mechanism:** investor search attention may proxy external demand/news attention, unlike archived trend, vol-management and perp funding thresholds. **Not** a measured flow of new investor money.

**Source check:** two byte-identical user-uploaded Google Trends exports each for `bitcoin` term and `Bitcoin (Cryptocurrency)` Topic, 210 Sunday-start rows per export; use 208 *complete* study weeks. Identical exports do not prove independent Trends sampling. Both series are **retrospectively retrieved and normalized** over a period including the 2022–2023 evaluation, without historical point-in-time snapshots. That permanently limits any positive result to *retrospective statistical association*. No claim of live execution feasibility.

**Frozen protocol:** `docs/ATTENTION_PHASE1_PROTOCOL.md` in feature PR. Weekly market target = current complete week's spot close-to-close log return; all regressors through **week t−2** (one complete intervening buffer week), 3 price-only variables (1-week historical log return, 4-week realized log-return SD, weekly BTC base-volume vs previous 4-week average), plus Topic log-ratio change. Fixed standardized ridge L2 penalty 10, intercept unpenalized; training 2020–2021 only; 104 evaluation weeks 2022–2023. Search term is predetermined robustness veto, not an additional independently optimized alpha signal.

**Pass gate:** overall Topic MSE reduction ≥5% vs same price-only model; paired circular 4-week block bootstrap ×2000, one-sided 95% lower bound of MSE gain >0; positive MSE gains in both evaluation years; augmented model beats fixed zero-return predictor; Search term positive overall MSE gain. Failure => STOP and archive this exact hypothesis; no tweaks, no 2024/2025 peek. Pass => `PASS_RETROSPECTIVE_INCREMENTAL_INFORMATION_ONLY`, not validated historical tradability, alpha or strategy backtest permission.

**Execution status:** CLI and 12 synthetic/offline tests passed. The user subsequently ran the frozen retrospective Kill Test on local 2020–2023 BTC spot data and supplied a failed real-data report; its results and limits are recorded below. The underlying raw price file was not independently re-run in the assistant environment.

### BTC attention Phase 1 actual retrospective Kill Test — stopped and archived (2026-11-17)

**Evidence:** user-uploaded local `BTCUSDT-attention-phase1-retrospective-kill-v1.json`, protocol `BTC_ATTENTION_DEMAND_v1_retrospective_incremental_kill_frozen_2026-11-17`; results follow the predeclared primary Topic and robustness Search term design. The local CSVs were not independently re-evaluated here.

```yaml
research_id: BTC_ATTENTION_DEMAND_v1
mechanism: investor_attention_demand
phase: PHASE_1_RETROSPECTIVE_INCREMENTAL_INFORMATION
calibration: "2020-2021"
evaluation: "2022-2023"
training_weeks: 97
evaluation_weeks: 104
topic_mse: 0.007363039853341847
price_only_mse: 0.007372907653703622
zero_return_mse: 0.007047648383972307
relative_topic_mse_gain: 0.0013383865396467362
bootstrap_lower_one_sided_95_mse_gain: -0.000019224585919018704
relative_term_mse_gain: -0.0006137635439484827
status: STOP_INSUFFICIENT_INCREMENTAL_INFORMATION
decision: ARCHIVE_RETROSPECTIVE_ATTENTION_PREDICTION_CANDIDATE
strategy_backtest_allowed: false
holdout_evaluated: false
trading_allowed: false
```

**All five frozen gates failed:**

1. Topic improvement **0.1338%** is below the required **5%** relative MSE reduction.
2. Four-week block-bootstrap one-sided 95% lower MSE-gain bound is **negative**, so positive incremental prediction improvement is not supported.
3. The 2022 paired absolute MSE gain was `+0.000022921325611290846`; 2023 was `-0.0000031857248877415244`, violating the required positive sign in both years.
4. Topic augmented model MSE `0.007363039853341847` is worse than predeclared zero-return forecast MSE `0.007047648383972307` (roughly **4.48%** larger).
5. Search term robustness effect was **−0.0614%** relative MSE gain.

**Input provenance (report):** Topic SHA256 `99b33105242c99e2b9580de04413c269c38d1988a1fa3a6fd26987d05a341a5f`, Search term SHA256 `8eb882a7984d96bdd4033010263710fc404c0d7add9b77d6d8181a4f82d6e8fe`, 2020–2023 spot prefix SHA256 `fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def`. The report is user-run evidence, not an independent raw-data reproduction.

**Interpretation:** This **specific, fixed weekly BTC attention incremental-prediction hypothesis** failed its predetermined materiality, statistical, annual-stability, naive-forecast and robustness gates. Do not infer investor attention can never affect crypto markets. The historical Trends export is full-period normalized and point-in-time unavailable, further limiting retrospective findings.

**Stop and archive:** Do not change search entity/term, model penalty, lookbacks, forecast lag, horizons or evaluation window to rescue the candidate. Do not open 2024/2025, generate trading rules, or perform strategy P&L. Close the current attention-demand candidate; only an independent economic mechanism with genuinely new evidence warrants a separately preregistered future study.

## AGENT_ORCHESTRATOR_v0 — approved-task autonomous control (2026-11-17)

```yaml
long_term_goal: 7x24_AUTONOMOUS_RESEARCH_DISCOVER_FALSIFY_ARCHIVE_ITERATE
current_phase: P1_FIRST_REAL_CYCLE_COMPLETED_SOURCE_FIT_REVIEW_REQUIRED
completed_milestone: MVP_CORE_LOOP_ACCEPTED
active_strategy_research: null
new_unreviewed_mechanism_execution_allowed: false
trading_allowed: false
account_simulation_allowed: false
ticket_generation_allowed: false
sealed_holdout_access_allowed: false
autonomous_external_browsing_allowed: false
autonomous_code_generation_execution_allowed: false
agent_systemd_timer_enabled: true # user-reported; systemd journal not independently reviewed
seven_day_unattended_acceptance: IN_PROGRESS_NOT_PASSED
```

The prior study-by-study approach built useful reproducible tests but not the intended closed-loop autonomous agent. Next priority: control-plane lifecycle, not a fifth BTC mechanism.

**P0 protocol:** [`docs/AGENT_ORCHESTRATOR_V0.md`](docs/AGENT_ORCHESTRATOR_V0.md). Operator-owned JSON policy, archived-mechanism guards, SQLite atomic task claiming, audit events and immutable task approvals, bounded restart recovery, pause/safe idle, UTC-day heartbeats. The new one-shot systemd timer is provided as a **disabled example**; the legacy archived-trend runner is never invoked by this controller.

**v0 task allowlist:** (1) existing curated six-source registry screen for eligible mechanisms; no eligible -> `NO_NEW_FEASIBLE_MECHANISMS`, eligible -> `AWAITING_HUMAN_PROTOCOL_APPROVAL`; (2) SHA256/status/safety verification of a previously archived funding/attention JSON report. Does **not** autonomously retrieve new literature, generate code, run mechanism Kill Tests, backtest, access sealed holdouts, call an LLM or trade. This is intentionally a **P0 controller** with bounded capabilities, not a full research agent.

**No rescue:** trend, volatility exposure, funding pressure and attention demand remain archived and cannot be revived by changing the v0 policy. An empty queue is a correct stop condition, not a request to generate redundant research.

**Acceptance:** Seven *real* consecutive UTC dates of service heartbeats, at least one completed preapproved task, no failed tasks or policy drift, no duplicate work or paid API calls, and independent OS journal verification of unattended scheduling. Simulated-time tests are not proof of a deployed 7×24 agent. Only then record `SEVEN_DAY_UNATTENDED_CONTROLLER_ACCEPTED`. Further P1 evidence discovery / generic bounded test execution requires new human review. Stop further P0 infrastructure work once accepted.

## AUTONOMOUS_RESEARCH_LOOP_v1 — bounded evidence-to-falsification P1 (2026-11-18)

```yaml
p1_status: FIRST_REAL_CYCLE_USER_REPORTED_SOURCE_FIT_FAILED
p1_live_external_source_checked: true # user-reported Crossref fetch; raw response not independently inspected
p1_real_spot_mechanism_result: STOP_INSUFFICIENT_INCREMENTAL_INFORMATION # user-reported; full JSON unavailable
p1_timer_enabled: false
p0_seven_day_unattended_acceptance: IN_PROGRESS_NOT_PASSED
trading_allowed: false
account_simulation_allowed: false
sealed_2024_2025_holdout_evaluated: false
```

**Purpose:** Move beyond P0's hourly `IDLE_NO_APPROVED_TASKS` to a real bounded **new evidence → frozen hypothesis → automated falsification → cumulative archive** cycle. Stop spending the primary development budget on P0 infrastructure or bespoke manually operated new trading models.

**Design and source audit:** `docs/AUTONOMOUS_RESEARCH_LOOP_V1.md`. A separate `quant-research-loop` process (not altering the deployed P0 service) may, if explicitly activated by the operator, request new-to-local-archive **Crossref DOI/title/publication metadata** from one fixed HTTPS endpoint/query at most once per UTC day. It stores the untouched response bytes + hash, screens a deterministic calendar-return title cue, saves all eligible/irrelevant DOIs and selects only the FIRST eligible paper as a hypothesis lead. A title is NOT empirical proof; published evidence might overlap historical sample dates; no LLM, self-executed code, arbitrary network URLs or trading.

**One preapproved independent mechanism test:** `BTC_WEEKDAY_INFORMATION_v1` checks if a known Monday calendar indicator improves BTC future daily log-return prediction beyond returns, volatility and volume, with fixed ridge lambda 10, 2020–2021 calibration / 2022–2023 evaluation, pinned previously used BTC 2020–2023 spot prefix SHA256 `fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def`. Inputs break before 2024. Four preregistered AND gates: >=2% OOS relative MSE gain, positive paired block bootstrap 14-day/1000 one-sided 95% lower gain, positive in both years, beats zero-return baseline. Failure STOP/ARCHIVE; passage RETROSPECTIVE_MECHANISM_ONLY/NEEDS_HUMAN_REVIEW; never a trading validation. Only ONE study globally per P1 lifecycle, no new paper/day/model reruns to rescue.

**Evidence state:** 19 authoring-side offline mocked-source/synthetic unit tests passed. GitHub CI and any *real* Crossref/pinned BTC evaluation are **not yet** validated here. The proposed P1 service/timer are disabled examples. P0's live timer and existing SQLite runtime remain untouched.

**P1 acceptance:** user-reviewed PR; first live Crossref metadata provenance and at most one real pinned spot test (if a title-eligible new DOI is found) producing an immutable report without manual bridging. No title candidate means discovery-only progress and does NOT count as autonomous falsification. No source access => safe stop. If a first real report passes review, stop P1 implementation rather than expand to yet more one-off tests. Open-ended AI mechanism invention remains an unsolved P2 capability.

## P1 first real autonomous cycle — source-fit audit (2026-11-18)

```yaml
research_id: BTC_WEEKDAY_INFORMATION_v1
run_origin: USER_RUN_LOCAL_P1_CYCLE
source_doi: 10.1016/j.frl.2025.108661
source_title: "A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns"
source_paper_target: MONDAY_STOCK_MARKET_RETURNS
frozen_test_target: MONDAY_BTC_SPOT_RETURNS
source_to_hypothesis_fit: FAILED
research_status: STOP_INSUFFICIENT_INCREMENTAL_INFORMATION
four_preregistered_gates_passed: 0
four_preregistered_gates_total: 4
report_relative_path: runtime/agent/reports/BTC_WEEKDAY_INFORMATION_v1.json
report_sha256_user_reported: d7c5963aa73340c1c8f9d8901c511d74ce0dbd9a8dca33ae04657f59d4d0fe99
raw_source_response_independently_inspected: false
full_report_independently_inspected: false
real_spot_recomputed_here: false
p1_automated_execution_path: USER_REPORTED_COMPLETED
p1_scientific_source_relevance_gate: FAILED
p1_unattended_scheduler_enabled: false
p0_seven_day_unattended_acceptance: IN_PROGRESS_NOT_PASSED
trading_allowed: false
holdout_evaluated: false
```

**Facts from user-run CLI:** `quant-research-loop cycle` selected DOI above and automatically wrote an immutable, SHA256-pinned retrospective report. The user-shared CLI summary reported **false for each of the four previously frozen gates**: >=2% relative MSE improvement, positive one-sided paired 14-day block-bootstrap lower bound, 2022/2023 annual sign consistency and beating the zero-return predictor. The full numeric metrics, original Crossref response bytes and historical spot file were not uploaded for independent replication. The user-provided SHA256 is recorded as reported, not independently verified.

**Independent source check:** RePEc/Elsevier bibliographic record for DOI [10.1016/j.frl.2025.108661](https://ideas.repec.org/a/eee/finlet/v86y2025ipes1544612325019154.html) describes **weekend cryptocurrency returns as predictors of Monday equity/stock returns**. The P1 preapproved experiment uses the calendar Monday indicator to predict **BTC's own** returns. Title-cue `classify()` screening accepted a different dependent variable. This is a material source-to-research-scope mismatch; the automated result is **not a falsification of the discovered paper's hypothesis**. The independent, already frozen BTC-Monday incremental-prediction test itself remains a user-reported failure; do not replace the DOI, alter Monday, test another weekday, rerun with a different source, or inspect 2024/2025 to rescue it.

**Decision:** P1's engineering path (external metadata → DOI classification → frozen execution → immutable archive) was demonstrated in one user-initiated real run. **Do not mark the scientific relevance gate or end-to-end autonomous scientific research accepted.** Keep the original archived report bytes and all original logs intact. P1 timer is not reported as enabled; P0 unattended 7-day acceptance remains separate. No new strategy experiments or P1 feature expansion to retune the failed result.

**Next highest-value improvement (separately reviewed future P2):** enforce source *dependent variable, direction and target-market* alignment (ideally abstract-level evidence scope verification) before executing an approved hypothesis template. Add counterexamples such as crypto-weekend → Monday-stock to relevance-gate tests. Avoid claiming this is a model-based or fully general autonomous scientist. STOP further P1 mechanism experiments pending that relevance gate and independent artifact review.
