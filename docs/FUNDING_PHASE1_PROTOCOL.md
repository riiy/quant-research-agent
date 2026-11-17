# BTC_PERP_FUNDING_PRESSURE_v1 — Phase 1 mechanism Kill Test

**Frozen protocol:** `BTC_PERP_FUNDING_PRESSURE_v1_mechanism_frozen_2026-11-17`  
**Research-only. No trade strategy, strategy backtest, account simulation, broker order, or 2024/2025 data access.**

## One question / economic mechanism

Does **extreme positive BTCUSDT USD-M perpetual funding** contain incremental information about **lower future BTC spot returns or greater next-day downside probability**, beyond BTC's own lagged 7-day returns and 30-day realized volatility? The proposed mechanism is potential long-side perpetual positioning pressure. Funding is a *proxy for premium/carry/demand*, **not** a direct measurement of open interest, leverage, or liquidations. Existing cited work on funding and BTC volatility is not proof of directional cash/long alpha.

This is the **first** test of this mechanism in this project. Do not reframe rejected BTC trend/momentum or volatility-managed long/cash families.

## Source, provenance, and causal alignment

1. Funding: the exact, passed Phase 0 Binance canonical CSV `runtime/funding/BTCUSDT-funding-2020-2023.v2.csv`, with SHA256 `159050d8818298c777f9ac1290530aecc01a01859d209df9d39c306a4b5eb977`. Require passing `audit.v2.json` of protocol `BTC_PERP_FUNDING_PRESSURE_v2_timestamp_jitter_audit_2020_2023` and all 4,383 unique 8h settled events. **Do not download, resample, or silently repair data in Phase 1.** Daily funding = arithmetic mean of the day's three **settled funding rates** (in original rate units), not cash paid by a position.
2. Spot: existing local BTCUSDT `runtime/data/BTCUSDT-1d.csv` with `day,open,high,low,close,volume`. Parse/validate a continuous 2020-01-01–2023-12-31 **prefix only**, stop on 2023-12-31, and record a canonical SHA256 for the 2020–2023 OHLCV rows. No 2024 or 2025 price values can be loaded.
3. For the evaluated outcome on UTC day **t**, calculate **all** funding and price controls through UTC day **t−2** only. This deliberately discards the immediately preceding day to make the available-information cutoff conservative despite lack of exact funding publication timestamps. The measured outcome is `log(close[t]/close[t−1])`; it must not enter any feature. This **does not** assert that funding was published immediately at its raw settlement timestamp.
4. 2020-01-01–2021-12-31: calibration. 2022-01-01–2023-12-31: frozen mechanism evaluation (**730 days**). The latter is a chronological split of **already-used project development years**, **not** pristine project-level OOS or the sealed 2025 holdout.

## Frozen signal and price-only comparator

- Calculate the **nearest-rank 90th percentile** of the **daily mean** funding values on all 731 days of 2020–2021. An event occurs when the *t−2* daily mean funding is **strictly greater** than that threshold; threshold must be >0. Do **not** change percentile, daily aggregation, direction, return horizon, or lag based on observed results.
- For the t−2 spot close calculate (a) `log(close[t−2]/close[t−9])` (7-day historical return), and (b) the sample standard deviation of the previous 30 daily close-to-close log returns ending t−2. Both controls are available at the signal cutoff and contain **no** outcome observations.
- Fit **tercile boundaries only on 2020–2021 calibration price features**, using fixed nearest-rank percentiles at 1/3 and 2/3. On 2022–2023 test days, assign a fixed **3 × 3** (7-day return × 30-day volatility) price-control stratum, **crossed with calendar year**. Year matching prevents a 2022 bear-market effect from masquerading as incremental funding information. Within each year/price stratum, compare extreme-positive funding event days to contemporaneous non-event days. Weight stratum event-minus-control differences by the proportion of actual extreme events in that stratum. This is an **observational, retrospective** matched diagnostic: non-event outcomes in the test window are used to describe differences, **not** to set an investable baseline.

## Endpoints, multiple testing, and rejection criteria

Two *predeclared* directional endpoints (either may pass), with **Bonferroni one-sided 2.5% alpha each** and 1,000 deterministic paired 14-calendar-day circular-block bootstrap replicates (seed 20261117); require at least **950 valid bootstrap replicates**:

1. **Primary economic endpoint, weaker subsequent returns:** adjusted event-minus-control next-day **mean log return ≤ −0.003 (−30 basis points)** and the bootstrap **97.5% one-sided upper bound < 0**.
2. **Secondary risk endpoint, more frequent downside:** adjusted event-minus-control probability of next-day log return **≤ −0.02** is **≥ +0.05** (five percentage points) and the bootstrap **97.5% one-sided lower bound > 0**.

The selected endpoint must also have the **correct directional sign in each evaluation calendar year** (2022 and 2023 separately); not required to be statistically significant in each individual year.

**Minimum effective support:** ≥40 extreme event days total, ≥10 in **each** of 2022 and 2023, spanning ≥8 distinct non-overlapping 14-day calendar blocks. Every event year/price stratum must have ≥10 contemporaneous non-event comparator days. If any support condition fails, stop rather than retune the threshold or pool away missing controls. No imputation, event dropping, or strategy simulation. The fixed 14-day block length is a rough serial-dependence screen, **not** a universally valid statistical guarantee; these tests are diagnostic, not causal proof.

**Outcome statuses:**

- `PASS_INCREMENTAL_INFORMATION_ONLY` only if at least one endpoint satisfies *all* relevant requirements; passing does **not** authorize a strategy, trade, lookahead, or alpha claim. Separate risk-/exposure-/cost-matched strategy protocol requires a distinct review.
- `STOP_INSUFFICIENT_INCREMENTAL_INFORMATION` if sample, overlap, stability, economic effect or uncertainty conditions fail. **Archive the mechanism**; do not retry with funding quantiles, horizons, controls or return signs changed.
- Input provenance/time-validation errors fail closed with no result file and **no** mechanism conclusion; investigate genuine data faults only.

The report is an immutable local JSON `runtime/funding/BTCUSDT-funding-phase1-mechanism-v1.json`, recording thresholds, all gates, observations, annual effects, both endpoints, CIs, and funding/spot data hashes. This module neither modifies any research database nor calls the backtester. Never use the 2024 period or the sealed 2025 holdout for this candidate during the mechanism gate.
