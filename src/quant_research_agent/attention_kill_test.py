"""Frozen retrospective-only BTC attention incremental-prediction Kill Test.

Requires user-provided Google Trends exports and local BTC spot daily OHLCV.
Never reads post-2023 spot prices, never fits on 2022/2023 target returns,
never generates orders, positions, portfolio P&L, or an investable strategy.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
from random import Random
from statistics import mean, stdev

FIRST = date(2020, 1, 1)
LAST = date(2023, 12, 31)
FIRST_WEEK = date(2020, 1, 5)
LAST_WEEK = date(2023, 12, 24)
CAL_LAST = date(2021, 12, 31)
EVAL_START = date(2022, 1, 1)
PROTOCOL = "BTC_ATTENTION_DEMAND_v1_retrospective_incremental_kill_frozen_2026-11-17"
TOPIC_SHA = "99b33105242c99e2b9580de04413c269c38d1988a1fa3a6fd26987d05a341a5f"
TERM_SHA = "8eb882a7984d96bdd4033010263710fc404c0d7add9b77d6d8181a4f82d6e8fe"
SPOT_PREFIX_SHA = "fa5113d1b946ed19ab0eb48d32e05317ef944a6ba12bee79680ba7a247237def"
WEEKLY_OBSERVATIONS = 208
FEATURE_WEEK_LAG = 2
VOL_WEEKS = 4
VOLUME_REF_WEEKS = 4
RIDGE_LAMBDA = 10.0
BLOCK_WEEKS = 4
BOOTSTRAPS = 2000
BOOT_SEED = 20261117
MATERIAL_RELATIVE_MSE_GAIN = 0.05
MIN_TRAIN_WEEKS = 70
MIN_EVAL_WEEKS_PER_YEAR = 40
OUTPUT_NAME = "BTCUSDT-attention-phase1-retrospective-kill-v1.json"


class AttentionError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _weeks():
    d = FIRST_WEEK
    while d <= LAST_WEEK:
        yield d
        d += timedelta(days=7)


def load_trends(path: Path, *, topic: bool) -> tuple[dict[date, int], dict]:
    """Pin original export bytes; ignore its 2019 and partial 2023-12-31 boundary weeks."""
    raw = path.read_bytes()
    expected_sha = TOPIC_SHA if topic else TERM_SHA
    if digest(raw) != expected_sha:
        raise AttentionError("Google Trends raw export SHA256 differs from frozen source")
    lines = raw.decode("utf-8-sig").splitlines()
    if len(lines) < 3 or lines[0] != "Category: All categories" or lines[1] != "":
        raise AttentionError("Unexpected Google Trends export preamble")
    reader = csv.DictReader(io.StringIO("\n".join(lines[2:]) + "\n"))
    value_col = "Bitcoin: (Worldwide)" if topic else "bitcoin: (Worldwide)"
    if reader.fieldnames != ["Week", value_col]:
        raise AttentionError("Google Trends query type/region/header mismatch")
    seen: dict[date, int] = {}
    prev = None
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise AttentionError("Malformed Trends row")
        d = date.fromisoformat(row["Week"])
        if prev is not None and d != prev + timedelta(days=7):
            raise AttentionError("Missing, duplicate, or out-of-order Trends week")
        prev = d
        text = row[value_col]
        if not text.isdigit():
            raise AttentionError("Non-numeric Trends value")
        v = int(text)
        if not 1 <= v <= 100:
            raise AttentionError("Zero/censored or out-of-range Trends value; log ratio undefined")
        if FIRST_WEEK <= d <= LAST_WEEK:
            seen[d] = v
    expected = list(_weeks())
    if list(seen) != expected or len(seen) != WEEKLY_OBSERVATIONS:
        raise AttentionError("Need 208 complete UTC Sunday-start weeks in 2020-2023")
    return seen, {"sha256": expected_sha, "usable_weeks": len(seen), "query": "Topic: /m/05p0rrx" if topic else "Search term: bitcoin"}


def load_spot(path: Path) -> tuple[dict[date, tuple[float, float]], dict]:
    """Consume exactly 2020..2023 OHLCV, breaking at 2023-12-31."""
    prices: dict[date, tuple[float, float]] = {}
    h = hashlib.sha256()
    prev = None
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if set(reader.fieldnames or ()) != {"day", "open", "high", "low", "close", "volume"}:
            raise AttentionError("Spot CSV must contain day/open/high/low/close/volume")
        for row in reader:
            day = date.fromisoformat(row["day"])
            if day > LAST:
                break  # Never read post-2023 OHLCV values.
            if day < FIRST:
                continue
            if (prev is None and day != FIRST) or (prev is not None and day != prev + timedelta(days=1)):
                raise AttentionError("Spot development data gap, duplicate or disorder")
            numbers = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
            o, high, low, close, vol = numbers
            if (not all(math.isfinite(x) for x in numbers) or min(o, high, low, close) <= 0
                    or vol < 0 or high < max(o, close) or low > min(o, close)):
                raise AttentionError("Invalid spot OHLCV")
            h.update((str(day) + "," + ",".join(format(x, ".17g") for x in numbers) + "\n").encode())
            prices[day] = close, vol
            prev = day
            if day == LAST:
                break
    if prev != LAST or len(prices) != 1461:
        raise AttentionError("Need every spot UTC day from 2020-01-01 to 2023-12-31")
    # Source pin is the already audited 2020..2023 spot prefix from funding Phase 1.
    if h.hexdigest() != SPOT_PREFIX_SHA:
        raise AttentionError("Spot development prefix SHA256 differs from previous verified local experiment")
    return prices, {"development_prefix_sha256": h.hexdigest(), "development_rows": len(prices),
                    "first": str(FIRST), "last": str(LAST)}


def weekly_aggregate(prices: dict[date, tuple[float, float]]) -> tuple[list[date], list[float], list[float]]:
    weeks = list(_weeks())
    closes, volume = [], []
    for sunday in weeks:
        close_day = sunday + timedelta(days=6)
        closes.append(prices[close_day][0])
        volume.append(sum(prices[sunday + timedelta(days=j)][1] for j in range(7)))
        if volume[-1] <= 0:
            raise AttentionError("Zero spot volume in complete week")
    return weeks, closes, volume


def construct_rows(prices: dict[date, tuple[float, float]], topic: dict[date, int],
                   term: dict[date, int]) -> tuple[list[dict], list[dict]]:
    weeks, closes, volumes = weekly_aggregate(prices)
    log_close = list(map(math.log, closes))
    rets = [None] + [log_close[i] - log_close[i-1] for i in range(1, len(weeks))]
    train, test = [], []
    for i in range(6, len(weeks)):
        k = i - FEATURE_WEEK_LAG
        # All features are from the fully completed week k (two weekly labels before outcome week i).
        # The entire intervening week i-1 is a conservative publication buffer.
        vol4 = stdev(rets[k-3:k+1])
        relvol = math.log(volumes[k] / mean(volumes[k-4:k]))
        week = weeks[i]
        item = {
            "week": week, "features_base": (rets[k], vol4, relvol),
            "topic_change": math.log(topic[weeks[k]] / topic[weeks[k-1]]),
            "term_change": math.log(term[weeks[k]] / term[weeks[k-1]]),
            "target": rets[i]
        }
        if week + timedelta(days=6) <= CAL_LAST:
            train.append(item)
        elif week >= EVAL_START:
            test.append(item)
        # Week ending 2022-01-01 is neither calibration nor evaluation.
    if len(train) < MIN_TRAIN_WEEKS:
        raise AttentionError("Too few calibration weeks")
    by_year = {year: sum(r["week"].year == year for r in test) for year in (2022, 2023)}
    if min(by_year.values()) < MIN_EVAL_WEEKS_PER_YEAR:
        raise AttentionError("Too few evaluation weeks in either year")
    return train, test


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Small Gauss-Jordan system with pivoting; stdlib only (4/5 parameters)."""
    n = len(b)
    matrix = [a[i][:] + [b[i]] for i in range(n)]
    for j in range(n):
        pivot = max(range(j, n), key=lambda x: abs(matrix[x][j]))
        matrix[j], matrix[pivot] = matrix[pivot], matrix[j]
        if abs(matrix[j][j]) < 1e-12:
            raise AttentionError("Regression singular after ridge penalty")
        d = matrix[j][j]
        matrix[j] = [v / d for v in matrix[j]]
        for i in range(n):
            if i != j:
                factor = matrix[i][j]
                matrix[i] = [matrix[i][t] - factor * matrix[j][t] for t in range(n+1)]
    return [row[-1] for row in matrix]


def fit_predict(train: list[dict], test: list[dict], *, signal: str | None) -> tuple[list[float], dict]:
    def features(row):
        x = list(row["features_base"])
        if signal is not None:
            x.append(row[signal])
        return x
    xs = [features(row) for row in train]
    ys = [r["target"] for r in train]
    p = len(xs[0])
    mu = [mean(x[j] for x in xs) for j in range(p)]
    sd = [stdev(x[j] for x in xs) for j in range(p)]
    if min(sd) <= 0:
        raise AttentionError("Degenerate training feature: cannot standardize")
    def normalize(x):
        return [1.] + [(x[j] - mu[j])/sd[j] for j in range(p)]
    zx = [normalize(x) for x in xs]
    m = p + 1
    lhs = [[sum(row[i]*row[j] for row in zx) + (RIDGE_LAMBDA if i==j and i>0 else 0.)
            for j in range(m)] for i in range(m)]
    rhs = [sum(row[i]*y for row,y in zip(zx,ys)) for i in range(m)]
    beta = solve(lhs, rhs)
    pred = [sum(coef*val for coef,val in zip(beta, normalize(features(r)))) for r in test]
    return pred, {"intercept_and_standardized_coefficients": beta,
                  "train_feature_mean": mu, "train_feature_sd": sd}


def block_lower(delta: list[float]) -> float:
    """Deterministic circular moving-block 95% one-sided lower CI of paired MSE gain."""
    rnd = Random(BOOT_SEED)
    n = len(delta)
    results = []
    for _ in range(BOOTSTRAPS):
        sampled = []
        while len(sampled) < n:
            start = rnd.randrange(n)
            sampled.extend(delta[(start+j) % n] for j in range(BLOCK_WEEKS))
        results.append(mean(sampled[:n]))
    results.sort()
    return results[int(0.05*(BOOTSTRAPS-1))]


def evaluate(train: list[dict], test: list[dict]) -> dict:
    y = [r["target"] for r in test]
    base_pred, base_fit = fit_predict(train, test, signal=None)
    topic_pred, topic_fit = fit_predict(train, test, signal="topic_change")
    term_pred, term_fit = fit_predict(train, test, signal="term_change")
    b_err = [(t-p)**2 for t,p in zip(y,base_pred)]
    t_err = [(t-p)**2 for t,p in zip(y,topic_pred)]
    s_err = [(t-p)**2 for t,p in zip(y,term_pred)]
    naive = [x*x for x in y]  # Frozen no-change/zero-return prediction.
    delta = [b-a for b,a in zip(b_err,t_err)]
    delta_term = [b-a for b,a in zip(b_err,s_err)]
    base_mse = mean(b_err)
    topic_mse = mean(t_err)
    term_mse = mean(s_err)
    naive_mse = mean(naive)
    if base_mse <= 0:
        raise AttentionError("Degenerate baseline MSE")
    rel = (base_mse-topic_mse)/base_mse
    term_rel = (base_mse-term_mse)/base_mse
    years = {}
    for year in (2022, 2023):
        ids = [i for i,r in enumerate(test) if r["week"].year==year]
        years[str(year)] = {
            "weeks": len(ids),
            "baseline_mse": mean(b_err[i] for i in ids),
            "topic_mse": mean(t_err[i] for i in ids),
            "term_mse": mean(s_err[i] for i in ids),
            "paired_topic_mse_gain": mean(delta[i] for i in ids)
        }
    lower = block_lower(delta)
    reasons = []
    if rel < MATERIAL_RELATIVE_MSE_GAIN:
        reasons.append("Topic out-of-sample MSE improvement below predeclared 5% materiality")
    if lower <= 0:
        reasons.append("4-week paired block-bootstrap 95% lower MSE gain bound not above zero")
    if any(years[str(year)]["paired_topic_mse_gain"] <= 0 for year in (2022,2023)):
        reasons.append("Topic incremental effect not positive in both 2022 and 2023")
    if topic_mse >= naive_mse:
        reasons.append("Topic augmented model did not beat frozen zero-return forecast")
    if term_rel <= 0:
        reasons.append("Search-term robustness does not have a positive overall MSE gain")
    return {
        "status": "PASS_RETROSPECTIVE_INCREMENTAL_INFORMATION_ONLY" if not reasons else "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
        "reasons": reasons,
        "training_weeks": len(train), "evaluation_weeks": len(test),
        "metrics": {
            "mse_base": base_mse, "mse_topic": topic_mse,
            "mse_term_robustness": term_mse, "mse_zero_return": naive_mse,
            "relative_topic_mse_gain": rel, "relative_term_mse_gain": term_rel,
            "paired_mse_gain_bootstrap_lower_one_sided_95": lower,
            "annual": years
        },
        "model_fits": {"price_only": base_fit, "topic_augmented": topic_fit, "term_augmented": term_fit}
    }


def run(home: Path, topic_file: Path, term_file: Path, spot_file: Path) -> dict:
    topic, topic_meta = load_trends(topic_file, topic=True)
    term, term_meta = load_trends(term_file, topic=False)
    spot, spot_meta = load_spot(spot_file)
    train,test = construct_rows(spot,topic,term)
    result = evaluate(train,test)
    report = {
        "protocol": PROTOCOL, "research_id": "BTC_ATTENTION_DEMAND_v1",
        "mechanism": "investor_attention_demand", "phase": "RETROSPECTIVE_INCREMENTAL_INFORMATION_ONLY",
        "data": {"topic": topic_meta,"search_term_robustness": term_meta,"spot": spot_meta},
        "calibration": {"through": "2021-12-31", "target_weeks": len(train)},
        "evaluation": {"from": "2022-01-02", "through": "2023-12-24", "weeks": len(test)},
        "gates": {"material_topic_mse_gain": MATERIAL_RELATIVE_MSE_GAIN,
                  "block_bootstrap_weeks": BLOCK_WEEKS,"bootstrap_reps": BOOTSTRAPS,
                  "bootstrap_seed": BOOT_SEED,"one_sided_lower_alpha": 0.05,
                  "annual_positive_gain_required": True,"topic_mse_below_naive_required": True,
                  "search_term_overall_gain_positive_required": True},
        "controls": {"past_week_return": "week t-2", "realized_weekly_volatility": "past 4 weekly returns through t-2",
                     "weekly_base_asset_volume_ratio": "t-2 volume / mean prior 4 weeks"},
        "signal": {"primary": "log(topic[t-2]/topic[t-3])",
                   "robustness": "log(term[t-2]/term[t-3])",
                   "publication_buffer_complete_weeks": 1},
        "model": {"family": "fixed standardized ridge with unpenalized intercept", "ridge_lambda": RIDGE_LAMBDA,
                  "fit_range": "2020-2021 only", "coefficients_refit_in_evaluation": False},
        **result,
        "point_in_time_data": "UNVERIFIED; full-range 2026 Google Trends export is retrospective and rescaled/sampled; NOT historical executable signal",
        "strategy_backtest_allowed": False,"holdout_evaluated": False,"trading_allowed": False
    }
    out_dir = home / "attention"
    out_dir.mkdir(parents=True,exist_ok=True)
    out_path = out_dir / OUTPUT_NAME
    payload = json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False) + "\n"
    if out_path.exists():
        if out_path.read_text(encoding="utf-8") != payload:
            raise AttentionError("Frozen report differs; refusing to overwrite prior evidence")
    else:
        with out_path.open("x",encoding="utf-8") as f:
            f.write(payload)
    return {"status": result["status"],"report": str(out_path),"reasons": result["reasons"],"metrics": result["metrics"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BTC attention retrospective incremental-information Kill Test; no trading")
    parser.add_argument("--home",type=Path,default=Path(os.environ.get("QUANT_HOME","runtime")))
    parser.add_argument("--topic",type=Path,required=True,help="Frozen Bitcoin Cryptocurrency Topic multiTimeline CSV")
    parser.add_argument("--term",type=Path,required=True,help="Frozen bitcoin Search term multiTimeline CSV")
    parser.add_argument("--spot",type=Path,default=None,help="BTC spot day/open/high/low/close/volume file")
    args = parser.parse_args(argv)
    try:
        result = run(args.home,args.topic,args.term,args.spot or args.home/"data"/"BTCUSDT-1d.csv")
    except (AttentionError, OSError, ValueError, UnicodeError) as ex:
        print("ERROR: " + str(ex))
        return 2
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result["status"] == "PASS_RETROSPECTIVE_INCREMENTAL_INFORMATION_ONLY" else 2

if __name__ == "__main__":
    raise SystemExit(main())
