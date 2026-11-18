"""Frozen calendar-weekday predictive-information screen, never a trading strategy.

An *a priori* Monday indicator adds one feature to fixed lagged price controls.
No weekdays are searched; only 2020-2021 targets fit coefficients and only
2022-2023 targets evaluate. 2024/2025 price values are never consumed.
"""
from __future__ import annotations

from datetime import date, timedelta
import csv
import hashlib
import math
from random import Random
from statistics import mean, stdev
from pathlib import Path

SPOT_PREFIX_SHA = "fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def"


def load_spot(path: Path) -> tuple[dict, dict]:
    """Parse exactly 2020-2023, stop before any 2024+ OHLCV content."""
    first, last = date(2020, 1, 1), date(2023, 12, 31)
    observed = {}
    h = hashlib.sha256()
    prev = None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) != {"day", "open", "high", "low", "close", "volume"}:
            raise ValueError("Spot OHLCV header mismatch")
        for row in reader:
            day = date.fromisoformat(row["day"])
            if day > last:
                break
            if day < first:
                continue
            if (prev is None and day != first) or (prev and day != prev + timedelta(days=1)):
                raise ValueError("Spot continuity/ordering mismatch")
            values = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
            o, hi, lo, c, v = values
            if (not all(math.isfinite(x) for x in values) or min(o, hi, lo, c) <= 0
                    or v < 0 or hi < max(o, c) or lo > min(o, c)):
                raise ValueError("Spot OHLCV invalid")
            h.update((str(day) + "," + ",".join(format(x, ".17g") for x in values) + "\n").encode())
            observed[day] = c, v
            prev = day
            if day == last:
                break
    if prev != last or len(observed) != 1461 or h.hexdigest() != SPOT_PREFIX_SHA:
        raise ValueError("Spot 2020-2023 prefix does not match preregistered SHA256")
    return observed, {"development_prefix_sha256": h.hexdigest(),
                      "development_rows": len(observed), "first": str(first), "last": str(last)}


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Pure deterministic pivoted Gauss-Jordan, with ridge on non-intercept."""
    n = len(b)
    mat = [a[i][:] + [b[i]] for i in range(n)]
    for j in range(n):
        pivot = max(range(j, n), key=lambda i: abs(mat[i][j]))
        if abs(mat[pivot][j]) < 1e-12:
            raise ValueError("Singular ridge regression")
        mat[j], mat[pivot] = mat[pivot], mat[j]
        d = mat[j][j]
        mat[j] = [x / d for x in mat[j]]
        for i in range(n):
            if i != j:
                factor = mat[i][j]
                mat[i] = [mat[i][k] - factor * mat[j][k] for k in range(n+1)]
    return [x[-1] for x in mat]


PROTOCOL = "BTC_WEEKDAY_INFORMATION_v1_FROZEN_2026-11-18"
RESEARCH_ID = "BTC_WEEKDAY_INFORMATION_v1"
EVAL_START = date(2022, 1, 1)
RIDGE_LAMBDA = 10.0
BLOCK_DAYS = 14
BOOTSTRAPS = 1000
BOOT_SEED = 20261118
MIN_GAIN = 0.02


def build_rows(prices: dict) -> tuple[list[dict], list[dict]]:
    days = sorted(prices)
    closes = [prices[d][0] for d in days]
    volumes = [prices[d][1] for d in days]
    returns = [0.0] + [math.log(closes[i] / closes[i-1]) for i in range(1, len(days))]
    train, test = [], []
    for i in range(35, len(days)):
        k = i - 2  # completed-day buffer: no same-day volume or return in controls
        trailing = returns[k-29:k+1]
        prior_volume = volumes[k-30:k]
        if not prior_volume or mean(prior_volume) <= 0:
            raise ValueError("Insufficient positive reference volume")
        row = {
            "day": days[i], "target": returns[i],
            "features_base": [returns[k], stdev(trailing), math.log1p(volumes[k]) - math.log1p(mean(prior_volume))],
            "weekday_monday": float(days[i].weekday() == 0),
        }
        (train if days[i] < EVAL_START else test).append(row)
    if len(train) < 600 or len(test) != 730 or [len([r for r in test if r["day"].year == y]) for y in (2022, 2023)] != [365, 365]:
        raise ValueError("Frozen calibration/evaluation calendar mismatch")
    return train, test


def fit_predict(train: list[dict], evaluation: list[dict], augmented: bool) -> tuple[list[float], dict]:
    def columns(row):
        return row["features_base"] + ([row["weekday_monday"]] if augmented else [])
    xs = [columns(r) for r in train]
    ys = [r["target"] for r in train]
    dim = len(xs[0])
    avg = [mean(x[j] for x in xs) for j in range(dim)]
    std = [stdev(x[j] for x in xs) for j in range(dim)]
    if min(std) <= 0:
        raise ValueError("Cannot standardize constant predictor")
    def norm(x):
        return [1.] + [(x[j] - avg[j]) / std[j] for j in range(dim)]
    X = [norm(x) for x in xs]
    m = dim + 1
    a = [[sum(x[i]*x[j] for x in X) + (RIDGE_LAMBDA if i == j and i else 0.) for j in range(m)] for i in range(m)]
    b = [sum(x[j] * y for x, y in zip(X, ys)) for j in range(m)]
    beta = solve(a, b)
    return ([sum(z*w for z, w in zip(norm(columns(r)), beta)) for r in evaluation],
            {"intercept_and_standardized_coefficients": beta, "train_mean": avg, "train_sd": std})


def lower_block_gain(delta: list[float]) -> float:
    r = Random(BOOT_SEED)
    n = len(delta)
    values = []
    for _ in range(BOOTSTRAPS):
        picked = []
        while len(picked) < n:
            start = r.randrange(n)
            picked.extend(delta[(start+j) % n] for j in range(BLOCK_DAYS))
        values.append(mean(picked[:n]))
    return sorted(values)[int(0.05 * (BOOTSTRAPS-1))]


def evaluate(prices: dict) -> dict:
    train, test = build_rows(prices)
    base_pred, base_fit = fit_predict(train, test, False)
    aug_pred, aug_fit = fit_predict(train, test, True)
    err_base = [(r["target"] - y)**2 for r, y in zip(test, base_pred)]
    err_aug = [(r["target"] - y)**2 for r, y in zip(test, aug_pred)]
    zero = mean(r["target"]**2 for r in test)
    delta = [x - y for x, y in zip(err_base, err_aug)]
    baseline = mean(err_base)
    augmented = mean(err_aug)
    rel = (baseline - augmented) / baseline
    ci = lower_block_gain(delta)
    annual = {str(y): {"days": sum(r["day"].year == y for r in test),
                       "paired_mse_gain": mean(x for x, r in zip(delta, test) if r["day"].year == y)}
              for y in (2022, 2023)}
    gates = {
        "relative_mse_gain_at_least_2pct": rel >= MIN_GAIN,
        "block_bootstrap_95pct_lower_above_zero": ci > 0.,
        "both_evaluation_years_positive": all(v["paired_mse_gain"] > 0 for v in annual.values()),
        "augmented_beats_fixed_zero_return": augmented < zero,
    }
    passed = all(gates.values())
    return {"research_id": RESEARCH_ID, "protocol": PROTOCOL,
            "status": "PASS_RETROSPECTIVE_MECHANISM_ONLY" if passed else "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
            "decision": "NEEDS_HUMAN_REVIEW" if passed else "ARCHIVED_NON_TRADABLE",
            "training_days": len(train), "evaluation_days": len(test),
            "metrics": {"mse_baseline": baseline, "mse_augmented": augmented,
                        "mse_zero_return": zero, "relative_mse_gain": rel,
                        "paired_gain_block_lower_95": ci, "annual": annual},
            "gates": gates,
            "model_fits": {"baseline": base_fit, "monday_augmented": aug_fit},
            "model": "fixed standardized ridge, lambda=10, Monday only; no day or horizon tuning",
            "point_in_time_literature": "EX_POST; published study may overlap evaluation dates",
            "strategy_backtest_allowed": False, "holdout_evaluated": False, "trading_allowed": False}


def run(spot: Path) -> dict:
    # Reuse the previously pinned 2020-2023 parser; breaks at 2023-12-31.
    prices, provenance = load_spot(spot)
    report = evaluate(prices)
    report["spot"] = provenance
    return report
