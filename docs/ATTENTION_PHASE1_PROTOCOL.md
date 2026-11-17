# BTC_ATTENTION_DEMAND_v1 — frozen retrospective incremental-information Kill Test

**Frozen:** 2026-11-17, before using any real 2022–2023 BTC returns in this experiment. This is **not** a strategy backtest, real-time historically accessible search signal, or trading permission.

## Economic mechanism and failure claim

**Hypothesis:** investor attention, proxied by normalized Google Trends Bitcoin *Topic* search interest, might convey incremental information about future BTC spot returns beyond past returns, volatility, and exchange volume. Alternative explanation: attention simply reacts to past price moves or news already in prices.

**Decision:** with the fixed two models below, does the Topic-augmented model improve out-of-sample prediction enough to merit *further research*? A failure stops this exact candidate and prevents after-the-fact choice of keyword, lag, regularization, forecast horizon, or date window.

## Source contracts

- Topic primary: global web search, all categories, entity `/m/05p0rrx`, exported 2020-01-01..2023-12-31; raw SHA256 `99b33105242c99e2b9580de04413c269c38d1988a1fa3a6fd26987d05a341a5f`.
- Search term robustness only: global web search `bitcoin`, same date range, raw SHA256 `8eb882a7984d96bdd4033010263710fc404c0d7add9b77d6d8181a4f82d6e8fe`.
- Keep 208 full Sunday-start weeks, 2020-01-05..2023-12-24; ignore the boundary weeks starting 2019-12-29 and 2023-12-31. Values are normalized 1..100 indexes, **not search counts**.
- BTC spot: Binance BTCUSDT daily local CSV `day,open,high,low,close,volume`, covering 2020-01-01 through 2023-12-31. The loader reads/validates ONLY this prefix and breaks before consuming 2024 prices. Pins the canonical full 2020–2023 OHLCV digest `fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def` from the prior local Phase 1 BTC research report.
- `volume` means **BTC base-asset volume**, not quote-USDT turnover or exchange-wide trading activity. Weekly volume is the 7-day sum.

## Causal timing and target

A Google Trends row labeled Sunday W summarizes Sunday..Saturday. For target week W, use only features through **week W−2**, leaving all of W−1 as a complete-publication buffer. The target is the *following distinct week* BTC weekly close-to-close log return, using the Saturday UTC daily close in each complete week: `log(SatClose[W]/SatClose[W−1])`.

Neither Google Trends full-range retrospective indexes nor their historical publication timestamp have been verified as **point-in-time available**. A one-week buffer prevents a structural same-week timestamp leak but **does not solve historical normalization, sampling, or revisions**. Any result is restricted to retrospective statistical association.

## Frozen comparison; no post-result parameter changes

- **Training/calibration:** target weeks fully completed by 2021-12-31, after the warm-up needed by lagged features. Do not fit with a target that ends in 2022. Standardization means/SDs and all model coefficients fit *once* here.
- **Evaluation:** 2022-01-02..2023-12-24, **104 full weeks** (52 per year); do not refit or select on these outcomes.
- **Baseline:** standardized fixed ridge regression (unpenalized intercept, L2 lambda `10`) on 1-week BTC log return, 4-week realized sample SD of weekly returns, and `log(weekly BTC base volume / mean volume of previous 4 weeks)`, all computed as of W−2.
- **Topic-augmented:** identical estimator/training rows, add exactly one feature `log(topic[W−2]/topic[W−3])`. Log ratio is invariant to a global multiplicative Trends normalization **except for integer rounding**; it still cannot remove historical revision/selection bias.
- **Search term robustness:** same model as Topic, but replace Topic log ratio with `log(term[W−2]/term[W−3])`; *never* select whichever improves MSE more.
- **Reference sanity check:** fixed `0` weekly return forecast; the augmented model must beat its evaluation MSE.
- **Metrics:** mean squared prediction error (MSE) on the same future weekly BTC log returns, and event-paired weekly MSE gain `baseline_squared_error − augmented_squared_error`. Report overall plus 2022 and 2023 separately.

## Prespecified gate and stop rule

**Pass retrospective information only** iff ALL criteria hold:

1. Topic MSE reduction relative to baseline at least **5%** overall.
2. One-sided **95% lower** bound of paired MSE gain (2,000 fixed-seed circular 4-week block bootstrap draws, seed `20261117`) **strictly > 0**. Bootstrap re-samples evaluation errors for uncertainty, not model fitting.
3. Topic MSE gain > 0 **in both 2022 and 2023**.
4. Topic model evaluation MSE < the zero-return comparator's MSE.
5. Search-term augmented model has **positive overall** MSE gain vs the same price-only baseline; this is a conservative, explicitly predeclared robustness veto, not a second alpha source.

If any gate fails: `STOP_INSUFFICIENT_INCREMENTAL_INFORMATION`; do not rescue by switching to Search term, changing model class/penalty, lags, controls, horizon, or calibration split. Passing yields `PASS_RETROSPECTIVE_INCREMENTAL_INFORMATION_ONLY`, **not investability**.

### Bounds and limitations

- Only about 104 evaluation target weeks; residual serial dependence and regime changes are possible; bootstrap lower bound is an approximate uncertainty diagnostic, not a guarantee.
- The 0–100 data are **post-period exports** queried using a full 2020–2023 search range, not point-in-time snapshots; no positive result can justify account simulation, strategy P&L, or claims of historically live-available signals.
- All inputs must match the pinned hashes; each rerun is deterministic and outputs an immutable JSON report. No 2024/2025 data use and no trading permissions.
- A later strategy test would need truly contemporaneously available attention data, independent validation, costs, exposure/risk matching, and owner review; this PR does not authorize one.
