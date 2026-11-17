"""Pre-registered, mechanism-only BTC realized-volatility kill test.

Consumes only 2018--2023 OHLCV rows. Does NOT import or call backtest,
open 2024/2025 candles, trade, optimize, or mutate the idea database.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
from random import Random
import re
import sqlite3
from statistics import mean, median, stdev

FIRST = date(2018, 1, 1)
CAL_END = date(2020, 12, 31)
EVAL_START = date(2021, 1, 1)
LAST = date(2023, 12, 31)
LOOKBACK = 30
BLOCK_DAYS = 14
BOOTSTRAPS = 1000
BOOT_SEED = 20261116
MIN_REGIME_DAYS = 100
MATERIAL_RISK_RATIO = 1.20
IDEA_MECHANISM = "volatility_exposure"
SOURCE_ID = "moreira_muir2017"
PROTOCOL = "btc-vol-mechanism-kill-v1-frozen-2026-11-16"


def load_prior_idea(root: Path, idea_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{12}", idea_id):
        raise ValueError("Idea ID must have 12 lowercase hex characters")
    db = root / "ideas.sqlite3"
    if not db.is_file():
        raise ValueError("Idea database missing: cannot audit an unregistered hypothesis")
    with closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT status, mechanism_id, idea_json FROM ideas WHERE idea_id=?", (idea_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Unknown idea ID; no automatic hypothesis generation")
    status, mechanism_id, raw = row
    idea = json.loads(raw)
    if (status != "AWAITING_RULE_DESIGN_NOT_BACKTESTED"
            or mechanism_id != IDEA_MECHANISM
            or idea.get("mechanism_id") != IDEA_MECHANISM
            or SOURCE_ID not in idea.get("source_ids", [])):
        raise ValueError("Only the archived, unbacktested volatility-exposure idea is eligible")
    # This protocol specifically tests the received fixed 30-day/median proposal.
    proposal = idea.get("signal_proposal", "").lower()
    if "30" not in proposal or "median" not in proposal:
        raise ValueError("Archived idea did not propose the fixed 30-day / median diagnostic")
    return idea


def load_development_closes(path: Path) -> tuple[list[tuple[date, float]], dict]:
    """Stop reading at the FIRST row after 2023-12-31, without parsing its prices.

    A 2024+ suffix may exist in the CSV, but never enters the calculation or
    provenance digest. This is intentionally not the all-years data loader.
    """
    data = []
    digest = hashlib.sha256()
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        expected = {"day", "open", "high", "low", "close", "volume"}
        if set(reader.fieldnames or []) != expected:
            raise ValueError("Expected day,open,high,low,close,volume columns")
        for row in reader:
            day = date.fromisoformat(row["day"])
            if day > LAST:
                break
            if day < FIRST:
                raise ValueError("Unexpected pre-2018 row; freeze exact study range")
            if data and day != data[-1][0] + timedelta(days=1):
                raise ValueError("Missing, duplicate or unordered development day")
            if not data and day != FIRST:
                raise ValueError("Development history must begin 2018-01-01")
            o, h, l, c, v = (float(row[name]) for name in ("open", "high", "low", "close", "volume"))
            if (not all(math.isfinite(x) for x in (o, h, l, c, v))
                    or min(o, h, l, c) <= 0 or v < 0
                    or h < max(o, c, l) or l > min(o, c, h)):
                raise ValueError(f"Invalid development OHLCV {day}")
            data.append((day, c))
            digest.update((f"{day.isoformat()}," + ",".join(
                format(x, ".17g") for x in (o, h, l, c, v)) + "\n").encode())
            if day == LAST:
                break  # Do not even consume the first 2024 record.
    if not data or data[-1][0] != LAST:
        raise ValueError("Need continuous 2018-01-01 through 2023-12-31 closes")
    return data, {"development_rows": len(data), "development_ohlcv_sha256": digest.hexdigest(),
                  "first": str(data[0][0]), "last": str(data[-1][0])}


def build_observations(closes: list[tuple[date, float]]) -> tuple[float, list[tuple[bool, float]]]:
    """For day t, classify with vol known at t-1 and observe close(t)/close(t-1).

    The cutoff is fitted on *signals* dated 2018-01-31..2020-12-31 only.
    The mechanism observations are next-day returns dated 2021-01-01..2023-12-31.
    """
    returns = [None] + [math.log(closes[i][1] / closes[i - 1][1])
                        for i in range(1, len(closes))]
    rolling = {}
    for i in range(LOOKBACK, len(closes)):
        rolling[i] = stdev(returns[i - LOOKBACK + 1:i + 1])
    calibration = [rolling[i] for i in range(LOOKBACK, len(closes))
                   if closes[i][0] <= CAL_END]
    if len(calibration) < 365:
        raise ValueError("Insufficient pre-2021 calibration history")
    threshold = median(calibration)
    if threshold <= 0:
        raise ValueError("Volatility calibration is degenerate")
    observations = []
    for i in range(1, len(closes)):
        if EVAL_START <= closes[i][0] <= LAST:
            # i-1: yesterday's *completed* daily close, never the evaluated return.
            if i - 1 not in rolling:
                raise ValueError("Missing lagged volatility signal")
            observations.append((rolling[i - 1] > threshold, returns[i]))
    return threshold, observations


def describe(obs: list[tuple[bool, float]]) -> dict:
    higher = [r for high, r in obs if high]
    lower = [r for high, r in obs if not high]
    if not higher or not lower:
        return {"high_days": len(higher), "low_days": len(lower),
                "high_low_abs_risk_ratio": None, "high_reward_per_abs_risk": None,
                "low_reward_per_abs_risk": None}
    h_abs, l_abs = mean(abs(r) for r in higher), mean(abs(r) for r in lower)
    if l_abs == 0 or h_abs == 0:
        raise ValueError("Degenerate realized risk, cannot compute conditional ratio")
    return {
        "high_days": len(higher), "low_days": len(lower),
        "high_nextday_mean_abs_log_return": h_abs,
        "low_nextday_mean_abs_log_return": l_abs,
        "high_nextday_mean_log_return": mean(higher),
        "low_nextday_mean_log_return": mean(lower),
        "high_nextday_std_log_return": stdev(higher) if len(higher) > 1 else None,
        "low_nextday_std_log_return": stdev(lower) if len(lower) > 1 else None,
        "high_low_abs_risk_ratio": h_abs / l_abs,
        "high_reward_per_abs_risk": mean(higher) / h_abs,
        "low_reward_per_abs_risk": mean(lower) / l_abs,
    }


def bootstrap_lower(obs: list[tuple[bool, float]]) -> float | None:
    """Chronological paired 14-day circular block bootstrap; fixed local seed.

    Resamples regime labels and next-day returns together. It is a conservative
    diagnostic for serial dependence, not proof of independent OOS alpha.
    """
    n = len(obs)
    rng = Random(BOOT_SEED)
    results = []
    for _ in range(BOOTSTRAPS):
        high_n = low_n = 0
        high_sum = low_sum = 0.0
        for _block in range((n + BLOCK_DAYS - 1) // BLOCK_DAYS):
            start = rng.randrange(n)
            for offset in range(BLOCK_DAYS):
                # Last block may be truncated to exactly n observations.
                index = _block * BLOCK_DAYS + offset
                if index >= n:
                    break
                high, r = obs[(start + offset) % n]
                if high:
                    high_n += 1
                    high_sum += abs(r)
                else:
                    low_n += 1
                    low_sum += abs(r)
        if high_n and low_n and low_sum > 0:
            results.append((high_sum / high_n) / (low_sum / low_n))
    if len(results) < int(BOOTSTRAPS * 0.95):
        return None
    results.sort()
    return results[int(0.05 * (len(results) - 1))]  # one-sided ~95% lower bound


def evaluate(obs: list[tuple[bool, float]]) -> dict:
    summary = describe(obs)
    lower = bootstrap_lower(obs) if min(summary["high_days"], summary["low_days"]) >= MIN_REGIME_DAYS else None
    summary["risk_ratio_block_bootstrap_lower_95_one_sided"] = lower
    reasons = []
    if min(summary["high_days"], summary["low_days"]) < MIN_REGIME_DAYS:
        reasons.append("Fewer than 100 evaluation days in one volatility regime")
    else:
        if summary["high_low_abs_risk_ratio"] < MATERIAL_RISK_RATIO:
            reasons.append("High-vol state did not predict >=20% greater next-day absolute return")
        if lower is None or lower <= 1.0:
            reasons.append("14-day block-bootstrap lower bound does not exclude risk ratio <=1")
        if summary["high_reward_per_abs_risk"] > summary["low_reward_per_abs_risk"]:
            reasons.append("High-vol state offered higher realized mean-log-return per unit absolute risk")
    status = "STOP_INSUFFICIENT_MECHANISM_EVIDENCE" if reasons else "PASS_MECHANISM_GATE_ONLY"
    return {"status": status, "reasons": reasons, "metrics": summary}


def run(root: Path, idea_id: str, data_path: Path | None = None) -> dict:
    root = root.resolve()
    idea = load_prior_idea(root, idea_id)
    data_path = data_path or root / "data" / "BTCUSDT-1d.csv"
    closes, provenance = load_development_closes(data_path)
    threshold, observations = build_observations(closes)
    results = evaluate(observations)
    result = {
        "protocol": PROTOCOL,
        "idea_id": idea_id, "mechanism_id": IDEA_MECHANISM,
        "source_ids": idea["source_ids"],
        "market": "BTCUSDT spot 1d, research only",
        "calibration": {"dates": "2018-01-01..2020-12-31", "lagged_vol_window": LOOKBACK,
                        "threshold_type": "calibration median of 30d log-return stdev",
                        "threshold": threshold},
        "evaluation": {"dates": "2021-01-01..2023-12-31", "count": len(observations),
                       "target": "next-day absolute close-to-close log return"},
        "gates": {"minimum_days_each_regime": MIN_REGIME_DAYS,
                  "minimum_high_low_mean_abs_risk_ratio": MATERIAL_RISK_RATIO,
                  "block_bootstrap_days": BLOCK_DAYS, "block_bootstrap_reps": BOOTSTRAPS,
                  "bootstrap_seed": BOOT_SEED,
                  "bootstrap_one_sided_lower": 0.05,
                  "reward_condition": "mean log return / mean absolute log return, high <= low"},
        "data": provenance,
        **results,
        "scope": "Mechanism screening only; not a trade strategy, alpha or validation-period test. "
                 "No fee modeling applies without trades. No 2024/2025 data used. "
                 "Evidence from traditional asset factors is not BTC proof.",
    }
    output = root / "ideas" / f"{idea_id}_volatility_mechanism_kill_v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    # Immutable one-shot diagnostic. Reruns on identical inputs are idempotent;
    # changed data/code cannot silently replace the original audit evidence.
    if output.exists():
        if output.read_text(encoding="utf-8") != text:
            raise ValueError("Existing frozen kill-test report differs; will not overwrite it")
    else:
        with output.open("x", encoding="utf-8") as file:
            file.write(text)
    return {"report": str(output), **result}
