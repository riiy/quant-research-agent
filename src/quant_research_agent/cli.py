"""Command-line lifecycle for one BTC daily evidence-first research experiment."""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

from .backtest import assess, simulate
from .data import ingest, load_research_data, prefix_hash
from .discovery import discover
from .models import Candidate
from .reports import write_report
from .storage import Store

TRAIN_START, TRAIN_END = date(2018, 1, 1), date(2023, 12, 31)
VALID_START, VALID_END = date(2024, 1, 1), date(2024, 12, 31)
HOLDOUT_START, HOLDOUT_END = date(2025, 1, 1), date(2025, 12, 31)


def run_once(root: Path, data_path: Path, mode: str) -> str:
    store = Store(root)
    if store.paused():
        raise RuntimeError("Research is paused")
    # No API call is needed to check local data; don't pay for unusable runs.
    bars, provenance = load_research_data(data_path)
    if bars[0].day > TRAIN_START or bars[-1].day < VALID_END:
        raise ValueError("Data must cover all days from 2018-01-01 to 2024-12-31")
    if mode == "api":
        max_calls = int(os.getenv("QUANT_MAX_API_CALLS_MONTH", "20"))
        if not 1 <= max_calls <= 1000:
            raise ValueError("QUANT_MAX_API_CALLS_MONTH must be 1..1000")
        attempt_id = store.reserve_api_call(os.getenv("QUANT_MODEL", "gpt-6-luna"), max_calls)
    candidate, discovery_meta = discover(mode)
    if mode == "api":
        store.record_usage(attempt_id, discovery_meta.get("usage", {}))
    prior = store.get_by_fingerprint(candidate.fingerprint)
    if prior:
        print(f"Already researched identical rules: {prior['id']} ({prior['status']})")
        return prior["id"]
    development = simulate(bars, candidate, TRAIN_START, TRAIN_END)
    validation = simulate(bars, candidate, VALID_START, VALID_END)
    stress = simulate(bars, candidate, VALID_START, VALID_END, fee=0.002, slippage=0.001)
    status, reasons = assess(validation, stress)
    if provenance["source"] != "binance-public-data-spot-monthly":
        status = "DEMO_UNVERIFIED_DATA"
        reasons.insert(0, "Local CSV is not verified by Binance checksum manifest; demonstration only")
    if mode == "seed":
        status = "DEMO_SEEDED_HYPOTHESIS"
        reasons.insert(0, "Deterministic seed hypothesis; no AI discovery was performed")
    data_meta = dict(provenance)
    data_meta["pre_holdout_prefix_sha256"] = prefix_hash(bars, VALID_END)
    metadata = {"discovery": discovery_meta, "data": data_meta,
                "protocol_version": "btc-daily-v1-locked-2026-11-16"}
    result = {"development": development.as_dict(), "validation": validation.as_dict(),
              "validation_double_cost": stress.as_dict(), "reasons": reasons}
    path = root / "reports" / f"{candidate.fingerprint}.md"
    payload = {"status": status, "candidate": candidate.as_dict(), "metadata": metadata, "result": result}
    write_report(path, payload)
    run_id = store.save(candidate.fingerprint, candidate.as_dict(), metadata, result, status, path)
    print(f"Run {run_id}: {status}\nReport: {path}")
    return run_id


def finalize(root: Path, data_path: Path, run_id: str) -> None:
    """One-time sealed holdout; does not reopen strategy optimization."""
    store = Store(root)
    if store.paused():
        raise RuntimeError("Research is paused")
    row = store.get(run_id)
    if not row:
        raise ValueError("Unknown run ID")
    if row["holdout_evaluated"] or row["status"] != "PENDING_SEALED_HOLDOUT":
        raise ValueError("Not eligible for one-time sealed holdout")
    candidate = Candidate.from_dict(json.loads(row["candidate_json"]))
    meta = json.loads(row["metadata_json"])
    bars, provenance = load_research_data(data_path)
    if provenance["source"] != "binance-public-data-spot-monthly":
        raise ValueError("Holdout requires checksum-verified Binance archive")
    if bars[0].day != TRAIN_START or bars[-1].day < HOLDOUT_END:
        raise ValueError("Holdout dataset must include 2018-01-01 through 2025-12-31")
    if prefix_hash(bars, VALID_END) != meta["data"]["pre_holdout_prefix_sha256"]:
        raise ValueError("Pre-holdout data changed; abort to avoid invalid comparison")
    holdout = simulate(bars, candidate, HOLDOUT_START, HOLDOUT_END)
    holdout_stress = simulate(bars, candidate, HOLDOUT_START, HOLDOUT_END, fee=0.002, slippage=0.001)
    result = json.loads(row["result_json"])
    result["holdout"] = holdout.as_dict()
    result["holdout_double_cost"] = holdout_stress.as_dict()
    reasons = list(result["reasons"])
    if holdout.entries < 2 or holdout.total_return <= 0 or holdout.excess_return <= 0 or holdout_stress.excess_return <= 0:
        status = "ARCHIVED_FAILED_FINAL_HOLDOUT"
        reasons.append("Final holdout failed predeclared cost, sample or performance screen")
    else:
        status = "ARCHIVED_PRELIMINARY_ONLY"
        reasons.append("Passed one sealed holdout; single-market/single-year evidence is still insufficient for trading")
    result["reasons"] = reasons
    # SQLite transition prevents double-spending the final test; no subsequent re-optimization.
    store.finalize(run_id, result, status)
    payload = {"status": status, "candidate": candidate.as_dict(), "metadata": meta, "result": result}
    write_report(Path(row["report_path"]), payload)
    print(f"Run {run_id}: {status}\nReport: {row['report_path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-agent", description="Research-only BTC daily strategy agent")
    parser.add_argument("--home", type=Path, default=Path(os.getenv("QUANT_HOME", "runtime")))
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_cmd = sub.add_parser("ingest", help="Download checksum-verified monthly Binance candles")
    ingest_cmd.add_argument("--from", dest="start", default="2018-01")
    ingest_cmd.add_argument("--to", dest="end", default="2024-12")
    run_cmd = sub.add_parser("run-once", help="Discover and verify one hypothesis, then archive")
    run_cmd.add_argument("--mode", choices=("api", "seed"), default="api")
    run_cmd.add_argument("--data", type=Path, help="CSV path (unverified local CSV is demo-only)")
    final_cmd = sub.add_parser("finalize", help="Evaluate the sealed 2025 holdout exactly once")
    final_cmd.add_argument("run_id")
    final_cmd.add_argument("--data", type=Path)
    sub.add_parser("status")
    sub.add_parser("candidates")
    report_cmd = sub.add_parser("report")
    report_cmd.add_argument("--latest", action="store_true")
    sub.add_parser("pause")
    sub.add_parser("resume")
    args = parser.parse_args(argv)
    root = args.home.resolve()
    store = Store(root)
    try:
        if args.command == "ingest":
            print(f"Verified CSV: {ingest(root, args.start, args.end)}")
        elif args.command == "run-once":
            run_once(root, args.data or root / "data" / "BTCUSDT-1d.csv", args.mode)
        elif args.command == "finalize":
            finalize(root, args.data or root / "data" / "BTCUSDT-1d.csv", args.run_id)
        elif args.command == "status":
            latest = store.list(limit=1)
            print(json.dumps({"paused": store.paused(), "api_calls_this_month": store.usage_count(),
                              "last_experiment": latest[0] if latest else None,
                              "trading_allowed": False, "account_simulation_allowed": False}, indent=2))
        elif args.command == "candidates":
            print(json.dumps(store.list(), indent=2))
        elif args.command == "report":
            latest = store.list(limit=1)
            if not latest:
                raise ValueError("No experiment reports")
            print(Path(latest[0]["report_path"]).read_text())
        elif args.command == "pause":
            store.set_paused(True)
            print("Paused")
        elif args.command == "resume":
            store.set_paused(False)
            print("Resumed")
        return 0
    except (ValueError, RuntimeError, FileNotFoundError, OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
