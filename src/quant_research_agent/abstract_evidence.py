"""Bounded DOI-matched abstract provenance and source-to-experiment review.

This module cannot execute a research study.  It collects publisher-deposited
Crossref metadata and (when missing) OpenAlex indexed abstracts, preserving raw
bytes and quoted, field-level evidence.  OpenAlex is an *index*, not a publisher
attestation; abstract presence is not scientific validity.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib import error, parse, request

from .source_fit import clean_abstract
from .source_fit_audit import verified_stored_paper

VERSION = "ABSTRACT_EVIDENCE_REVIEW_V1_2026_11_20"
_CROSSREF = "api.crossref.org"
_OPENALEX = "api.openalex.org"
_DOI = re.compile(r"^10\.\d{4,9}/[^\s<>]{1,160}$", re.I)
_DAY = re.compile(r"\b(?:day[- ]of[- ]the[- ]week|day[- ]of[- ]week|weekdays?|monday|weekend)\b", re.I)
_CALENDAR = re.compile(r"\b(?:calendar|seasonalit[yies]*|seasonal)\b", re.I)
_BTC = re.compile(r"\b(?:bitcoin|btc)\b", re.I)
_RETURN = re.compile(r"\breturns?\b", re.I)
_STOCK = re.compile(r"\b(?:stocks?|equities|equity|saudi stock exchange|islamic stock)\b", re.I)
_DERIV = re.compile(r"\b(?:bitcoin|btc)\s+(?:futures?|options?|perpetuals?|perps?)\b", re.I)
_HOURLY = re.compile(r"\b(?:hourly|intraday|intra-day|time-of-day|high.frequency)\b", re.I)
_NONCALENDAR = re.compile(r"\b(?:electricity consumption|macroeconomic|cross.markets?|other cryptocurrenc|connectedness)\b", re.I)
_WEEKEND_AS_PRED = re.compile(r"\b(?:using|based\s+on|from)\s+(?:weekend|prior)\s+(?:bitcoin|btc|crypto\w*)\s+returns?\b", re.I)
_ONE_DAY = re.compile(r"\b(?:daily|day-of-the-week|day of the week|weekdays?)\b", re.I)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _normalize(s: str) -> str:
    return " ".join(s.split())


def _evidence(pattern: re.Pattern, title: str, abstract: str) -> dict | None:
    """Quote the exact matching words and source field; never invent evidence."""
    for kind, value in (("title", title), ("abstract", abstract)):
        match = pattern.search(value)
        if match:
            # Preserve at most 12 words of source evidence, not entire abstracts.
            lo = max(0, match.start() - 24)
            hi = min(len(value), match.end() + 40)
            quote = _normalize(value[lo:hi])
            words = quote.split()
            return {"field": kind, "quote": " ".join(words[:12]), "offset": match.start()}
    return None


def analyze(title: str, abstract: str | None, *, source: str) -> dict:
    """Identify scope, with quote-backed features and deliberate abstention.

    This is an evidence review, NOT a paper replication and never grants
    authority to launch a previously archived BTC Monday strategy experiment.
    """
    t = _normalize(title)
    a = clean_abstract(abstract)
    sample = t + ". " + a
    signals = {key: _evidence(pat, t, a) for key, pat in {
        "bitcoin": _BTC, "return": _RETURN, "weekday": _DAY,
        "calendar": _CALENDAR, "equity": _STOCK, "derivative": _DERIV,
        "hourly": _HOURLY, "alternative_predictor": _NONCALENDAR,
        "weekend_crypto_predictor": _WEEKEND_AS_PRED,
        "daily": _ONE_DAY,
    }.items()}
    # A discussion of BTC as an EXPLANATORY variable cannot validate BTC as
    # the dependent variable.  This known counterexample must stay negative.
    stock_target = bool(_STOCK.search(t) or re.search(
        r"\b(?:predict\w*|forecast\w*)\s+.{0,70}\b(?:stock|equity)\s+returns?\b", sample, re.I))
    if stock_target:
        target = "EQUITY_OR_STOCK_RETURNS"
    elif _BTC.search(t) and _RETURN.search(t):
        target = "BTC_RETURNS_PROVISIONAL"
    elif _BTC.search(a) and _RETURN.search(a):
        target = "BTC_RETURNS_UNCONFIRMED_DEPENDENCY"
    else:
        target = "UNRESOLVED"
    if _WEEKEND_AS_PRED.search(sample):
        predictor = "PRIOR_CRYPTO_RETURN"
    elif _DAY.search(sample):
        predictor = "WEEKDAY_OR_MONDAY_CALENDAR"
    elif _CALENDAR.search(sample):
        predictor = "GENERIC_CALENDAR"
    elif _NONCALENDAR.search(sample):
        predictor = "OTHER_MACRO_OR_CROSS_MARKET"
    else:
        predictor = "UNRESOLVED"
    if _DERIV.search(sample):
        market = "BTC_DERIVATIVES"
    elif stock_target:
        market = "EQUITIES"
    elif _BTC.search(sample):
        market = "BTC_MARKET_TYPE_UNVERIFIED"
    else:
        market = "UNRESOLVED"
    frequency = "HOURLY_OR_INTRADAY" if _HOURLY.search(sample) else (
        "DAILY_OR_WEEKDAY" if _ONE_DAY.search(sample) else "UNRESOLVED")
    # An historical calendar effect is NOT the same as evaluating a frozen
    # predictive model: never emit AUTO or approve another experiment.
    reasons = []
    if stock_target:
        decision = "REJECT_TARGET_MISMATCH"
        reasons.append("Paper concerns equity/stock returns; frozen outcome is BTC spot daily return")
    elif _DERIV.search(sample):
        decision = "REJECT_MARKET_MISMATCH"
        reasons.append("BTC derivatives are not the frozen BTC spot target")
    elif frequency == "HOURLY_OR_INTRADAY":
        decision = "REJECT_FREQUENCY_MISMATCH"
        reasons.append("Intraday/hourly evidence cannot be substituted for a daily close-to-close protocol")
    elif predictor == "PRIOR_CRYPTO_RETURN":
        decision = "REJECT_PREDICTOR_MISMATCH"
        reasons.append("Lagged weekend crypto returns are not a known-in-advance Monday indicator")
    elif predictor == "OTHER_MACRO_OR_CROSS_MARKET":
        decision = "REJECT_PREDICTOR_MISMATCH"
        reasons.append("Source predictor differs from the frozen calendar indicator")
    elif not a:
        decision = "NEEDS_HUMAN_SOURCE_REVIEW"
        reasons.append("No DOI-matched indexed abstract was obtainable from approved sources")
    elif target == "BTC_RETURNS_PROVISIONAL" and predictor == "WEEKDAY_OR_MONDAY_CALENDAR":
        decision = "TOPIC_RELATED_PROTOCOL_REVIEW"
        reasons.append("BTC returns and weekday calendar factor are explicit; spot, direction, sample and model equivalence are unverified")
    elif target == "BTC_RETURNS_PROVISIONAL" and predictor == "GENERIC_CALENDAR":
        decision = "NEEDS_HUMAN_SOURCE_REVIEW"
        reasons.append("Generic calendar effect does not identify the fixed Monday indicator")
    else:
        decision = "NEEDS_HUMAN_SOURCE_REVIEW"
        reasons.append("Abstract/title do not establish both BTC return as outcome and Monday-calendar predictor")
    return {
        "version": VERSION, "decision": decision,
        "target": target, "predictor": predictor, "market": market,
        "frequency": frequency,
        "direction": "WEEKEND_CRYPTO_TO_STOCK" if stock_target and predictor == "PRIOR_CRYPTO_RETURN"
                     else "CALENDAR_FACTOR_TO_BTC_RETURN_POSSIBLE" if decision == "TOPIC_RELATED_PROTOCOL_REVIEW"
                     else "UNRESOLVED_OR_MISMATCH",
        "evidence": {k: v for k, v in signals.items() if v is not None},
        "why": reasons,
        "unknowns": ["Exact traded instrument (spot vs derivatives)",
                     "Full paper method and empirical results",
                     "Point-in-time replicability and comparability with the frozen BTC model"],
        "abstract_available": bool(a), "abstract_source": source if a else None,
        "experiment_authorized": False,
        "archived_BTC_Monday_retest_allowed": False,
    }


def decode_openalex(index: object) -> str:
    """Rebuild an abstract only from a complete, non-colliding inverted index."""
    if not isinstance(index, dict) or not index or len(index) > 1500:
        return ""
    positions: dict[int, str] = {}
    for word, offsets in index.items():
        if not isinstance(word, str) or not word or len(word) > 90 or not isinstance(offsets, list):
            return ""
        for n in offsets:
            if type(n) is not int or not 0 <= n < 1500 or n in positions:
                return ""
            positions[n] = word
    if not positions or set(positions) != set(range(len(positions))):
        return ""
    return clean_abstract(" ".join(positions[i] for i in range(len(positions))))


def _doi(value: object) -> str:
    if not isinstance(value, str):
        return ""
    val = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if val.startswith(prefix):
            val = val[len(prefix):]
    return val if _DOI.fullmatch(val) else ""


def crossref_abstract(raw: bytes, expected: str) -> tuple[str, str]:
    obj = json.loads(raw)
    msg = obj.get("message") if isinstance(obj, dict) and obj.get("status") == "ok" else None
    if not isinstance(msg, dict) or _doi(msg.get("DOI")) != expected:
        raise ValueError("Crossref response DOI mismatch")
    title = msg.get("title")
    if not isinstance(title, list) or not title or not isinstance(title[0], str):
        raise ValueError("Crossref response title missing")
    abstract = clean_abstract(msg.get("abstract"))
    return abstract, _normalize(title[0])


def openalex_abstract(raw: bytes, expected: str) -> tuple[str, str]:
    obj = json.loads(raw)
    if not isinstance(obj, dict) or not isinstance(obj.get("results"), list):
        raise ValueError("OpenAlex response schema mismatch")
    results = obj["results"]
    if len(results) > 1:
        raise ValueError("Ambiguous OpenAlex DOI response")
    if not results:
        return "", ""
    item = results[0]
    if not isinstance(item, dict) or _doi(item.get("doi")) != expected:
        raise ValueError("OpenAlex response DOI mismatch")
    if not isinstance(item.get("title"), str):
        raise ValueError("OpenAlex title missing")
    return decode_openalex(item.get("abstract_inverted_index")), _normalize(item["title"])


def source_urls(doi: str) -> tuple[str, str]:
    if _doi(doi) != doi:
        raise ValueError("Only preverified lowercase DOI permitted")
    cref = "https://" + _CROSSREF + "/works/" + parse.quote(doi, safe="")
    params = parse.urlencode({"filter": "doi:https://doi.org/" + doi,
                             "per-page": "1", "select": "doi,title,abstract_inverted_index"})
    return cref, "https://" + _OPENALEX + "/works?" + params


def get_json(url: str) -> bytes:
    """Exact-host HTTPS only, no redirect, limited read, capped timeout."""
    target = parse.urlsplit(url)
    if target.scheme != "https" or target.hostname not in (_CROSSREF, _OPENALEX) or target.username or target.password or target.port:
        raise ValueError("Unexpected abstract evidence origin")
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("Redirect forbidden")
    agent = request.build_opener(NoRedirect)
    req = request.Request(url, headers={"User-Agent": "quant-research-agent-review/0.1",
                                        "Accept": "application/json"})
    with agent.open(req, timeout=12) as handle:
        if handle.status != 200 or parse.urlsplit(handle.geturl()).hostname != target.hostname:
            raise ValueError("Unexpected response source")
        data = handle.read(500_001)
        if len(data) > 500_000:
            raise ValueError("Oversized response")
        return data


def _write_once(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != body:
            raise ValueError("Immutable archive conflict: " + path.name)
        return
    with os.fdopen(fd, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _candidates(root: Path) -> list[dict]:
    dbpath = root / "agent/autonomous_loop.sqlite3"
    if not dbpath.is_file():
        raise ValueError("Existing P1 DOI database not found")
    db = sqlite3.connect(dbpath.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        records = [dict(row) for row in db.execute("SELECT doi,title,publication_year,decision,response_sha FROM papers ORDER BY doi")]
        # Verify every DOI from original archived Crossref bytes, never trust a SQL row alone.
        verified = [verified_stored_paper(root, db, row["doi"]) for row in records]
    finally:
        db.close()
    candidates = []
    for paper, original in zip(records, verified):
        title = original["title"].lower()
        # A fixed relevance ranking, independent of research outcome.
        score = (3 if "bitcoin" in title else 0) + (3 if _DAY.search(title) else 0) + (
            2 if _CALENDAR.search(title) else 0) + (1 if _RETURN.search(title) else 0)
        if score < 5:
            continue
        candidates.append({"doi": paper["doi"], "title": original["title"],
                           "original_response_sha256": paper.get("response_sha") or None,
                           "rank_score": score, "reason": "DOI verified; BTC/weekday/calendar title relevance"})
    return sorted(candidates, key=lambda row: (-row["rank_score"], row["doi"]))


def plan(root: Path, max_papers: int = 5) -> dict:
    if type(max_papers) is not int or not 1 <= max_papers <= 5:
        raise ValueError("max_papers must be 1..5")
    root = root.resolve()
    selected = []
    for paper in _candidates(root):
        marker = root / "agent/evidence_enrichment/claims" / (digest(paper["doi"].encode()) + ".json")
        if not marker.exists():
            selected.append(paper)
        if len(selected) == max_papers:
            break
    return {"status": "EVIDENCE_ENRICHMENT_PLAN", "selected": selected,
            "max_requests": 2 * len(selected), "network_requests": 0,
            "study_runs_allowed": False}


def enrich(root: Path, max_papers: int = 5, *, now: datetime | None = None, fetcher=None) -> dict:
    """One opt-in 5-DOI batch/day, 2 requests/DOI max, never rerun studies."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("UTC now required")
    root = root.resolve()
    if (root / "PAUSED").exists():
        return {"status": "PAUSED", "network_requests": 0}
    plan_result = plan(root, max_papers)
    if not plan_result["selected"]:
        return {"status": "IDLE_NO_NEW_REVIEW_PAPERS", "network_requests": 0}
    claims = root / "agent/evidence_enrichment/claims"
    claims.mkdir(parents=True, exist_ok=True)
    day_path = claims / ("batch-" + now.date().isoformat() + ".json")
    # Claim before touching network.  Interrupted attempts require operator
    # review, not unlimited automatic retries or duplicate API calls.
    try:
        fd = os.open(day_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return {"status": "IDLE_DAILY_EVIDENCE_BUDGET", "network_requests": 0}
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"time": now.isoformat(), "selected": [p["doi"] for p in plan_result["selected"]]}, handle)
    fetched = fetcher or get_json
    entries = []
    network_requests = 0
    for paper in plan_result["selected"]:
        key = digest(paper["doi"].encode())
        path = claims / (key + ".json")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Do not race another process or silently redo a failed attempt.
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"doi": paper["doi"], "claimed_at": now.isoformat()}, handle)
        crossref_url, openalex_url = source_urls(paper["doi"])
        source = "NONE"
        abstract = ""
        provider_errors = []
        provenance = []
        source_integrity_failure = False
        for provider, url in (("Crossref", crossref_url), ("OpenAlex", openalex_url)):
            if source_integrity_failure:
                break
            if provider == "OpenAlex" and abstract:
                break
            network_requests += 1
            try:
                raw = fetched(url)
                if not isinstance(raw, bytes) or len(raw) > 500_000:
                    raise ValueError("Invalid/oversized response")
                a, remote_title = (crossref_abstract(raw, paper["doi"]) if provider == "Crossref" else
                                   openalex_abstract(raw, paper["doi"]))
                # Same DOI has final authority, but titles must not be completely
                # unrelated (DOI registry contamination / wrong work mappings).
                ours = set(re.findall(r"[a-z0-9]+", paper["title"].lower()))
                theirs = set(re.findall(r"[a-z0-9]+", remote_title.lower()))
                if remote_title and (not ours or len(ours & theirs) / len(ours) < 0.5):
                    raise ValueError("DOI title incompatible with archived Crossref metadata")
                evidence_file = root / "agent/evidence_enrichment/raw" / (key + "-" + provider.lower() + ".json")
                _write_once(evidence_file, raw)
                provenance.append({"provider": provider, "request_url": url,
                                   "raw_sha256": digest(raw), "raw_path": str(evidence_file.relative_to(root)),
                                   "doi_verified": True, "observed_at": now.isoformat(),
                                   "has_abstract": bool(a)})
                if a:
                    abstract = a
                    source = provider
            except (OSError, ValueError, json.JSONDecodeError, error.URLError, TypeError) as exc:
                provider_errors.append({"provider": provider, "error_type": type(exc).__name__})
                if isinstance(exc, ValueError) and ("DOI mismatch" in str(exc) or "title incompatible" in str(exc)):
                    source_integrity_failure = True
        analysis = analyze(paper["title"], abstract, source=source)
        # Do NOT reproduce full source abstract in this report; leave it in its
        # SHA256-pinned source API response, and quote only tiny evidence spans.
        entries.append({"doi": paper["doi"], "title": paper["title"],
                        "abstract_status": "AVAILABLE" if abstract else "NOT_AVAILABLE",
                        "abstract_sha256": digest(abstract.encode()) if abstract else None,
                        "provenance": provenance, "provider_errors": provider_errors,
                        "scope": analysis})
    report = {"version": VERSION, "generated_at": now.isoformat(), "entry_count": len(entries),
              "network_requests": network_requests, "max_network_requests": 2 * max_papers,
              "not_a_paper_replication": True, "experiments_executed": 0,
              "previous_study_modified": False, "trading_allowed": False,
              "entries": entries}
    raw = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    h = digest(raw)
    out = root / "agent/reports" / ("abstract-evidence-v1-" + h[:12] + ".json")
    _write_once(out, raw)
    return {"status": "EVIDENCE_REVIEW_ARCHIVED", "report_path": str(out),
            "report_sha256": h, "papers_reviewed": len(entries),
            "network_requests": network_requests, "studies_executed": 0,
            "decisions": {d: sum(e["scope"]["decision"] == d for e in entries)
                          for d in sorted(set(e["scope"]["decision"] for e in entries))}}
