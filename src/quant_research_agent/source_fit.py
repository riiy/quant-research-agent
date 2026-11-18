"""Conservative, evidence-scoped source-to-protocol relevance gate.

Purpose: decide whether a Crossref *metadata record* can justify running the
fixed BTC Monday-return information test. It does NOT verify any study's
findings or generate research protocols. Unknown/ambiguous scope fails closed.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re

GATE_VERSION = "BTC_MONDAY_SOURCE_FIT_V1_2026_11_18"
AUTO = "ELIGIBLE_FOR_FROZEN_TEMPLATE"
REVIEW = "NEEDS_HUMAN_SOURCE_REVIEW"
REJECT_TARGET = "REJECT_TARGET_MISMATCH"
REJECT_PREDICTOR = "REJECT_PREDICTOR_MISMATCH"
REJECT_MARKET = "REJECT_MARKET_MISMATCH"


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_abstract(value: str | None) -> str:
    """Crossref's optional abstract can contain JATS/HTML; never execute it."""
    if not isinstance(value, str) or not value:
        return ""
    if len(value) > 20000:
        return ""  # Oversized text is unavailable evidence, never eligibility.
    try:
        parser = _TextOnly()
        parser.feed(value)
        text = " ".join(parser.parts)
    except (ValueError, TypeError):
        return ""
    return " ".join(text.split())[:8000]


def _find(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


# These expressions identify *the dependent variable*, not mere mention of an
# asset. E.g. "Bitcoin weekend returns predicting Monday stock returns" is a
# STOCK-market-target paper, even though the title contains 'bitcoin returns'.
_STOCK_AS_TARGET = (
    r"\b(?:predict(?:ing|s|ed)?|forecast(?:ing|s|ed)?|explain(?:ing|s|ed)?)"
    r"\s+(?:\w+[ -]+){0,5}?(?:stock|equity|equities|s\s*&\s*p\s*500)"
    r"(?:\s+market)?\s+returns?\b",
    r"\b(?:stock|equity|equities)\s+(?:market\s+)?returns?\s+"
    r"(?:are\s+|is\s+|can\s+be\s+)?(?:predict(?:ed|able)?|forecast|explained)\b",
    r"\b(?:bitcoin|btc|crypto(?:currency)?)\s+returns?\s+"
    r"(?:predict|forecast|lead|explain)\s+(?:\w+[ -]+){0,5}?"
    r"(?:stocks?|equities|equity\s+returns?)\b",
)
_BTC_DERIVATIVES = r"\b(?:bitcoin|btc)\s+(?:futures?|perpetuals?|perps?|options?)\b"
# Source predictor is some *return-derived input*, not the Monday dummy used
# by the frozen template. If this wording appears in a predictive claim,
# require a separately approved protocol rather than extrapolating.
_OTHER_PREDICTOR = (
    r"\b(?:predict(?:ing)?|forecast(?:ing)?)\s+(?:\w+[ -]+){0,5}?"
    r"(?:using|with|based\s+on|from)\s+(?:\w+[ -]+){0,5}?"
    r"(?:weekend|prior|lagged)\s+(?:bitcoin|btc|crypto(?:currency)?)\s+returns?\b",
    r"\b(?:using|based\s+on|from)\s+(?:weekend|prior|lagged)\s+"
    r"(?:bitcoin|btc|crypto(?:currency)?)\s+returns?\b",
    r"\b(?:using|based\s+on)\s+(?:funding\s+rates?|tweets?|sentiment|search\s+volume)\b",
)
_BTC_RETURN_TARGET = (
    r"\b(?:bitcoin|btc)(?:\s+spot)?(?:\s+(?:daily|monday|weekday|day-of-the-week))?\s+returns?\b",
    r"\breturns?\s+(?:of|on|in|for)\s+(?:bitcoin|btc)(?:\s+spot)?\b",
)
_DAY_OF_WEEK = (
    r"\bmonday\b",
    r"\bday[- ]of[- ]the[- ]week\b",
    r"\bday[- ]of[- ]week\b",
    r"\bweekday\b",
)
# 'Weekend effect' and generic 'calendar anomaly' by themselves do not prove
# the frozen Monday dummy is the proposed explanatory variable.
_CALENDAR_METHOD = r"\b(?:effect|effects|anomal(?:y|ies)|seasonal(?:ity)?|patterns?|predict(?:ive|ability|ion)?)\b"


def _any(patterns: tuple[str, ...], text: str) -> bool:
    return any(_find(p, text) for p in patterns)


def assess_source(title: str, abstract: str | None = None) -> dict:
    """High-precision suitability gate, NOT a claim about a paper's results.

    Auto-eligibility requires both title and nonempty abstract to explicitly
    support BTC return as *outcome* and a weekday/Monday calendar factor as the
    candidate feature. Directional, market, or predictor contradictions veto.
    """
    t = " ".join(title.split()) if isinstance(title, str) else ""
    a = clean_abstract(abstract)
    combined = t + " " + a
    target = "BTC_SPOT_DAILY_LOG_RETURN" if _any(_BTC_RETURN_TARGET, combined) else "UNRESOLVED"
    method = "MONDAY_OR_WEEKDAY_CALENDAR" if _any(_DAY_OF_WEEK, combined) else "UNRESOLVED"
    info = {
        "gate_version": GATE_VERSION,
        "expected_target": "BTC_SPOT_DAILY_LOG_RETURN",
        "expected_predictor": "MONDAY_CALENDAR_INDICATOR",
        "expected_timing": "TARGET_DAY_CALENDAR_KNOWN_BEFORE_TARGET_RETURN",
        "detected_target": target,
        "detected_predictor_scope": method,
        "abstract_available": bool(a),
        "evidence_level": "CROSSREF_TITLE_AND_ABSTRACT" if a else "CROSSREF_TITLE_ONLY",
        "not_a_paper_replication": True,
    }

    def result(decision: str, reason: str) -> dict:
        return {**info, "decision": decision, "reason_code": reason}

    # Contradictions outrank the mere presence of 'Bitcoin'/'Monday'.
    if _any(_STOCK_AS_TARGET, combined):
        return result(REJECT_TARGET, "STOCK_RETURNS_ARE_PREDICTED_OUTCOME")
    if _find(_BTC_DERIVATIVES, combined):
        return result(REJECT_MARKET, "BTC_DERIVATIVE_MARKET_NOT_SPOT")
    if _any(_OTHER_PREDICTOR, combined):
        return result(REJECT_PREDICTOR, "SOURCE_USES_DIFFERENT_PREDICTOR")
    if not _any(_BTC_RETURN_TARGET, t):
        return result(REVIEW, "BTC_RETURN_DEPENDENT_VARIABLE_NOT_EXPLICIT_IN_TITLE")
    if not _any(_DAY_OF_WEEK, t) or not _find(_CALENDAR_METHOD, t):
        return result(REVIEW, "MONDAY_OR_WEEKDAY_FACTOR_NOT_EXPLICIT_IN_TITLE")
    if not a:
        return result(REVIEW, "ABSTRACT_UNAVAILABLE_TO_CONFIRM_DIRECTION")
    if not _any(_BTC_RETURN_TARGET, a):
        return result(REVIEW, "ABSTRACT_DOES_NOT_CONFIRM_BTC_RETURN_TARGET")
    if not _any(_DAY_OF_WEEK, a):
        return result(REVIEW, "ABSTRACT_DOES_NOT_CONFIRM_WEEKDAY_FACTOR")
    return result(AUTO, "METADATA_MATCHES_FROZEN_TARGET_AND_CALENDAR_FACTOR")
