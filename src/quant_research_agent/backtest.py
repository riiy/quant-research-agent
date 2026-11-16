"""Fixed long-only spot simulation. No order routing and no intrabar lookahead."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from math import sqrt
from statistics import mean, stdev
from typing import Callable

from .data import Bar
from .models import Candidate


@dataclass(frozen=True)
class Summary:
    start: str
    end: str
    days: int
    total_return: float
    buy_hold_return: float
    excess_return: float
    max_drawdown: float
    buy_hold_max_drawdown: float
    sharpe: float
    entries: int
    completed_trades: int
    exposure: float

    def as_dict(self) -> dict:
        return asdict(self)


def _mean_at(values: list[float], end: int, n: int) -> float | None:
    if end + 1 < n:
        return None
    return sum(values[end - n + 1 : end + 1]) / n


def signal(candidate: Candidate, closes: list[float], end: int) -> bool:
    """Desired position as of close[end]. Can only trade on following day's open."""
    p = candidate.params
    if candidate.family == "sma":
        fast, slow = _mean_at(closes, end, p["fast"]), _mean_at(closes, end, p["slow"])
        return fast is not None and slow is not None and fast > slow
    if candidate.family == "momentum":
        return end >= p["lookback"] and closes[end] > closes[end - p["lookback"]]
    # Breakout is a stateful family; execution uses separate entry/exit rules.
    raise ValueError("Breakout requires stateful signal; call _desired")


def _desired(candidate: Candidate, closes: list[float], yesterday: int, invested: bool) -> bool:
    if candidate.family != "breakout":
        return signal(candidate, closes, yesterday)
    p = candidate.params
    if invested:
        n = p["exit"]
        return not (yesterday >= n and closes[yesterday] < min(closes[yesterday - n:yesterday]))
    n = p["entry"]
    return yesterday >= n and closes[yesterday] > max(closes[yesterday - n:yesterday])


def _max_drawdown(values: list[float]) -> float:
    high, worst = values[0], 0.0
    for v in values:
        high = max(high, v)
        worst = min(worst, v / high - 1.0)
    return worst


def simulate(bars: list[Bar], candidate: Candidate, start: date, end: date,
             fee: float = 0.001, slippage: float = 0.0005) -> Summary:
    """Each evaluation window starts in cash, including its buy-and-hold comparator.

    Pre-window bars may be used ONLY for rolling signals, never for positions or P&L.
    Both strategies pay fee and slippage. End positions are marked at final close.
    """
    if fee < 0 or slippage < 0 or fee >= 1 or slippage >= 1:
        raise ValueError("Fee/slippage out of range")
    selected = [i for i, b in enumerate(bars) if start <= b.day <= end]
    if not selected:
        raise ValueError(f"No bars in evaluation window {start}..{end}")
    if bars[selected[0]].day != start or bars[selected[-1]].day != end:
        raise ValueError("Evaluation window missing boundary dates")
    closes = [b.close for b in bars]
    cash, qty = 1.0, 0.0
    bh_qty = (1.0 / (bars[selected[0]].open * (1 + slippage) * (1 + fee)))
    curve, baseline = [1.0], [1.0]
    entries, completed, invested_days = 0, 0, 0
    for idx in selected:
        bar = bars[idx]
        desired = idx > 0 and _desired(candidate, closes, idx - 1, qty > 0)
        if desired and qty == 0:
            execution = bar.open * (1 + slippage)
            qty = cash / (execution * (1 + fee))
            cash = 0.0
            entries += 1
        elif not desired and qty > 0:
            execution = bar.open * (1 - slippage)
            cash = qty * execution * (1 - fee)
            qty = 0.0
            completed += 1
        invested_days += int(qty > 0)
        curve.append(cash + qty * bar.close)
        baseline.append(bh_qty * bar.close)
    daily = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve))]
    sharpe = (sqrt(365) * mean(daily) / stdev(daily)) if len(daily) > 1 and stdev(daily) > 0 else 0.0
    strat_ret, benchmark_ret = curve[-1] - 1, baseline[-1] - 1
    return Summary(str(start), str(end), len(selected), strat_ret, benchmark_ret,
                   strat_ret - benchmark_ret, _max_drawdown(curve), _max_drawdown(baseline),
                   sharpe, entries, completed, invested_days / len(selected))


def assess(validation: Summary, stress: Summary) -> tuple[str, list[str]]:
    """Preregistered screen, not a claim of alpha or simulation approval."""
    reasons = []
    if validation.entries < 2:
        reasons.append("Fewer than 2 validation entries: insufficient evidence")
    if validation.total_return <= 0:
        reasons.append("Validation absolute net return is not positive")
    if validation.excess_return <= 0:
        reasons.append("Validation net return does not beat fee-adjusted buy-and-hold")
    if stress.excess_return <= 0:
        reasons.append("Twice-cost validation does not beat its cost-adjusted benchmark")
    if reasons:
        return "ARCHIVED_REJECTED_OR_INCONCLUSIVE", reasons
    return "PENDING_SEALED_HOLDOUT", ["Initial screening passed; NOT evidence of stable alpha"]
