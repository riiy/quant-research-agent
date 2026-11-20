# ABSTRACT_EVIDENCE_ENRICHMENT_V1 — DOI-matched evidence with explainable scope decisions

**Status:** separately reviewed PR; no live API access or local 15-paper result is claimed by the implementation alone.

## Decision goal

Fix the real P1 failure: a paper about **weekend cryptocurrency returns predicting Monday equity returns** was mistakenly used to justify an experiment about **BTC's own Monday returns**. The earlier `BTC_WEEKDAY_INFORMATION_v1` was STOP/ARCHIVED and **must not be rerun**. The aim of this change is to improve evidence **selection and scope recognition**, not to authorize a second calendar experiment.

## Inputs and source trust

- Read **only the current P1 SQLite DOI registry** and verify each DOI against original immutable Crossref `crossref-poll-*.json` and its SHA256 before planning. No new paper is invented, no previously archived study/SQL row is edited.
- At most **5 DOI records per manual enrichment batch**, at most **one claimed batch per UTC calendar day**, at most **2 HTTPS requests per DOI** (10 total). A claim is written *before* external I/O; the next attempt skips previously claimed DOIs and will not rescue a crash by automatically resending requests.
- First: `https://api.crossref.org/works/{encoded DOI}` — publication metadata deposited with Crossref. Its optional `abstract` field is not assured.
- Fallback only if Crossref does not provide an abstract: `https://api.openalex.org/works?filter=doi:<DOI>&per-page=1&select=doi,title,abstract_inverted_index`. OpenAlex may not have an abstract; its **indexed** abstract is reconstructable only when all word positions are well formed.
- Both responses are **metadata services**, not guarantees of peer review, validity, author intent, or current full-text publication. We verify DOI equality, plausible title overlap, source host, no redirect, size/timeout bounds, original API response hash, UTC retrieval timestamp, and archive the raw JSON separately. OpenAlex is a secondary index, not publisher attestation. Missing, ambiguous or conflicting sources => human review.
- **No LLM API**, arbitrary URLs, generated commands, full-PDF scraping, broker, sealed 2024/2025 access, trade, new strategy report, or reuse of the archived BTC Monday Kill Test. The original P0 timer remains unchanged. No new P1 timer is installed.

## Structured analysis

For each DOI, report title, reconstructed source type, source SHA256/path and exact matching snippets (capped short quotes) for:

- `target`: **dependent variable** (BTC vs stock/equity; direction matters);
- `predictor`: weekday/Monday *calendar indicator* vs lagged weekend crypto returns, other markets, macro or generic calendar scope;
- `market`: BTC derivatives vs BTC with spot type **unverified** vs equities;
- `frequency`: daily/weekdays, hourly/intraday or unresolved;
- `direction`: cross-market crypto-to-equity versus potentially known-before-return calendar predictor;
- `decision`, `why`, `unknowns`, `abstract_source`, and evidence field-level quotes.

The report **never** emits a license to execute an experiment, or asserts a source is scientifically correct. Even `TOPIC_RELATED_PROTOCOL_REVIEW` does not establish exact model equivalence, data timing, costs, out-of-sample independence or an investable anomaly. Ambiguity => `NEEDS_HUMAN_SOURCE_REVIEW`.

This is intentionally a **high-precision, constrained rule-based explainer**. It does not solve arbitrary scientific semantic inference. The long-term project needs general independent mechanism synthesis; do not claim that is achieved here.

## Commands (after reviewer approves PR)

Run using the repository's existing runtime, **without deleting** `runtime/agent/autonomous_loop.sqlite3` or the original report:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v

# Offline dry-run; checks original evidence integrity; no network or studies
quant-research-loop --home runtime evidence-plan --max-papers 5

# Explicit opt-in; <=5 DOIs, Crossref first / OpenAlex fallback, <=10 requests
quant-research-loop --home runtime evidence-enrich --max-papers 5

# The original study remains byte-identical
sha256sum runtime/agent/reports/BTC_WEEKDAY_INFORMATION_v1.json
# expected d7c5963aa73340c1c8f9d8901c511d74ce0dbd9a8dca33ae04657f59d4d0fe99
```

The resulting `runtime/agent/reports/abstract-evidence-v1-<hash>.json` is immutable and includes all available source fields and reasons. DOI SHA256 keys are safe filenames. Raw API JSON lives under `runtime/agent/evidence_enrichment/raw/`. `.json` claim markers under `runtime/agent/evidence_enrichment/claims/` are **do-not-retry guards**, not an external scheduling approval. If the request fails or OpenAlex lacks an abstract, record uncertainty and stop. Do not broaden the source list or edit the DOI to manufacture a positive paper.

**Quality gate / stop condition:** Check at most the first 5 high-relevance existing DOIs against their original recorded title, verify all new source hashes, ensure the known crypto→stock mismatch stays `REJECT_TARGET_MISMATCH`, and confirm true BTC calendar papers receive useful evidence while hourly and generic-calendar papers do not falsely get automatic experiment permission. If the method cannot extract dependable directional information, stop and mark `INSUFFICIENT_ABSTRACT_EVIDENCE`; **no model/backtest rerun**. Further expansion requires evidence that source selection quality materially changes decisions.
