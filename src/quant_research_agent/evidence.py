"""Fixed, human-curated evidence registry. Papers are hypotheses, not BTC alpha proofs.

Published titles, DOIs, and narrow abstracts checked against publisher/NBER pages.
No model-generated bibliographic URLs or live literature browsing are allowed.
"""

SOURCES = {
    "moskowitz2012": {
        "title": "Time Series Momentum — Moskowitz, Ooi, Pedersen (2012)",
        "url": "https://doi.org/10.1016/j.jfineco.2011.11.003",
        "universe": "Futures across asset classes, not BTC spot",
        "finding": "Evidence of time-series momentum in futures; transfer to BTC is unverified.",
    },
    "liu_tsyvinski2021": {
        "title": "Risks and Returns of Cryptocurrency — Liu and Tsyvinski (2021)",
        "url": "https://doi.org/10.1093/rfs/hhaa113",
        "universe": "Cryptocurrencies including Bitcoin; time series and investor attention",
        "finding": "Reports crypto time-series momentum and relationships with investor attention; not a deployable net-of-cost BTC strategy.",
    },
    "moreira_muir2017": {
        "title": "Volatility-Managed Portfolios — Moreira and Muir (2017)",
        "url": "https://doi.org/10.1111/jofi.12513",
        "universe": "Equity/style factors and currency carry, not BTC spot",
        "finding": "Lower factor exposure after elevated realized volatility may improve risk-adjusted outcomes; BTC transfer and all-cash implementation are not established.",
    },
    "zaremba2021": {
        "title": "Up or Down? Short-Term Reversal, Momentum, and Liquidity Effects — Zaremba et al. (2021)",
        "url": "https://doi.org/10.1016/j.irfa.2021.101908",
        "universe": "Cross-sectional cryptocurrency portfolios, mostly smaller/illiquid coins",
        "finding": "Reversal concentrates in illiquid cryptoassets; the largest liquid coins exhibit daily momentum, opposing naive BTC reversal transfer.",
    },
    "bianchi2022": {
        "title": "Trading Volume and Liquidity Provision in Cryptocurrency Markets — Bianchi, Babiak, Dickerson (2022)",
        "url": "https://doi.org/10.1016/j.jbankfin.2022.106547",
        "universe": "Cross-section of USD crypto trading pairs, especially illiquid pairs",
        "finding": "Liquidity-provision/reversal returns are concentrated in low-activity pairs; not evidence for BTC daily long-only reversal.",
    },
    "smales2022": {
        "title": "Investor Attention in Cryptocurrency Markets — Smales (2022)",
        "url": "https://doi.org/10.1016/j.irfa.2021.101972",
        "universe": "Bitcoin and other cryptocurrencies with Google search volume proxies",
        "finding": "Google search attention relates to returns, volatility and liquidity; attention proxies are not present in an OHLCV-only dataset.",
    },
}

# Important: these are *research mechanisms*, not implementations of live strategies.
# Evidence class is assigned by humans from the studies' universes; no LLM scoring.
MECHANISMS = {
    "volatility_exposure": {
        "question": "Can a BTC long/cash exposure policy responding to prior realized volatility improve risk-adjusted results after costs?",
        "mechanism": "volatility-risk-management",
        "sources": ["moreira_muir2017"],
        "evidence_scope": "TRANSFER_FROM_NONCRYPTO_FACTORS",
        "evidence_points": 1,
        "required_data": ["daily_ohlcv"],
        "baseline": "BTC buy-and-hold plus predeclared risk/exposure-matched baseline",
        "failure_rule": "Reject if no out-of-sample risk-adjusted improvement after fees, or if risk reduction is explainable only by less BTC exposure.",
        "execution_status": "RULE_NOT_IMPLEMENTED",
        "priority": 1,
    },
    "attention_demand": {
        "question": "Does measured investor search attention contain BTC predictive information beyond BTC price and volume?",
        "mechanism": "attention-demand",
        "sources": ["liu_tsyvinski2021", "smales2022"],
        "evidence_scope": "CRYPTO_EMPIRICAL_WITH_EXTERNAL_SIGNAL",
        "evidence_points": 2,
        "required_data": ["daily_ohlcv", "google_search_volume"],
        "baseline": "BTC buy-and-hold and OHLCV-only control",
        "failure_rule": "Reject if incremental out-of-sample net performance over OHLCV control is not positive.",
        "execution_status": "EXTERNAL_DATA_REQUIRED",
        "priority": 2,
    },
    "liquidity_reversal": {
        "question": "Does cross-sectional illiquidity-induced short-horizon reversal transfer to BTC spot?",
        "mechanism": "liquidity-provision-reversal",
        "sources": ["zaremba2021", "bianchi2022"],
        "evidence_scope": "CONTRADICTORY_FOR_LIQUID_BTC",
        "evidence_points": 0,
        "required_data": ["multi_asset_liquidity_panel"],
        "baseline": "BTC buy-and-hold and direct BTC one-day momentum control",
        "failure_rule": "Do not test BTC-only reversal based on evidence concentrated in small illiquid coins.",
        "execution_status": "MARKET_SCOPE_MISMATCH",
        "priority": 3,
    },
    "trend_persistence": {
        "question": "Is BTC daily trend-following robust after costs?",
        "mechanism": "trend-persistence",
        "sources": ["moskowitz2012", "liu_tsyvinski2021"],
        "evidence_scope": "CRYPTO_EMPIRICAL_BUT_EXISTING_LOCAL_FAILURE",
        "evidence_points": 2,
        "required_data": ["daily_ohlcv"],
        "baseline": "BTC buy-and-hold",
        "failure_rule": "The archived BTC 120-day momentum experiment failed its 2024 excess-return screen; do not retune related trend families.",
        "execution_status": "SATURATED_LOCAL_FAMILY",
        "priority": 4,
    },
}

AVAILABLE_DATA = frozenset({"daily_ohlcv"})
TREND_FAMILIES = frozenset({"sma", "momentum", "breakout"})


def mechanism_screen(mechanism_id: str, seen: set[str] | frozenset[str] = frozenset()) -> dict:
    """Deterministic feasibility screen *before* model calls or market backtests."""
    if mechanism_id not in MECHANISMS:
        raise ValueError("Unknown research mechanism")
    m = MECHANISMS[mechanism_id]
    missing = sorted(set(m["required_data"]) - AVAILABLE_DATA)
    reasons = []
    if m["execution_status"] == "SATURATED_LOCAL_FAMILY":
        reasons.append("Existing archived BTC trend experiment; SMA/breakout/lookback tweaks share this mechanism")
    if m["execution_status"] == "MARKET_SCOPE_MISMATCH":
        reasons.append("Cross-sectional low-liquidity reversal literature does not support BTC-only reversal")
    if missing:
        reasons.append("Required input data unavailable: " + ", ".join(missing))
    if mechanism_id in seen:
        reasons.append("Mechanism already screened; no new parameter or wording variants")
    return {
        "mechanism_id": mechanism_id,
        "status": "BLOCKED" if reasons else "ELIGIBLE_FOR_IDEA_ONLY",
        "score": {
            "evidence_relevance": m["evidence_points"],  # 0..2, not an alpha probability
            "data_feasibility": 2 if not missing else 0,
            "novelty": 0 if mechanism_id in seen or m["execution_status"] == "SATURATED_LOCAL_FAMILY" else 2,
            "total": m["evidence_points"] + (2 if not missing else 0) + (0 if mechanism_id in seen or m["execution_status"] == "SATURATED_LOCAL_FAMILY" else 2),
        },
        "reasons": reasons,
        "baseline": m["baseline"],
        "kill_test": m["failure_rule"],
        "execution_status": m["execution_status"],
    }


def next_feasible_mechanism(seen: set[str]) -> str | None:
    for name in sorted(MECHANISMS, key=lambda key: MECHANISMS[key]["priority"]):
        if mechanism_screen(name, seen)["status"] == "ELIGIBLE_FOR_IDEA_ONLY":
            return name
    return None


def legacy_trend_researched(store) -> bool:
    """Stop repeated *real* SMA/momentum/breakout searches before paid model calls.

    All three currently share a trend-persistence economic mechanism. Existing
    deterministic demo rows do not consume the real research mechanism.
    """
    import json
    for item in store.list(limit=100000):
        row = store.get(item["id"])
        if row and not row["status"].startswith("DEMO_"):
            if json.loads(row["candidate_json"]).get("family") in TREND_FAMILIES:
                return True
    return False
