"""Fail-closed, research-only autonomous task controller v0.

A tick executes at most ONE human-approved, deterministic task. It never calls
models, exchanges, external URLs, shell commands, strategy backtests or holdouts.
SQLite records claims, outcomes and heartbeats for systemd restart recovery.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

from .evidence import MECHANISMS, SOURCES, mechanism_screen

SCHEMA_VERSION = 1
LEASE_SECONDS = 600
MAX_REPORT_BYTES = 2_000_000
ALLOWED_ARTIFACTS = frozenset({
    "funding/BTCUSDT-funding-phase1-mechanism-v1.json",
    "attention/BTCUSDT-attention-phase1-retrospective-kill-v1.json",
})
ALLOWED_TASK_KINDS = frozenset({"screen_curated", "verify_archived_report"})
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{3,79}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BLOCKED_POLICY_FLAGS = (
    "trading_allowed", "account_simulation_allowed", "ticket_generation_allowed",
    "holdout_access_allowed", "network_access_allowed", "model_calls_allowed",
    "arbitrary_code_allowed", "strategy_backtest_allowed",
)
SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, task_digest TEXT NOT NULL, task_json TEXT NOT NULL,
    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    claimed_at TEXT, created_at TEXT NOT NULL, completed_at TEXT,
    result_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, task_id TEXT,
    kind TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, outcome TEXT NOT NULL
);
"""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def load_policy(path: Path) -> dict:
    """Operator-authored policy is *data*, never executable source or prompt."""
    raw = path.read_bytes()
    if len(raw) > 100_000:
        raise ValueError("Policy too large")
    value = json.loads(raw)
    required = {"schema_version", "research_only", *BLOCKED_POLICY_FLAGS,
                "max_attempts", "archived_mechanisms", "tasks"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("Policy must have exactly the frozen v0 schema fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported policy version")
    if value["research_only"] is not True or any(value[x] is not False for x in BLOCKED_POLICY_FLAGS):
        raise ValueError("Orchestrator is permanently research-only; every capability flag must be false")
    if type(value["max_attempts"]) is not int or not (1 <= value["max_attempts"] <= 2):
        raise ValueError("max_attempts must be 1 or 2")
    archived = value["archived_mechanisms"]
    if (type(archived) is not list or any(type(x) is not str or not IDENTIFIER.fullmatch(x)
                                         for x in archived) or len(set(archived)) != len(archived)):
        raise ValueError("Invalid archived mechanisms")
    # Prevent reactivating prior archived research under a freshly edited policy.
    required_archived = {"trend_persistence", "volatility_exposure", "attention_demand",
                         "derivatives_leverage_pressure"}
    if not required_archived.issubset(archived):
        raise ValueError("Previously archived economic mechanisms cannot be unarchived by policy")
    tasks = value["tasks"]
    if type(tasks) is not list or len(tasks) > 100:
        raise ValueError("Task queue must contain at most 100 tasks")
    seen = set()
    for task in tasks:
        if type(task) is not dict or not {"id", "kind"}.issubset(task):
            raise ValueError("Invalid task entry")
        if type(task["id"]) is not str or not IDENTIFIER.fullmatch(task["id"]):
            raise ValueError("Invalid task ID")
        if task["id"] in seen:
            raise ValueError("Duplicate task ID")
        seen.add(task["id"])
        if task["kind"] not in ALLOWED_TASK_KINDS:
            raise ValueError("Task kind is not allowlisted")
        if task["kind"] == "screen_curated":
            if set(task) != {"id", "kind"}:
                raise ValueError("Curated screening task has unexpected fields")
        else:
            if set(task) != {"id", "kind", "artifact", "research_id", "expected_status", "sha256"}:
                raise ValueError("Report verification requires exact immutable fields")
            if task["artifact"] not in ALLOWED_ARTIFACTS:
                raise ValueError("Report path is not approved (no arbitrary file access)")
            if (type(task["research_id"]) is not str or type(task["expected_status"]) is not str
                    or type(task["sha256"]) is not str or not SHA256.fullmatch(task["sha256"])):
                raise ValueError("Invalid pinned report metadata")
            allowed = {
                "funding/BTCUSDT-funding-phase1-mechanism-v1.json": "BTC_PERP_FUNDING_PRESSURE_v1",
                "attention/BTCUSDT-attention-phase1-retrospective-kill-v1.json": "BTC_ATTENTION_DEMAND_v1",
            }
            if (task["research_id"] != allowed[task["artifact"]]
                    or task["expected_status"] != "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION"):
                raise ValueError("Only already-archived STOP reports are supported in v0")
    return value


def connect(root: Path) -> sqlite3.Connection:
    folder = root / "agent"
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "orchestrator.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SQL)
    db.commit()
    return db


def event(db: sqlite3.Connection, now: datetime, task_id: str | None, kind: str, details: dict) -> None:
    db.execute("INSERT INTO events(at,task_id,kind,details_json) VALUES(?,?,?,?)",
               (now.isoformat(), task_id, kind, canonical(details)))


def _claim(root: Path, policy: dict, now: datetime) -> dict | None:
    db = connect(root)
    try:
        db.execute("BEGIN IMMEDIATE")
        for task in policy["tasks"]:
            td = digest({"task": task, "archived_mechanisms": policy["archived_mechanisms"]})
            old = db.execute("SELECT task_digest FROM tasks WHERE task_id=?", (task["id"],)).fetchone()
            if old and old["task_digest"] != td:
                raise ValueError(f"POLICY_DRIFT_BLOCKED: task ID {task['id']} was changed; use a new ID")
            if old is None:
                db.execute("INSERT INTO tasks(task_id,task_digest,task_json,status,created_at) VALUES(?,?,?,?,?)",
                           (task["id"], td, canonical(task), "QUEUED", now.isoformat()))
                event(db, now, task["id"], "APPROVED_TASK_REGISTERED", {"task_digest": td})
        # Reclaim only interrupted tasks whose bounded deterministic runner was not finished.
        cutoff = (now - timedelta(seconds=LEASE_SECONDS)).isoformat()
        stale = db.execute("SELECT task_id,attempts FROM tasks WHERE status='RUNNING' AND claimed_at<=?",
                           (cutoff,)).fetchall()
        for row in stale:
            retry = row["attempts"] < policy["max_attempts"]
            db.execute("UPDATE tasks SET status=?,claimed_at=NULL WHERE task_id=?",
                       ("QUEUED" if retry else "INTERRUPTED_REVIEW_REQUIRED", row["task_id"]))
            event(db, now, row["task_id"], "STALE_CLAIM_RECOVERED",
                  {"retry": retry, "previous_attempts": row["attempts"]})
        # Only operator-listed tasks, in approved order; never auto-synthesize new research.
        for task in policy["tasks"]:
            row = db.execute("SELECT attempts,status FROM tasks WHERE task_id=?", (task["id"],)).fetchone()
            if row["status"] == "QUEUED":
                if row["attempts"] >= policy["max_attempts"]:
                    db.execute("UPDATE tasks SET status='INTERRUPTED_REVIEW_REQUIRED' WHERE task_id=?", (task["id"],))
                    continue
                db.execute("UPDATE tasks SET status='RUNNING',attempts=attempts+1,claimed_at=? WHERE task_id=?",
                           (now.isoformat(), task["id"]))
                event(db, now, task["id"], "TASK_CLAIMED", {"attempt": row["attempts"] + 1})
                db.commit()
                return task
        db.commit()
        return None
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _screen_curated(policy: dict) -> tuple[str, dict]:
    screened = []
    feasible = []
    for key in sorted(MECHANISMS, key=lambda k: (MECHANISMS[k]["priority"], k)):
        s = mechanism_screen(key, frozenset(policy["archived_mechanisms"]))
        screened.append({"mechanism_id": key, "status": s["status"], "reasons": s["reasons"],
                         "source_ids": MECHANISMS[key]["sources"]})
        if s["status"] == "ELIGIBLE_FOR_IDEA_ONLY":
            feasible.append(key)
    source_meta = {k: {"url": v["url"], "universe": v["universe"]} for k, v in SOURCES.items()}
    result = {"catalog_digest": digest({"mechanisms": MECHANISMS, "sources": source_meta}),
              "screened": screened, "eligible_mechanisms": feasible,
              "new_public_research_retrieved": False,
              "note": "Fixed previously-reviewed source registry; not an autonomous web literature search"}
    return ("AWAITING_HUMAN_PROTOCOL_APPROVAL" if feasible else "NO_NEW_FEASIBLE_MECHANISMS", result)


def _verify_archived(root: Path, task: dict) -> tuple[str, dict]:
    """Verify pinned *report integrity*, not independently reproduce economic claims."""
    file = (root / task["artifact"]).resolve()
    if not file.is_relative_to(root.resolve()):
        raise ValueError("Report escaped runtime root")
    if not file.is_file():
        return "BLOCKED_MISSING_INPUT", {"artifact": task["artifact"], "reason": "Pinned report absent"}
    if file.stat().st_size > MAX_REPORT_BYTES:
        return "FAILED_REVIEW_REQUIRED", {"reason": "Pinned report too large"}
    raw = file.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != task["sha256"]:
        return "FAILED_REVIEW_REQUIRED", {"reason": "Pinned report SHA256 mismatch", "actual_sha256": actual}
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "FAILED_REVIEW_REQUIRED", {"reason": "Malformed report JSON"}
    if (type(report) is not dict or report.get("research_id") != task["research_id"]
            or report.get("status") != task["expected_status"]):
        return "FAILED_REVIEW_REQUIRED", {"reason": "Report research ID or status mismatch"}
    for cap in ("strategy_backtest_allowed", "trading_allowed", "holdout_evaluated"):
        if report.get(cap) is not False:
            return "FAILED_REVIEW_REQUIRED", {"reason": f"Report safety field {cap} is not false"}
    return "ARCHIVED_REPORT_VERIFIED", {"artifact": task["artifact"], "sha256": actual,
                                        "research_id": task["research_id"],
                                        "reported_status": report["status"],
                                        "scope": "Exact file and frozen status integrity only; raw-data outcomes not recomputed"}


def _execute(root: Path, policy: dict, task: dict) -> tuple[str, dict]:
    if task["kind"] == "screen_curated":
        return _screen_curated(policy)
    if task["kind"] == "verify_archived_report":
        return _verify_archived(root, task)
    raise AssertionError("Unreachable task kind: input schema rejects it")


def _heartbeat(db: sqlite3.Connection, now: datetime, outcome: str) -> None:
    db.execute("INSERT INTO heartbeats(at,outcome) VALUES(?,?)", (now.isoformat(), outcome))


def tick(root: Path, policy_path: Path, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("UTC clock required")
    root = root.resolve()
    policy = load_policy(policy_path)
    if (root / "PAUSED").exists():
        db = connect(root)
        try:
            with db:
                _heartbeat(db, now, "PAUSED")
        finally:
            db.close()
        return {"status": "PAUSED", "ran_task": False}
    task = _claim(root, policy, now)
    if task is None:
        db = connect(root)
        try:
            with db:
                _heartbeat(db, now, "IDLE_NO_APPROVED_TASKS")
        finally:
            db.close()
        return {"status": "IDLE_NO_APPROVED_TASKS", "ran_task": False}
    try:
        outcome, result = _execute(root, policy, task)
    except Exception as exc:  # Fail-closed. No automatic research retries on semantic errors.
        outcome, result = "FAILED_REVIEW_REQUIRED", {"reason": type(exc).__name__, "details": str(exc)[:240]}
    db = connect(root)
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT status FROM tasks WHERE task_id=?", (task["id"],)).fetchone()
        if row is None or row["status"] != "RUNNING":
            raise RuntimeError("Claim missing or already finalized; refuse to rewrite outcome")
        db.execute("UPDATE tasks SET status=?,result_json=?,completed_at=?,claimed_at=NULL WHERE task_id=?",
                   (outcome, canonical(result), now.isoformat(), task["id"]))
        event(db, now, task["id"], "TASK_COMPLETED", {"status": outcome, "result_digest": digest(result)})
        _heartbeat(db, now, outcome)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
    return {"status": outcome, "ran_task": True, "task_id": task["id"], "result": result}


def status(root: Path) -> dict:
    db = connect(root.resolve())
    try:
        rows = db.execute("SELECT task_id,status,attempts,created_at,completed_at,result_json FROM tasks ORDER BY created_at,task_id").fetchall()
        hb = db.execute("SELECT at,outcome FROM heartbeats ORDER BY id DESC LIMIT 1").fetchone()
        return {"paused": (root.resolve() / "PAUSED").exists(),
                "last_heartbeat": dict(hb) if hb else None,
                "tasks": [{"id": x["task_id"], "status": x["status"], "attempts": x["attempts"],
                           "created_at": x["created_at"], "completed_at": x["completed_at"],
                           "result": json.loads(x["result_json"]) if x["result_json"] else None} for x in rows]}
    finally:
        db.close()


def acceptance(root: Path, *, days: int = 7, now: datetime | None = None) -> dict:
    """Pass ONLY after distinct UTC day heartbeats; no simulated uptime claim."""
    if not 1 <= days <= 30:
        raise ValueError("days must be 1..30")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("UTC clock required")
    db = connect(root.resolve())
    try:
        begin = (now.date() - timedelta(days=days - 1)).isoformat()
        rows = db.execute("SELECT at,outcome FROM heartbeats WHERE at>=? AND at<=? ORDER BY at",
                          (begin, now.isoformat())).fetchall()
        by_day = {x["at"][:10] for x in rows if x["outcome"] != "PAUSED"}
        completed = db.execute("SELECT COUNT(*) FROM tasks WHERE completed_at IS NOT NULL AND status NOT IN ('FAILED_REVIEW_REQUIRED', 'BLOCKED_MISSING_INPUT', 'INTERRUPTED_REVIEW_REQUIRED')").fetchone()[0]
        failed = db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('FAILED_REVIEW_REQUIRED', 'INTERRUPTED_REVIEW_REQUIRED')").fetchone()[0]
        passed = len(by_day) == days and completed >= 1 and failed == 0
        return {"status": "PASS_UNATTENDED_CONTROLLER_GATE_ONLY" if passed else "NOT_YET",
                "window_days": days, "observed_distinct_utc_days": len(by_day),
                "completed_tasks": completed, "failed_tasks": failed,
                "note": "Heartbeats demonstrate recorded ticks, not host uptime or independent strategy discovery"}
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-orchestrator", description="research-only approved-task controller")
    parser.add_argument("--home", type=Path, default=Path(os.getenv("QUANT_HOME", "runtime")))
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("tick", help="Execute at most one approved deterministic task")
    t.add_argument("--policy", type=Path, required=True, help="Operator-owned reviewed JSON policy")
    sub.add_parser("status", help="Inspect durable tasks and last heartbeat")
    a = sub.add_parser("acceptance", help="Assess recorded multi-day unattended controller gate")
    a.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        if args.command == "tick":
            output = tick(args.home, args.policy)
        elif args.command == "status":
            output = status(args.home)
        else:
            output = acceptance(args.home, days=args.days)
        print(json.dumps(output, sort_keys=True, indent=2))
        return 0 if not output["status"].startswith("FAILED_") else 1
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        print(json.dumps({"status": "STOP_CONTROLLER_ERROR", "reason": str(exc)[:300]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
