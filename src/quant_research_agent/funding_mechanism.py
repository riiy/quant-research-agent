"""Predeclared BTC perpetual funding mechanism Kill Test; NOT a strategy backtest.

Only 2020-2023 funding and spot daily close observations are consumed. Both
input series end at 2023-12-31. No 2024/2025 data, model API, simulation,
orders, parameter tuning, or trade costs are touched.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
from random import Random
from statistics import mean, stdev
import sys

FIRST = date(2020, 1, 1)
CAL_END = date(2021, 12, 31)
EVAL_START = date(2022, 1, 1)
LAST = date(2023, 12, 31)
EXPECTED_DAYS = (LAST - FIRST).days + 1
EXPECTED_FUNDING_ROWS = EXPECTED_DAYS * 3
AUDIT_PROTOCOL = "BTC_PERP_FUNDING_PRESSURE_v2_timestamp_jitter_audit_2020_2023"
PROTOCOL = "BTC_PERP_FUNDING_PRESSURE_v1_mechanism_frozen_2026-11-17"
EXPECTED_FUNDING_SHA = "159050d8818298c777f9ac1290530aecc01a01859d209df9d39c306a4b5eb977"
FUNDING_SCHEMA = ("calc_time", "funding_interval_hours", "last_funding_rate")
SPOT_SCHEMA = ("day", "open", "high", "low", "close", "volume")
SLOT_MS = 8 * 3600 * 1000
MAX_JITTER_MS = 100
FUNDING_PCTL = 0.90
RETURN_BIN_PCTLS = (1 / 3, 2 / 3)
SIGNAL_LAG_DAYS = 2
RETURN_LOOKBACK = 7
VOL_LOOKBACK = 30
MIN_EXTREME_DAYS = 40
MIN_EVENTS_PER_EVALUATION_YEAR = 10
MIN_DISTINCT_14D_BLOCKS = 8
MIN_COMPARATORS_PER_STRATUM = 10
BLOCK_DAYS = 14
BOOTSTRAPS = 1000
MIN_VALID_BOOTSTRAPS = 950
BOOT_SEED = 20261117
ONE_SIDED_ALPHA_PER_ENDPOINT = 0.025  # Bonferroni for two endpoints
RETURN_MATERIALITY = -0.003          # -30bp log return difference
DOWNSIDE_LOG_THRESHOLD = -0.02        # fixed daily log-return loss threshold
DOWNSIDE_MATERIALITY = 0.05          # +5 percentage points downside frequency


class MechanismError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], p: float) -> float:
    """Frozen nearest-rank percentile, ties preserved, no interpolation."""
    if not values or not 0 < p <= 1:
        raise MechanismError("Invalid empty calibration or percentile")
    ordered = sorted(values)
    return ordered[math.ceil(p * len(ordered)) - 1]


def load_verified_funding(path: Path, audit_path: Path) -> tuple[dict[date, float], dict]:
    """Read ONLY the already audited, frozen 2020-2023 canonical funding CSV."""
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit.get("protocol") != AUDIT_PROTOCOL
            or audit.get("status") != "DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED"
            or audit.get("issues") != []
            or audit.get("observed_rows") != EXPECTED_FUNDING_ROWS
            or audit.get("expected_settlements") != EXPECTED_FUNDING_ROWS
            or audit.get("unique_nominal_settlement_slots") != EXPECTED_FUNDING_ROWS
            or audit.get("range", {}).get("from") != str(FIRST)
            or audit.get("range", {}).get("through") != str(LAST)
            or audit.get("canonical_csv_sha256") != EXPECTED_FUNDING_SHA):
        raise MechanismError("Funding audit v2 is not the accepted frozen 2020-2023 data gate")
    actual_sha = sha256_file(path)
    if actual_sha != EXPECTED_FUNDING_SHA:
        raise MechanismError("Funding CSV SHA256 differs from the Phase 0 audited canonical dataset")
    collected: dict[date, list[float]] = {}
    seen_slots: set[int] = set()
    prev_raw = -1
    row_count = 0
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FUNDING_SCHEMA:
            raise MechanismError("Unexpected canonical funding CSV schema")
        for row in reader:
            raw = int(row["calc_time"])
            interval = int(row["funding_interval_hours"])
            rate = Decimal(row["last_funding_rate"])
            if not rate.is_finite() or abs(rate) >= 1 or interval != 8:
                raise MechanismError("Invalid funding observation")
            slot = (raw // SLOT_MS) * SLOT_MS
            offset = raw - slot
            day = datetime.fromtimestamp(slot / 1000, tz=timezone.utc).date()
            if not (FIRST <= day <= LAST) or not (0 <= offset <= MAX_JITTER_MS):
                raise MechanismError("Funding event outside the frozen settlement timeline")
            if slot in seen_slots or raw <= prev_raw:
                raise MechanismError("Duplicate / unordered funding settlement")
            seen_slots.add(slot)
            prev_raw = raw
            collected.setdefault(day, []).append(float(rate))
            row_count += 1
    if row_count != EXPECTED_FUNDING_ROWS or len(collected) != EXPECTED_DAYS:
        raise MechanismError("Funding settlement history not complete")
    current = FIRST
    while current <= LAST:
        if len(collected.get(current, ())) != 3:
            raise MechanismError(f"Missing funding day or settlement slot: {current}")
        current += timedelta(days=1)
    return {day: mean(v) for day, v in collected.items()}, {
        "funding_csv_sha256": actual_sha, "funding_audit_protocol": AUDIT_PROTOCOL,
        "funding_rows": row_count, "funding_days": len(collected),
    }


def load_spot_closes(path: Path) -> tuple[dict[date, float], dict]:
    """Skip earlier date labels; STOP after last 2023 bar without reading 2024 data."""
    closes: dict[date, float] = {}
    prefix = hashlib.sha256()
    previous = None
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if set(reader.fieldnames or ()) != set(SPOT_SCHEMA):
            raise MechanismError("Expected spot daily day/open/high/low/close/volume CSV")
        for row in reader:
            day = date.fromisoformat(row["day"])
            if day > LAST:
                break
            if day < FIRST:
                continue
            if (not closes and day != FIRST) or (previous is not None and day != previous + timedelta(days=1)):
                raise MechanismError("Missing/duplicate/out-of-order spot day")
            o, h, l, c, v = (float(row[x]) for x in SPOT_SCHEMA[1:])
            if (not all(math.isfinite(x) for x in (o, h, l, c, v)) or min(o, h, l, c) <= 0
                    or v < 0 or h < max(o, c, l) or l > min(o, c, h)):
                raise MechanismError(f"Invalid spot daily bar {day}")
            closes[day] = c
            previous = day
            prefix.update((str(day) + "," + ",".join(format(x, ".17g") for x in (o, h, l, c, v)) + "\n").encode())
            if day == LAST:
                break
    if len(closes) != EXPECTED_DAYS or previous != LAST:
        raise MechanismError("Need continuous 2020-01-01 through 2023-12-31 spot closes")
    return closes, {"spot_development_prefix_sha256": prefix.hexdigest(), "spot_development_rows": len(closes),
                    "spot_first": str(FIRST), "spot_last": str(LAST)}


def build_observations(funding: dict[date, float], closes: dict[date, float]) -> tuple[list[dict], list[dict]]:
    """Predict return on day t from funding and price controls no later than t-2.

    Deliberately leaves a full calendar-day buffer for publication. No same-day
    settlement, close, or forward-priced signal can enter t's target.
    """
    days = sorted(closes)
    log_close = [math.log(closes[d]) for d in days]
    returns = [None] + [log_close[i] - log_close[i - 1] for i in range(1, len(days))]
    cal: list[dict] = []
    evaluation: list[dict] = []
    for t in range(VOL_LOOKBACK + SIGNAL_LAG_DAYS, len(days)):
        k = t - SIGNAL_LAG_DAYS
        r7 = log_close[k] - log_close[k - RETURN_LOOKBACK]
        vol30 = stdev(returns[k - VOL_LOOKBACK + 1:k + 1])
        if not math.isfinite(vol30) or vol30 <= 0:
            raise MechanismError("Degenerate spot volatility history")
        item = {"day": days[t], "funding": funding[days[k]], "ret7": r7,
                "vol30": vol30, "target": returns[t],
                "downside": float(returns[t] <= DOWNSIDE_LOG_THRESHOLD)}
        (cal if days[t] <= CAL_END else evaluation).append(item)
    if len(evaluation) != 730 or not cal:
        raise MechanismError("Wrong 2022-2023 evaluation coverage")
    return cal, evaluation


def freeze_thresholds(funding: dict[date, float], cal: list[dict]) -> dict:
    cal_funding = [v for day, v in sorted(funding.items()) if day <= CAL_END]
    if len(cal_funding) != 731:
        raise MechanismError("Missing calibration funding days")
    threshold = percentile(cal_funding, FUNDING_PCTL)
    if threshold <= 0:
        raise MechanismError("High positive funding percentile not positive")
    r = [percentile([x["ret7"] for x in cal], p) for p in RETURN_BIN_PCTLS]
    v = [percentile([x["vol30"] for x in cal], p) for p in RETURN_BIN_PCTLS]
    if r[0] >= r[1] or v[0] >= v[1]:
        raise MechanismError("Insufficient price-control calibration variation")
    return {"extreme_positive_funding_threshold": threshold,
            "funding_calibration_days": len(cal_funding),
            "ret7_terciles": r, "vol30_terciles": v,
            "calibration_price_feature_days": len(cal)}


def assign_strata(rows: list[dict], frozen: dict) -> list[dict]:
    """Calibration-fixed 3x3 price bins × evaluation year, no outcome fitting."""
    result = []
    for x in rows:
        qret = sum(x["ret7"] > p for p in frozen["ret7_terciles"])
        qvol = sum(x["vol30"] > p for p in frozen["vol30_terciles"])
        result.append({"day": x["day"], "stratum": int((x["day"].year - EVAL_START.year) * 9 + qret * 3 + qvol),
                       "event": x["funding"] > frozen["extreme_positive_funding_threshold"],
                       "target": x["target"], "downside": x["downside"]})
    return result


def support(rows: list[dict]) -> dict:
    events = [r for r in rows if r["event"]]
    controls = [r for r in rows if not r["event"]]
    ecounts: dict[int, int] = {}
    ccounts: dict[int, int] = {}
    for row in events:
        ecounts[row["stratum"]] = ecounts.get(row["stratum"], 0) + 1
    for row in controls:
        ccounts[row["stratum"]] = ccounts.get(row["stratum"], 0) + 1
    # All event strata must have at least ten contemporaneous non-event controls.
    sparse = {str(k): ccounts.get(k, 0) for k in ecounts if ccounts.get(k, 0) < MIN_COMPARATORS_PER_STRATUM}
    block_ids = {(r["day"] - EVAL_START).days // BLOCK_DAYS for r in events}
    by_year = {str(year): sum(r["day"].year == year for r in events) for year in (2022, 2023)}
    return {"event_days": len(events), "control_days": len(controls),
            "event_days_by_year": by_year,
            "event_14day_calendar_blocks": len(block_ids),
            "event_strata": {str(k): n for k, n in sorted(ecounts.items())},
            "control_strata": {str(k): n for k, n in sorted(ccounts.items())},
            "sparse_control_strata": sparse}


def adjusted_differences(rows: list[dict], *, check_controls: bool) -> tuple[float, float] | None:
    """Event-weighted, within-stratum diagnostic; controls from evaluation only.

    Retrospective observational matched comparison, NOT an investable baseline
    and NOT fitted 2020-21 price-prediction model.
    """
    by: dict[int, dict[bool, list[dict]]] = {}
    for row in rows:
        by.setdefault(row["stratum"], {True: [], False: []})[row["event"]].append(row)
    n_total = sum(len(x[True]) for x in by.values())
    if n_total == 0:
        return None
    diffr = diffd = 0.0
    for groups in by.values():
        e, c = groups[True], groups[False]
        if not e:
            continue
        if len(c) < (MIN_COMPARATORS_PER_STRATUM if check_controls else 1):
            return None
        w = len(e) / n_total
        diffr += w * (mean(x["target"] for x in e) - mean(x["target"] for x in c))
        diffd += w * (mean(x["downside"] for x in e) - mean(x["downside"] for x in c))
    return diffr, diffd


def bootstrap(rows: list[dict]) -> dict:
    """Paired moving circular block bootstrap, preserving labels and return controls."""
    n = len(rows)
    rng = Random(BOOT_SEED)
    res: list[tuple[float, float]] = []
    for _ in range(BOOTSTRAPS):
        sample = []
        for _block in range((n + BLOCK_DAYS - 1) // BLOCK_DAYS):
            start = rng.randrange(n)
            for offset in range(BLOCK_DAYS):
                if len(sample) == n:
                    break
                sample.append(rows[(start + offset) % n])
        result = adjusted_differences(sample, check_controls=False)
        if result is not None:
            res.append(result)
    if len(res) < MIN_VALID_BOOTSTRAPS:
        return {"valid_replicates": len(res), "upper_return_97p5": None, "lower_downside_97p5": None}
    sret = sorted(x[0] for x in res)
    sdown = sorted(x[1] for x in res)
    return {"valid_replicates": len(res),
            "upper_return_97p5": sret[math.ceil((1 - ONE_SIDED_ALPHA_PER_ENDPOINT) * len(res)) - 1],
            "lower_downside_97p5": sdown[max(0, math.floor(ONE_SIDED_ALPHA_PER_ENDPOINT * len(res)) - 1)]}


def evaluate(rows: list[dict]) -> dict:
    observed = support(rows)
    reasons = []
    if observed["event_days"] < MIN_EXTREME_DAYS:
        reasons.append("Fewer than 40 extreme-positive funding days during evaluation")
    if min(observed["event_days_by_year"].values()) < MIN_EVENTS_PER_EVALUATION_YEAR:
        reasons.append("Fewer than ten extreme-positive funding days in either evaluation year")
    if observed["event_14day_calendar_blocks"] < MIN_DISTINCT_14D_BLOCKS:
        reasons.append("Extreme events cluster into fewer than eight separate 14-day blocks")
    if observed["sparse_control_strata"]:
        reasons.append("At least one event price-control stratum has fewer than ten non-event days")
    point = adjusted_differences(rows, check_controls=True) if not observed["sparse_control_strata"] else None
    uncertainty = bootstrap(rows) if not reasons else {
        "valid_replicates": 0, "upper_return_97p5": None, "lower_downside_97p5": None}
    if not reasons and uncertainty["valid_replicates"] < MIN_VALID_BOOTSTRAPS:
        reasons.append("Insufficient valid block-bootstrap replications")
    ret_pass = risk_pass = False
    annual = {str(y): adjusted_differences([x for x in rows if x["day"].year == y],
                                             check_controls=True)
              for y in (2022, 2023)}
    if point is not None and not reasons:
        ret_pass = (point[0] <= RETURN_MATERIALITY and uncertainty["upper_return_97p5"] < 0
                    and all(x is not None and x[0] < 0 for x in annual.values()))
        risk_pass = (point[1] >= DOWNSIDE_MATERIALITY and uncertainty["lower_downside_97p5"] > 0
                     and all(x is not None and x[1] > 0 for x in annual.values()))
        if not (ret_pass or risk_pass):
            reasons.append("Neither material directional nor downside increment survives price/volatility matching and multiplicity-aware bootstrap")
    elif point is None and not reasons:
        reasons.append("Unable to compute matched evaluation comparison")
    return {"status": "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION" if reasons else "PASS_INCREMENTAL_INFORMATION_ONLY",
            "reasons": reasons, "sample": observed,
            "annual_adjusted_differences": {year: {"log_return": x[0], "downside_probability": x[1]}
                                            if x is not None else None for year, x in annual.items()},
            "metrics": {"adjusted_log_return_diff": point[0] if point else None,
                        "adjusted_downside_probability_diff": point[1] if point else None,
                        **uncertainty, "directional_pass": ret_pass, "downside_pass": risk_pass}}


def run(root: Path, funding_csv: Path | None = None, audit_json: Path | None = None,
        spot_csv: Path | None = None) -> dict:
    root = root.resolve()
    funding_csv = funding_csv or root / "funding" / "BTCUSDT-funding-2020-2023.v2.csv"
    audit_json = audit_json or root / "funding" / "BTCUSDT-funding-2020-2023.audit.v2.json"
    spot_csv = spot_csv or root / "data" / "BTCUSDT-1d.csv"
    funding, funding_meta = load_verified_funding(funding_csv, audit_json)
    closes, spot_meta = load_spot_closes(spot_csv)
    calibration, evaluation = build_observations(funding, closes)
    frozen = freeze_thresholds(funding, calibration)
    rows = assign_strata(evaluation, frozen)
    outcome = evaluate(rows)
    report = {
        "protocol": PROTOCOL, "mechanism_id": "derivatives_leverage_pressure",
        "research_id": "BTC_PERP_FUNDING_PRESSURE_v1",
        "phase": "PHASE_1_MECHANISM_ONLY", "research_only": True,
        "data": {**funding_meta, **spot_meta},
        "calibration": {"from": str(FIRST), "through": str(CAL_END), **frozen},
        "evaluation": {"from": str(EVAL_START), "through": str(LAST), "days": len(evaluation),
                       "outcome": "spot close-to-close daily log return; t uses signal/controls through t-2"},
        "gates": {"extreme_positive_funding_quantile": FUNDING_PCTL,
                  "event_operator": "daily funding mean > calibration nearest-rank 90th percentile, threshold must be positive",
                  "signal_lag_calendar_days": SIGNAL_LAG_DAYS,
                  "price_controls": "calibration-fixed 3x3 tertile strata of 7d log return and 30d realized log-return stdev crossed with evaluation year",
                  "minimum_event_days": MIN_EXTREME_DAYS,
                  "minimum_events_per_evaluation_year": MIN_EVENTS_PER_EVALUATION_YEAR,
                  "year_stability": "endpoint must have correct adjusted effect sign in both 2022 and 2023",
                  "minimum_separate_14day_blocks": MIN_DISTINCT_14D_BLOCKS,
                  "minimum_control_days_per_event_stratum": MIN_COMPARATORS_PER_STRATUM,
                  "block_bootstrap_days": BLOCK_DAYS, "bootstrap_reps": BOOTSTRAPS,
                  "minimum_valid_bootstraps": MIN_VALID_BOOTSTRAPS,
                  "bootstrap_seed": BOOT_SEED,
                  "multiple_tests": "two one-sided endpoints, Bonferroni alpha 0.025 each",
                  "directional": "event minus price/vol matched non-event mean future log return <= -0.003; bootstrap 97.5% upper <0",
                  "downside": "event minus matched non-event probability of daily log return <= -0.02 >= +0.05; bootstrap 97.5% lower >0"},
        **outcome,
        "limits": "Price/volatility-matched observational diagnostic, not causal identification or investable baseline. "
                  "Positive funding does not directly measure open interest/leverage. "
                  "The 2022-2023 window is within prior project development data, not pristine holdout. "
                  "No 2024/2025 data, trade fills, fees, strategy return, or trading authorization.",
        "strategy_backtest_allowed": False, "holdout_evaluated": False, "trading_allowed": False,
    }
    out = root / "funding" / "BTCUSDT-funding-phase1-mechanism-v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if out.exists():
        if out.read_text(encoding="utf-8") != rendered:
            raise MechanismError("Existing frozen Phase 1 report differs; refusing overwrite")
    else:
        with out.open("x", encoding="utf-8") as f:
            f.write(rendered)
    return {"report": str(out), **report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-funding-kill", description="BTC funding mechanism information screen only")
    parser.add_argument("--home", type=Path, default=Path(os.getenv("QUANT_HOME", "runtime")))
    args = parser.parse_args(argv)
    try:
        result = run(args.home)
        print(json.dumps({"status": result["status"], "report": result["report"],
                          "reasons": result["reasons"], "sample": result["sample"],
                          "metrics": result["metrics"]}, indent=2))
        return 0 if result["status"] == "PASS_INCREMENTAL_INFORMATION_ONLY" else 2
    except (MechanismError, OSError, ValueError, json.JSONDecodeError, InvalidOperation, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
