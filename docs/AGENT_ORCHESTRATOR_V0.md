# AGENT_ORCHESTRATOR_v0 — bounded, auditable control loop

**Status:** Implementation proposed for review. **Not** a deployed autonomous research system, unrestricted research author, independent evidence searcher, strategy backtester or trading service.

## Mission and boundary

**Long-term mission:** Human sets the research objective, budget, safety boundaries and the allowed research methods; the agent discovers, executes, falsifies, archives and iterates continuously **within** those bounds.

**This PR's P0 control milestone:** A deterministic, durable scheduler tick and approval ledger. **No automatic new strategy research** is authorized in v0. Today's previously researched trend, volatility-exposure, funding-pressure and attention-demand candidates remain archived. Avoid a fake productivity loop: when the curated registry contains no eligible new economic mechanisms, the correct result is `NO_NEW_FEASIBLE_MECHANISMS`, not another parametrization.

Why P0 before autonomous paper retrieval? A new mechanism without a safe, restartable, reviewable lifecycle would merely replicate the past pattern of manually engineering bespoke Kill Tests.

## Architecture

```
Human-reviewed immutable task policy (JSON)
                   |
        systemd one-shot tick (hourly)
                   |
  strict validation + archived-mechanism denylist
                   |
      SQLite BEGIN IMMEDIATE task claim
                   |
  allowlisted deterministic research-only task
      /                             \
 fixed curated evidence screen     archived report fingerprint check
      |                             |
  candidate? -> WAITING REVIEW      integrity gate -> VERIFIED/STOP
      |                             |
  SQLite results/events + UTC daily heartbeats
                   |
   next tick -> next explicitly approved task / safe IDLE
```

**Task types (only two):**

1. `screen_curated`: read *only* the existing fixed six-source `evidence.py` registry, apply the repository's novelty/data/scope screen plus the operator's permanently archived mechanism list; record either `NO_NEW_FEASIBLE_MECHANISMS` or `AWAITING_HUMAN_PROTOCOL_APPROVAL`. This task **does not** conduct live literature search, author strategies, call the LLM or run a Kill Test. A discovered candidate cannot be executed without a *separately reviewed/frozen protocol* and a later bounded runner.
2. `verify_archived_report`: read only a specifically allowlisted file under `runtime/funding/` or `runtime/attention/`, match the operator-pinned SHA256, research ID, `STOP_INSUFFICIENT_INCREMENTAL_INFORMATION` status and mandatory safety flags. The result is `ARCHIVED_REPORT_VERIFIED`, **not** independent recomputation of prices, funding or Google Trends outcomes. Wrong hash/metadata stops for review; missing file returns `BLOCKED_MISSING_INPUT`. Operator must supply a new task ID after resolving such a failure, rather than changing an existing approval.

**Never called by v0:** `quant-agent run-once`, `quant-agent finalize`, `quant-ideas discover --mode api`, any strategy backtest, network requests, external scripts, APIs, self-modifying code or broker integrations. There are no generated trading rules, order tickets, account simulations or 2025 holdout accesses. The controller only handles these two fixed task types; it cannot create a new executable task by itself.

## Durable state / restart semantics

- SQLite WAL-independent standard transaction using `BEGIN IMMEDIATE` claims at most one task per tick; concurrent ticks cannot claim the same row. Persist task ID, canonical task + archived-list digest, all state transitions, result JSON, timestamps, and heartbeats to `runtime/agent/orchestrator.sqlite3`.
- Once an approved task ID is registered, modifying its payload or archived list is **rejected** as `POLICY_DRIFT_BLOCKED`; append a *new reviewed task ID* rather than editing prior evidence. A policy must always include the four archived mechanism IDs; it cannot silently reactivate them.
- Task completion and result archive are one atomic SQLite transaction; the task itself has no outside side effects. A process interrupted while `RUNNING` may reclaim after a conservative ten-minute lease and rerun **at most once**. Two uncompleted claims result in `INTERRUPTED_REVIEW_REQUIRED`, not an endless loop.
- A `PAUSED` marker created by existing `quant-agent pause` is honored without claiming work. An empty queue records `IDLE_NO_APPROVED_TASKS` (zero provider charges), rather than fabricating candidate research.
- The **policy file** is an operator-reviewed, machine-local document. JSON cannot contain commands, URLs, scripts or arbitrary paths. Only two hardcoded report paths are accepted for v0. The example policy in Git is **not automatically enabled** by installation.
- No network/model calls and no dynamic code execution means the v0 marginal API cost is zero. A future P1 model/web tool must get a separate source allowlist, hard provider spend cap, per-step approval contract and auditable provenance.

## Manual smoke before service setup

```
python -m pip install -e .
mkdir -p runtime
cp deploy/quant-orchestrator.policy.example.json runtime/orchestrator.policy.json
quant-orchestrator --home runtime tick --policy runtime/orchestrator.policy.json
quant-orchestrator --home runtime status
quant-orchestrator --home runtime tick --policy runtime/orchestrator.policy.json
```

Expected **first** tick: `NO_NEW_FEASIBLE_MECHANISMS` with a registry snapshot; **second** tick: `IDLE_NO_APPROVED_TASKS`. The `status` command is a read-only snapshot and exits with code **0** on successful inspection; it does not have a top-level `status` JSON field. A `tick` with `FAILED_*` or `BLOCKED_MISSING_INPUT` exits nonzero; healthy `NO_NEW_FEASIBLE_MECHANISMS` and `IDLE_NO_APPROVED_TASKS` exit 0. The `acceptance` command exits 1 for `NOT_YET`, and 0 only after `PASS_UNATTENDED_CONTROLLER_GATE_ONLY`, so automation cannot mistake an unmet gate for success. It is correct to produce no paid LLM traffic and no new strategies. Policy is **not** consent to trade or perform holdout evaluation. To approve a previously archived report integrity check, append a new `verify_archived_report` task with an exact content SHA256 calculated on the operator's local report. Do **not** register a task with a fabricated hash.

### Optional systemd example, **operator action only**

The repo includes `deploy/quant-orchestrator.service` and `.timer` examples. They **do not** activate automatically. They assume an unprivileged `quantresearch` OS user, local path `/opt/quant-research-agent`, a reviewed policy installed at `/etc/quant-orchestrator.policy.json` and write access solely to the runtime directory. Verify those assumptions before enabling; do not run the old `quant-agent.timer` simultaneously, as it targets a superseded trend runner.

After operator review, locally install units and enable the new timer:

```
sudo install -m 0644 deploy/quant-orchestrator.service /etc/systemd/system/
sudo install -m 0644 deploy/quant-orchestrator.timer /etc/systemd/system/
sudo install -m 0600 runtime/orchestrator.policy.json /etc/quant-orchestrator.policy.json
sudo systemctl daemon-reload
sudo systemctl enable --now quant-orchestrator.timer
systemctl list-timers --all | grep quant-orchestrator
journalctl -u quant-orchestrator.service --since '1 day ago'
```

**Do not execute these setup commands before approval**. The new timer emits one short task check per hour, not a constantly running expensive model. It does not need market connectivity.

## Seven-day unattended controller acceptance

**Only after** seven actual consecutive UTC calendar days of unattended service operation:

```
quant-orchestrator --home runtime acceptance --days 7
quant-orchestrator --home runtime status
```

The controller's pass predicate requires recorded tick heartbeats on all seven different UTC dates, at least one completed allowlisted task, zero tasks needing failure review, and no pause-only days. Operator must **also inspect systemd journal** to establish automatic, unattended triggers and absence of crashes; manual ticking can otherwise mimic heartbeats. Simulated dates in unit tests are **tests of the predicate, not operational evidence**. `PASS_UNATTENDED_CONTROLLER_GATE_ONLY` cannot be interpreted as autonomous independent discovery, alpha evidence, stable host uptime, completed 7x24 operations or trading permission.

**P0 exit condition:** Seven-day service review passes, idempotence and restart tests pass, no policy drift, no duplicate study, zero paid calls and an auditable SQLite task/result history. **Stop P0 work then**. The separate P1 decision is whether to introduce *reviewed*, direct external literature discovery and a finite library of generic mechanism-test runners, with separate approval and source-quality rules. Do not broaden P0 into a generic code-writing agent or continuous strategy mining.
