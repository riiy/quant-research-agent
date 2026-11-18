# AUTONOMOUS_RESEARCH_LOOP_v1 — bounded evidence-to-falsification P1

**Status:** PR implementation, offline tests only until reviewed. Research only. No automatically generated Python, live trading, account simulation, P&L, sealed holdout, model API or arbitrary network browsing.

## Decision goal and stop rule

North Star: Human approves goals, sources, spending and methods; the Agent discovers independent economic evidence, screens novelty, executes a predefined falsifiable experiment, archives the answer, and schedules subsequent discovery.

P0 already handles unattended task control. This P1 is **a separate prototype**, not a replacement of the user-deployed P0 service. It is deliberately *not* a general literature-reading agent: it handles one bounded external source (Crossref DOI **metadata**) and exactly one frozen independent mechanism template (BTC weekday/Monday incremental predictive information). If the paper's **title alone** is insufficient to categorize the mechanism, it is stored for review, not treated as causal evidence. It can finish one research cycle without human handoff provided a pinned local 2020–2023 spot CSV exists. Repeated new papers do not trigger repeated tests of the same calendar hypothesis.

**Why this template:** calendar/weekend market activity has a different proposed economic channel from the archived momentum, realized-vol-exposure, perp funding and investor attention research. Calendar-dependent participation/liquidity could show up in BTC returns but **no historical BTC alpha is presumed**. Choosing Monday as a single predeclared calendar comparison avoids searching seven weekdays for an anomaly. An individual Crossref title does not necessarily support a Monday effect; it is a hypothesis cue, not an empirical endorsement.

## The single fixed autonomous cycle

```
Human freezes deploy/quant-research-loop.policy.example.json
            |
P1 cycle (operator-authorized, <=1 request per UTC day)
            |
HTTPS Crossref metadata search; exact hardcoded host/query/fields
            |
Save unmodified raw JSON to runtime/agent/evidence/ + SHA256
            |
Normalize and deduplicate DOI, title, publication year
            |
Title cue: crypto + calendar/weekday/weekend + return-related words
            |
Nonmatch -> REFERENCE_ONLY_NEEDS_REVIEW (no experimentation)
First eligible DOI ever -> freeze template_id (one study maximum)
            |
Use *already existing* pinned BTC 2020–2023 spot OHLCV
            |
Frozen deterministic mechanism test, no dynamic parameter changes
            |
STOP/ARCHIVED or PASS_RETROSPECTIVE_MECHANISM_ONLY/NEEDS_HUMAN_REVIEW
            |
Immutable source hash + prediction gates + research report / SQLite
            |
Next day: new metadata, but no second test of same mechanism
```

Source: [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/). Query uses `query.bibliographic`, `rows=20`, `filter=type:journal-article`, `select=...`. The title filter is **not** scientific claim verification, only a low-cost screening cue. A DOI registry entry is not a quality guarantee; contradictory findings, data overlap and peer review require human scrutiny. There is no full-paper text ingestion and no ML-generated bibliographic claim. **“New evidence” means new to the local agent's DOI store, not necessarily newly published.** The API returns relevance-sorted *bounded* results, not exhaustive discovery of all recent papers; this limitation is explicitly in scope.

Hard limits: one network request per UTC day; at least 24 hours between polls; maximum 20 metadata records, 1 MB response, 15-second timeout; no retries until next eligible day on source failure. One template for life of the P1 database, exactly one DOI selected by the response's relevance order before inspecting historical outcomes. A new approved P2 protocol is required for a different category/template. URL and protocol/spot paths are not configurable through generated text. The source bytes, DOI, title, publication year, response digest, result, and source observation time are persisted. `runtime/agent/autonomous_loop.sqlite3` is separate from the live P0 `orchestrator.sqlite3`.

## Frozen test: BTC_WEEKDAY_INFORMATION_v1

**Measured hypothesis:** Does a known-in-advance Monday indicator improve the *future daily BTC spot close-to-close log return* forecast beyond lagged price return, 30-day realized volatility and relative BTC base-asset volume? It does not test net trading returns, causality, monetary flows, or source paper reproducibility.

- **Data**: BTCUSDT spot 1d, UTC, exactly 2020-01-01 .. 2023-12-31; the same already frozen **2020–2023 canonical prefix SHA256** `fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def`. Loader breaks after 2023-12-31 **without parsing 2024/2025 values**. Missing/gapped/altered data => no valid evaluation and an explicit failed review state.
- **Calibration**: all eligible 2020-02 and subsequent target days through 2021-12-31. **Evaluation**: all 730 target days of 2022–2023 (365 days/year). Regression coefficients and standardization frozen using calibration labels only. The source DOI may be published after the evaluation period and may itself study overlapping dates: results are **retrospective mechanism screening only**, *not* independent historical point-in-time discovery.
- **Price-only baseline**: return through day `t−2`, standard deviation of the preceding 30 completed daily returns through `t−2`, volume of day `t−2` versus prior 30-day mean (log1p ratio). Extra input in augmented model: **Monday dummy for target calendar day t**, known before t, **not selected from winning weekdays**. No outcome or market feature from t or t−1 used.
- **Model**: standardized ridge, intercept unpenalized, L2 lambda **10** frozen, identical solver for baseline and augmented. No model tuning, no separate lookback grid.
- **Decision**: four *AND* gates, fixed before first real run: ≥**2%** relative OOS MSE reduction vs baseline; paired circular **14-day** block bootstrap (**1000** repetitions; one-sided 95% MSE gain lower bound **>0**); gain positive in **both** 2022 and 2023; augmented model beats the **zero-return predictor**. Failure => `STOP_INSUFFICIENT_INCREMENTAL_INFORMATION`/`ARCHIVED_NON_TRADABLE`; pass => `PASS_RETROSPECTIVE_MECHANISM_ONLY`/`NEEDS_HUMAN_REVIEW`. The 2% threshold is a *materiality screening choice*, not economically proven alpha.
- **Never authorized**: backtesting a weekday trading strategy, stops/entries, capital simulation, fees/P&L, opening the sealed 2024/2025 holdout, adding winning day variants, re-running with a second paper, or inferring that published seasonal anomalies are tradable.

## Developer and operator smoke (do not enable a new timer yet)

Run from the feature branch in the existing `/home/riiy/quant-research-agent` repository, **without overwriting the existing runtime**, after code review:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
mkdir -p runtime
cp deploy/quant-research-loop.policy.example.json runtime/research-loop.policy.json
quant-research-loop --home runtime status
# This next command DOES make one new public HTTPS metadata request
# and CAN run the ONE preapproved research-only Kill Test if data are pinned.
quant-research-loop --home runtime cycle --policy runtime/research-loop.policy.json
quant-research-loop --home runtime status
```

If the API is unreachable: `STOP_SOURCE_UNAVAILABLE`, with an audit row and **no immediate retry**. If a relevant title is found but pinned spot file is missing: `BLOCKED_MISSING_SPOT` with a pending study (does not waste another Crossref call when file later appears). If a frozen study fails the data fingerprint or model calculation: `FAILED_REVIEW_REQUIRED` (never automatically rescued or rerun). If results are valid: immutable `runtime/agent/reports/BTC_WEEKDAY_INFORMATION_v1.json` with explicit gate outcomes. No matching paper: `EVIDENCE_ARCHIVED_NO_NEW_EXECUTABLE_STUDY`, not a false negative result.

The P0 hourly `quant-orchestrator.timer` stays unchanged. Only after separate PR review and manual smoke should an operator **choose** to enable a separate daily P1 service/timer; `deploy/quant-research-loop.service` and `.timer` are examples, **not auto-enabled**. Their `User` and paths assume the existing `/home/riiy` host and require local review; do not install into another machine without adapting. Both loops share only the `runtime/PAUSED` marker; their SQLite stores and tasks are separate. P1 requires Internet to one HTTPS API; P0 needs none.

## P1 acceptance, evidence needed, and stop condition

1. Automated tests and CI green, plus manual first real Crossref cycle produces a complete recorded source hash and DOI/title archive. No invented research, no malicious URLs, no duplicate network or candidate evaluation.
2. A **new-to-local-registry, title-eligible** Crossref DOI plus the pinned original BTC spot CSV leads *without manual bridging* to exactly one real frozen report, reproducibly archived with status STOP or PASS_MECHANISM_ONLY. **A missed title cue cannot count as a completed falsification.**
3. If Crossref has no eligible paper, report evidence discovery only; do **not** fabricate a completed end-to-end test. A capped test fixture proves code-path capability but is not a real autonomous success.
4. All 2024/2025 data remains untouched, zero model payments, zero trading calls; repeated cycles add evidence but never retune/repeat the one evaluated mechanism.
5. If the first real report is archived and source+model behavior is demonstrated, **stop P1 scope expansion**; the next reviewed iteration may open additional research templates and improve semantic classification. If this narrow mechanism can't reasonably be supported by available source metadata, stop and report that limitation rather than adding arbitrary filters.

Do not confuse a successful CI check with a successful live autonomy experiment. Results must be reviewed and `STATE.md` updated only after real host execution evidence.
