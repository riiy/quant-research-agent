# Quant Research Agent — BTC Daily MVP

A **research-only** experiment loop: source-grounded hypothesis discovery → preregistered rules → checksum-verified Binance BTCUSDT 1d candles → fixed next-open spot backtest → development/validation cost checks → report and SQLite archive. The 2025 holdout is explicitly gated and can be evaluated **once**, only for a candidate passing the 2024 screen.

**No broker/exchange trading APIs, keys, order generation, live trading or account-simulation permissions.** Neither a profitable backtest nor a passed holdout grants trading permission.

## Design decisions

- Hypotheses come from a **curated evidence note**, currently [Moskowitz, Ooi & Pedersen (2012)](https://doi.org/10.1016/j.jfineco.2011.11.003). The paper concerns futures, **not BTC spot**; BTC transfer is an unproven hypothesis.
- In `api` mode, the LLM selects **one candidate** in a fixed strategy grammar (`sma`, `momentum`, `breakout`) with hard parameter limits and a known source ID. It cannot author code, choose URLs, modify data or change the evaluation contract. This is **constrained discovery**, not autonomous Internet literature search.
- In `seed` mode the candidate is deterministic and is labeled **demo, not AI-discovered**. Unverified CSVs are also demo-only.
- Split is **2018–2023 development / 2024 validation / 2025 sealed holdout**. The final holdout is *not* touched by `run-once`, and only eligible candidates may be `finalize`d once. No hyperparameter grid search, no auto-tuning, no repeated final-test queries.
- Signal is calculated through **yesterday's close** and filled at **today's open**. Spot-only, long or cash; one asset, no leverage. Both strategy and buy-and-hold comparator pay fees and slippage. Fee 0.10%/side and assumed slippage 0.05%/side; doubled in the stress check. Each split resets to cash, with pre-split close history for indicators only.
- Ingestion uses monthly `.zip` and Binance `.CHECKSUM`, handles 2025 microsecond timestamps, refuses incomplete months, missing dates, invalid OHLC and altered manifests. The source data and SHA256 are recorded per experiment.

## Setup (Python 3.11+; standard-library runtime)

```bash
git clone https://github.com/riiy/quant-research-agent.git
cd quant-research-agent
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

Prepare genuine historical data (downloads BTCUSDT daily archives for every complete month):

```bash
quant-agent ingest --from 2018-01 --to 2024-12
```

Add an **independent billed OpenAI API key** (ChatGPT Plus does not include API usage). Use your provider's hard spend cap: `QUANT_MAX_API_CALLS_MONTH` is a *call-count* ceiling, **not** a money limit, and does not restrict token charges or third-party provider billing. Default is 20 requests per UTC month.

```bash
export OPENAI_API_KEY='...'
export QUANT_MODEL='gpt-6-luna'
export QUANT_MAX_API_CALLS_MONTH=20
quant-agent run-once --mode api
quant-agent candidates
quant-agent report --latest
quant-agent status
```

To use the 2025 sealed test **only if the experiment's status is `PENDING_SEALED_HOLDOUT`**, first extend the dataset and then make an explicit one-time call:

```bash
quant-agent ingest --from 2018-01 --to 2025-12
quant-agent finalize <run_id>
```

Previously stored pre-2025 prices are checked byte-equivalently at the canonical-bar level. If changed, finalization fails. Holdout results are archived, not recycled into parameter search.

### API gateway compatibility

The request sends Responses API `input` as a **list of user messages**. Official
OpenAI accepts either a string or an array, but some LiteLLM ChatGPT adapters
reject strings with `Input must be a list`. The user message also includes
an explicit five-key candidate contract for gateways that silently drop
`instructions` or `text.format` (structured output). A response with exactly
`{"candidate": {...}}` can be safely unwrapped; any other missing or unexpected
fields fail with key names (never the raw model text). No silent parameter
defaults, arbitrary field removal, or automatic paid retries are performed.
If field errors persist, check that the gateway supports Responses structured
output or use the official paid OpenAI API endpoint. ChatGPT Plus is not API credit.

### New evidence-first idea funnel (v2, independent of the accepted backtest)

This optional discovery upgrade keeps the accepted execution engine frozen. It
uses a **fixed, human-reviewed registry of six published papers** (source IDs,
DOI links, study universes, findings and transfer limitations). It does **not**
scrape the live Web or claim that a paper proves BTC alpha. A deterministic
economic-mechanism gate runs *before* any paid API request:

- `trend_persistence` (SMA, momentum and breakout variants): **blocked** after
  the archived BTC 120-day trend result. Legacy `quant-agent run-once --mode api`
  now refuses to buy further trend-parameter proposals when a real trend
  experiment exists; seed-mode integration tests remain possible.
- `liquidity_reversal`: **blocked** for BTC-only research. Zaremba et al.
  and Bianchi et al. find reversal mainly in less liquid cryptocurrency
  cross-sections, not strong supporting evidence for BTC spot reversal.
- `attention_demand`: **blocked** until independent Google search-volume data
  exists and its timestamp availability is verified.
- `volatility_exposure`: **eligible for one new research idea** using daily
  OHLCV. Moreira and Muir studied volatility management outside BTC; this
  is **transfer-only evidence**, not BTC alpha proof. The alternative
  comparator must explicitly control for reduced market exposure.

No new signal family or trade execution has been implemented. A generated
idea is **AWAITING_RULE_DESIGN_NOT_BACKTESTED**, never a validated strategy.
One idea per economic mechanism is stored in `runtime/ideas.sqlite3` with
the sources, fixed comparison, falsifier, evidence-scope grade and model
usage. Renaming a trend setup or tweaking its lookback does not reset
novelty. When no viable untested mechanism remains, the command stops
**before API billing** rather than endlessly proposing variants.

```bash
# No API, no BTC data required
quant-ideas sources
quant-ideas preview
quant-ideas discover --mode seed

# At most one paid hypothesis for the currently eligible mechanism
quant-ideas discover --mode api
quant-ideas list
```

The new idea generation shares the existing `QUANT_MAX_API_CALLS_MONTH`
reservation counter and same `OPENAI_API_KEY` / `QUANT_MODEL`. Limits on API
request counts are not currency spend caps. Use an upstream provider hard
spend limit. The demo does not consume the unique mechanism. Idea records
are separate from existing strategy experiments; **no 2025 holdout or
trading permission is touched**.

The source registry is curated from the published abstracts; it is **not a
general literature-review agent**. The 0–6 screening score is a deterministic
triage aid for evidence fit, data feasibility and novelty, **not** a likelihood
of alpha. Do not implement the volatility idea unless its proposed rule,
risk/exposure-adjusted comparator, and kill test are explicitly reviewed
and frozen beforehand.

### Bounded volatility mechanism Kill Test (no strategy/backtest)

For the **already generated** idea `4b7cb9282852`, run one fixed
mechanism diagnostic before implementing trading rules. This command
does **not** make model calls, run `backtest.simulate`, modify
`ideas.sqlite3`, calculate transaction P&L, or use any 2024/2025 data.

```bash
quant-ideas kill-test --idea-id 4b7cb9282852
# Optional: --data runtime/data/BTCUSDT-1d.csv
```

- Uses **only 2018-01-01 through 2023-12-31** from the daily CSV.
  The loader stops after 2023-12-31 even if later rows are present.
- **Calibration**: calculate the standard deviation of 30 completed
  close-to-close log returns; freeze the median of the signals dated
  2018-01-31 through 2020-12-31.
- **Mechanism test**: for dates 2021-01-01 through 2023-12-31,
  classify each next-day close-to-close log return using the trailing
  30-day volatility *known after the previous close*.
- Primary measure: mean **absolute next-day log return** in higher-vol
  versus lower-vol regimes. A meaningful conditional-risk relationship
  requires a high/low ratio >= **1.20**, a one-sided 95% lower bound
  above 1.0 from a **fixed-seed 14-day block bootstrap** (1,000
  replicates), and at least **100 daily observations** in each regime.
- Compensation veto: the high-vol regime must *not* have a higher
  mean log return per unit mean absolute log return than the low-vol
  regime. Both measures and sample counts are reported. These are
  **screening rules chosen in advance**, not estimated alpha or a
  formal BTC risk premium model.
- Outcomes are `STOP_INSUFFICIENT_MECHANISM_EVIDENCE` or
  `PASS_MECHANISM_GATE_ONLY`. A pass allows discussion of a fixed
  rule and separately predeclared, fee-adjusted exposure-matched
  backtest; it is **not** such a backtest or authorization to trade.
- Writes an immutable JSON report to
  `runtime/ideas/<idea_id>_volatility_mechanism_kill_v1.json`,
  recording the exact protocol, 2018–2023 OHLCV prefix hash, threshold,
  conditions and observations. Repeating the command with identical
  data is safe; a changed report is refused rather than overwritten.

The 2021–2023 evaluation segment is a chronological split **within
the previously studied 2018–2023 development years**, not a fresh
project-wide out-of-sample set. Results do not establish BTC alpha
or validate the Moreira–Muir transfer. Because no trades are modeled
here, there is no fee/slippage or exposure-matched strategy comparison;
those belong to a later, separately approved backtest **only if**
the mechanism gate passes. An inconclusive/failing gate should stop
this idea rather than trigger lookback/threshold adjustment. The idea's
database status is deliberately left unchanged pending human review.

### Funding pressure: Phase 0, data audit only

`BTC_PERP_FUNDING_PRESSURE_v1` is a distinct economic-mechanism lead, **not** a new execution strategy. It uses the official Binance USD-M perpetual BTCUSDT **settled funding** history, not the spot klines or live open interest. Settlement data are not a direct leverage measurement.

```bash
pip install -e .
quant-funding audit
# Later, if the official ZIPs are already cached:
quant-funding audit --offline
```

The command downloads the fixed **2020-01 through 2023-12** monthly fundingRate ZIP/CHECKSUM pairs from `data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/`. Source CSV columns must be `calc_time,funding_interval_hours,last_funding_rate`; the REST endpoint `/fapi/v1/fundingRate` has *different* field names (`fundingTime,fundingRate`). Every source ZIP SHA256 is checked before reading. The audit expects **4383** 8-hour settlements over 1461 days at nominal 00:00/08:00/16:00 UTC slots. **Audit v2** maps each raw millisecond timestamp to its nearest nominal slot **only for coverage diagnostics**, allowing an explicitly documented **0–100 ms positive offset**. It rejects negative or >100 ms offsets, missing/duplicate nominal slots, duplicate raw timestamps, out-of-order events, and unexpected funding intervals. The raw `calc_time` is never rewritten or treated as knowable before settlement/publication. Unexpected history is a failed gate, not permission to fill or deduplicate.

Local results: `runtime/funding/BTCUSDT-funding-2020-2023.audit.v2.json`, `runtime/funding/BTCUSDT-funding-2020-2023.v2.csv` (canonical CSV **only if** audit passes), and `runtime/funding/archive/` original ZIP/CHECKSUM files. **The original `.audit.json` v1 failed report is preserved** as immutable diagnostic evidence. V2 snapshots are also immutable: if files change, the command stops instead of overwriting previous results. No trading/backtest, model call, API key, 2024 or 2025 market data access.

**Evidence limit:** [Kim (2026)](https://doi.org/10.1016/j.jempfin.2026.101779) reports funding-rate information for future Bitcoin **volatility**, not a proven directional return effect. Phase 0 only checks the data. A separate, reviewed Phase 1 could freeze positive-funding extremes on 2020–2021 and test 2022–2023 post-settlement spot behavior versus trailing-return/volatility controls. Do not proceed if the data gate fails.

### Offline smoke test

Run **without** API access, on real downloaded data or on your own continuous CSV. The result is intentionally marked as a seeded demo and **not** as automatic discovery:

```bash
quant-agent run-once --mode seed
# Or: quant-agent run-once --mode seed --data path/to/sample.csv
```

`--data` local CSV columns: `day,open,high,low,close,volume`, UTC daily, chronological, covering every day from 2018-01-01 through 2024-12-31. When no verified manifest is present, it is explicitly labeled `unverified-local-csv`. Experiment results are not committed to Git.

### Commands

```text
quant-agent ingest [--from YYYY-MM --to YYYY-MM]
quant-agent run-once [--mode api|seed] [--data PATH]
quant-agent finalize RUN_ID [--data PATH]
quant-agent status
quant-agent candidates
quant-agent report --latest
quant-agent pause
quant-agent resume
# All accept --home PATH before the subcommand.
```

The default state root is `./runtime` (override with `QUANT_HOME`). It contains the cached archives, verified CSV/manifest, `research.sqlite3` and Markdown/JSON reports. `PAUSED` prevents new research runs. Fingerprints deduplicate identical rules, ignoring title rewordings. No artificial positive-result threshold can turn a candidate tradable.

## Automation and safety

`deploy/` contains example systemd service/timer unit files, **not enabled by installation**. Set up a dedicated unprivileged OS user, protect `/etc/quant-research-agent.env` (`0600`), ensure runtime write permission, and test manual runs first. The timer can otherwise repeatedly incur model costs. The core does not execute generated source code or launch Docker: the experiment grammar is safer and cheaper than unrestricted autonomous code execution in this first MVP. GPU acceleration is unnecessary for the daily loop.

### Limitations and stop condition

This MVP does not discover papers from the live Web, optimize trading costs using order books, calculate bootstrap confidence intervals or prove statistical alpha. An early 2024 screen and one 2025 holdout cannot establish stable reproducible excess return. If research repeatedly produces no economically credible hypotheses, stop rather than expanding infrastructure or tuning filters. No historical strategy already archived in the parent Trading Research project is reopened.
