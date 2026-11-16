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
reject strings with `Input must be a list`. This client-side fix addresses
that request shape only. Older LiteLLM adapters may also silently drop
`text.format` (structured JSON output); if the response is not valid JSON,
prefer the official paid OpenAI API endpoint or upgrade/fix the gateway
instead of weakening the research schema. ChatGPT Plus is not API credit.

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
