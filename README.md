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
