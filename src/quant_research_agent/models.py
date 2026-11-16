"""Frozen research contract: the model proposes parameters, not executable code."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

# Source describes non-crypto futures, not proof of profitability for BTC.
SOURCES = {
    "moskowitz2012": {
        "title": "Time series momentum (Moskowitz, Ooi & Pedersen, 2012)",
        "url": "https://doi.org/10.1016/j.jfineco.2011.11.003",
        "scope": "Evidence of time-series momentum in futures; BTC transfer remains a hypothesis.",
    },
}

ALLOWED_FAMILIES = ("sma", "momentum", "breakout")


@dataclass(frozen=True)
class Candidate:
    title: str
    rationale: str
    family: str
    params: dict[str, int]
    source_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict) -> "Candidate":
        if not isinstance(payload, dict):
            raise ValueError("Candidate must be an object")
        expected = {"title", "rationale", "family", "params", "source_ids"}
        actual = set(payload)
        if actual != expected:
            # Field names only. Never log the response body or API credentials.
            raise ValueError(
                "Candidate schema mismatch: "
                f"missing={sorted(expected - actual)}, "
                f"unexpected={sorted(actual - expected)}. "
                "The model or API gateway did not honor the exact candidate schema."
            )
        title, rationale = payload["title"], payload["rationale"]
        if not all(isinstance(x, str) and 10 <= len(x.strip()) <= 600 for x in (title, rationale)):
            raise ValueError("Title and rationale must be substantive strings")
        family, params = payload["family"], payload["params"]
        if family not in ALLOWED_FAMILIES or not isinstance(params, dict):
            raise ValueError("Unknown strategy family")
        required = {"sma": {"fast", "slow"}, "momentum": {"lookback"},
                    "breakout": {"entry", "exit"}}[family]
        if set(params) != required or any(type(v) is not int for v in params.values()):
            raise ValueError("Invalid strategy parameters")
        if family == "sma" and not (20 <= params["fast"] <= 100 < params["slow"] <= 250):
            raise ValueError("SMA parameters out of preregistered range")
        if family == "momentum" and not (60 <= params["lookback"] <= 250):
            raise ValueError("Momentum lookback out of preregistered range")
        if family == "breakout" and not (10 <= params["exit"] < params["entry"] <= 150):
            raise ValueError("Breakout parameters out of preregistered range")
        ids = payload["source_ids"]
        if not isinstance(ids, list) or not ids or len(ids) > 3 or any(x not in SOURCES for x in ids):
            raise ValueError("Unknown/unsupported evidence references")
        return cls(title.strip(), rationale.strip(), family, dict(params), tuple(dict.fromkeys(ids)))

    def as_dict(self) -> dict:
        result = asdict(self)
        result["source_ids"] = list(self.source_ids)
        return result

    @property
    def fingerprint(self) -> str:
        # Hypothesis rephrasing must not permit retesting the same rules.
        rules = {"family": self.family, "params": self.params, "symbol": "BTCUSDT", "interval": "1d"}
        return hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:16]


def seed_candidate() -> Candidate:
    """Explicit deterministic smoke-test hypothesis; NOT AI discovery."""
    return Candidate.from_dict({
        "title": "BTC daily long-only time-series momentum (180-day)",
        "rationale": "Test whether return persistence reported for futures is also present in BTC spot; "
                     "a 180-day close-to-close momentum rule may reduce drawdowns but could lag reversals.",
        "family": "momentum", "params": {"lookback": 180},
        "source_ids": ["moskowitz2012"],
    })
