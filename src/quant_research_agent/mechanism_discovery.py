"""P2-A offline mechanism/protocol gate. Never calls models, networks or runners.

Inputs are *untrusted* model-authored proposals and P1 DOI-verified evidence.
Passing the gate means human review is possible, never scientific novelty or execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .abstract_evidence import crossref_abstract, openalex_abstract, analyze

VERSION = "AUTONOMOUS_MECHANISM_DISCOVERY_V1_GATE"
ARCHIVED = frozenset({
    "trend_persistence", "volatility_exposure", "derivatives_leverage_pressure",
    "investor_attention_demand", "calendar_weekday", "liquidity_reversal",
})
# High-confidence counterexamples only. A miss NEVER confers novelty.
OLD_CHANNELS = {
    "trend_persistence": (r"\bmomentum\b", r"\btrend.follow", r"\bbreakout\b", r"\bmoving.average\b"),
    "volatility_exposure": (r"volatility.manag", r"volatility.target", r"volatility.timing", r"risk.parity"),
    "derivatives_leverage_pressure": (r"funding.rate", r"perpetual.funding", r"leverag(?:e|ed).pressure"),
    "investor_attention_demand": (r"google.trends", r"search.attention", r"investor.attention"),
    "calendar_weekday": (r"monday.effect", r"day.of.the.week", r"weekday.effect", r"calendar.anomal"),
    "liquidity_reversal": (r"illiquid.*reversal", r"liquidity.provision.*reversal"),
}
TOP = {"schema_version", "doi", "mechanism_id", "mechanism", "source_quotes", "novelty", "protocol", "execution_authorized"}
MECHANISM = {"name", "family", "actors", "friction_or_incentive", "causal_chain", "conditions", "why_not_indicator", "counterevidence"}
NOVELTY = {"closest_archived", "shared_features", "economic_difference", "relabel_risk"}
PROTOCOL = {"hypothesis", "null", "falsifier", "target", "predictor", "data", "sample", "baseline", "method", "oos", "metrics", "pass_rule", "stop_rule", "leakage_checks", "costs_and_execution", "budget", "human_escalation"}
TARGET = {"market", "instrument", "variable", "frequency", "horizon"}
PREDICTOR = {"variable", "proxy", "available_at", "publication_lag"}
DATA = {"name", "provider", "availability", "point_in_time", "timestamp_rule"}
SAMPLE = {"calibration", "evaluation", "sealed_holdout_excluded"}
BUDGET = {"max_research_hours", "max_new_network_requests", "max_model_calls", "max_spend_usd"}
DOI = re.compile(r"^10\.\d{4,9}/[^\s<>]{1,160}$", re.I)
IDENT = re.compile(r"^[a-z][a-z0-9_]{5,79}$")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _object(value: object, fields: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(label + ": exact schema required")
    return value


def _text(value: object, label: str, *, minimum: int = 8, maximum: int = 1200) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(label + ": nonempty bounded explanation required")
    return value.strip()


def _read_local(root: Path, relative: str, limit: int) -> bytes:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Relative runtime path required")
    path = root / relative
    if not path.resolve().is_relative_to(root) or not path.is_file() or path.is_symlink() or path.stat().st_size > limit:
        raise ValueError("Evidence file missing, unsafe or too large")
    return path.read_bytes()


def verified_evidence(root: Path, report_path: str, doi: str) -> dict:
    """Read only content-addressed P1 report and DOI-bound indexed raw bytes."""
    if not DOI.fullmatch(doi) or doi != doi.lower():
        raise ValueError("Invalid DOI")
    name = Path(report_path).name
    if not re.fullmatch(r"abstract-evidence-v1-[a-f0-9]{12}\.json", name) or report_path != "agent/reports/" + name:
        raise ValueError("Only archived P1 evidence reports permitted")
    raw = _read_local(root, report_path, 2_000_000)
    if _sha(raw)[:12] != name.removeprefix("abstract-evidence-v1-").removesuffix(".json"):
        raise ValueError("Evidence report digest mismatch")
    report = json.loads(raw)
    if report.get("experiments_executed") != 0 or report.get("trading_allowed") is not False or not isinstance(report.get("entries"), list):
        raise ValueError("Unexpected source report status")
    rows = [row for row in report["entries"] if isinstance(row, dict) and row.get("doi") == doi]
    if len(rows) != 1 or rows[0].get("abstract_status") != "AVAILABLE":
        raise ValueError("No unique DOI-matched abstract")
    entry = rows[0]
    for item in entry.get("provenance", []):
        if not isinstance(item, dict) or not item.get("has_abstract") or not item.get("doi_verified"):
            continue
        provider = item.get("provider")
        if provider not in ("Crossref", "OpenAlex"):
            continue
        path = item.get("raw_path")
        if not isinstance(path, str) or not path.startswith("agent/evidence_enrichment/raw/"):
            raise ValueError("Unexpected source raw path")
        payload = _read_local(root, path, 500_000)
        if _sha(payload) != item.get("raw_sha256"):
            raise ValueError("Evidence raw response digest mismatch")
        abstract, title = (crossref_abstract(payload, doi) if provider == "Crossref" else openalex_abstract(payload, doi))
        if not abstract or not isinstance(entry.get("title"), str):
            continue
        ours = set(re.findall(r"[a-z0-9]+", entry["title"].lower()))
        theirs = set(re.findall(r"[a-z0-9]+", title.lower()))
        if not ours or len(ours & theirs) / len(ours) < .5 or _sha(abstract.encode()) != entry.get("abstract_sha256"):
            raise ValueError("Source title/abstract mismatch")
        return {"doi": doi, "title": title, "abstract": abstract, "provider": provider,
                "raw_sha256": _sha(payload), "report_sha256": _sha(raw),
                "observed_at": item.get("observed_at"), "scope": analyze(title, abstract, source=provider)}
    raise ValueError("No hash-verified source abstract")


def validate(proposal: object, source: dict) -> tuple[str, list[str]]:
    """Deterministic safety checks; semantic novelty always remains unproven."""
    p = _object(proposal, TOP, "proposal")
    if type(p["schema_version"]) is not int or p["schema_version"] != 1 or p["execution_authorized"] is not False:
        raise ValueError("Proposal cannot authorize execution")
    if p["doi"] != source["doi"] or not isinstance(p["mechanism_id"], str) or not IDENT.fullmatch(p["mechanism_id"]):
        raise ValueError("Source DOI or mechanism identity mismatch")
    m = _object(p["mechanism"], MECHANISM, "mechanism")
    n = _object(p["novelty"], NOVELTY, "novelty")
    pr = _object(p["protocol"], PROTOCOL, "protocol")
    _object(pr["target"], TARGET, "target")
    _object(pr["predictor"], PREDICTOR, "predictor")
    _object(pr["sample"], SAMPLE, "sample")
    b = _object(pr["budget"], BUDGET, "budget")
    for obj, label in ((m, "mechanism"), (n, "novelty")):
        for key, val in obj.items():
            _text(val, label + "." + key, minimum=3 if key in ("family", "closest_archived") else 12)
    for key in ("hypothesis", "null", "falsifier", "baseline", "method", "oos", "pass_rule", "stop_rule", "costs_and_execution", "human_escalation"):
        _text(pr[key], "protocol." + key, minimum=12)
    for key, val in pr["target"].items():
        _text(val, "target." + key, minimum=2)
    for key, val in pr["predictor"].items():
        _text(val, "predictor." + key, minimum=5)
    for key, val in pr["sample"].items():
        if key != "sealed_holdout_excluded":
            _text(val, "sample." + key, minimum=5)
    if pr["sample"]["sealed_holdout_excluded"] is not True:
        raise ValueError("Sealed holdout must be excluded")
    for key in ("metrics", "leakage_checks"):
        values = pr[key]
        if not isinstance(values, list) or not 1 <= len(values) <= 8:
            raise ValueError("Missing " + key)
        for val in values:
            _text(val, key, minimum=8)
    if not isinstance(pr["data"], list) or not 1 <= len(pr["data"]) <= 5:
        raise ValueError("At least one named dataset and proxy required")
    missing = []
    for d in pr["data"]:
        _object(d, DATA, "dataset")
        for key in ("name", "provider", "point_in_time", "timestamp_rule"):
            _text(d[key], "data." + key, minimum=5)
        if d["availability"] not in ("UNVERIFIED", "OPERATOR_VERIFICATION_REQUIRED"):
            raise ValueError("Model may not self-certify data availability")
        missing.append(d["name"])
    if (type(b["max_research_hours"]) not in (int, float) or not 0 < b["max_research_hours"] <= 8 or
        any(type(b[k]) is not int or b[k] != 0 for k in ("max_new_network_requests", "max_model_calls")) or
        type(b["max_spend_usd"]) not in (int, float) or b["max_spend_usd"] != 0):
        raise ValueError("Unapproved execution or financial budget")
    quotes = p["source_quotes"]
    if not isinstance(quotes, list) or not 1 <= len(quotes) <= 3:
        raise ValueError("At least one verifiable source quote required")
    normalized_abstract = " ".join(source["abstract"].split()).casefold()
    for q in quotes:
        _object(q, {"quote", "interpretation"}, "quote")
        quote = _text(q["quote"], "quote", minimum=16, maximum=240)
        _text(q["interpretation"], "interpretation", minimum=12)
        if " ".join(quote.split()).casefold() not in normalized_abstract:
            raise ValueError("Invented or unsupported source quote")
    channel = " ".join(m[k] for k in ("name", "family", "actors", "friction_or_incentive", "causal_chain")).lower()
    if n["closest_archived"] not in ARCHIVED:
        raise ValueError("Novelty comparison must name a known archived mechanism")
    if (p["mechanism_id"] in ARCHIVED or m["family"] in ARCHIVED or
        any(re.search(pattern, channel) for patterns in OLD_CHANNELS.values() for pattern in patterns)):
        return "REJECT_ARCHIVED_MECHANISM", ["Canonical/known synonym of previously screened or archived economic channel"]
    scope = source["scope"]
    if scope["target"] == "EQUITY_OR_STOCK_RETURNS" and "btc" in pr["target"]["instrument"].lower():
        return "REJECT_SOURCE_TARGET_MISMATCH", ["Source predicts equities, proposed target is BTC"]
    if scope["market"] == "BTC_DERIVATIVES" and "spot" in pr["target"]["market"].lower():
        return "NEEDS_HUMAN_SOURCE_SCOPE_REVIEW", ["Derivatives source does not directly establish spot target"]
    if scope["frequency"] == "HOURLY_OR_INTRADAY" and "daily" in pr["target"]["frequency"].lower():
        return "NEEDS_HUMAN_SOURCE_SCOPE_REVIEW", ["High-frequency source may motivate, but not validate, daily protocol"]
    return "NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW", [
        "Novelty is a model inference, not independently verified",
        "Data provenance/availability has not been operator-verified: " + ", ".join(missing),
        "No experiment or model execution authorized",
    ]


def review(root: Path, evidence_report: str, proposal_path: str | None) -> dict:
    root = root.resolve()
    if (root / "PAUSED").exists():
        return {"status": "PAUSED", "experiments_executed": 0, "network_requests": 0}
    if proposal_path is None:
        return {"status": "NO_MODEL_PROPOSAL_UNDER_CURRENT_PERMISSIONS", "experiments_executed": 0, "network_requests": 0}
    proposal_bytes = _read_local(root, proposal_path, 80_000)
    p = json.loads(proposal_bytes)
    if type(p) is not dict or not isinstance(p.get("doi"), str):
        raise ValueError("Proposal DOI absent")
    source = verified_evidence(root, evidence_report, p["doi"])
    status, reasons = validate(p, source)
    record = {"version": VERSION, "status": status, "reasons": reasons,
              "proposal_sha256": _sha(proposal_bytes), "proposal": p,
              "source": {k: v for k, v in source.items() if k not in ("abstract",)},
              "source_claims_are_verified_abstract_quotes_only": True,
              "causal_claims_and_novelty_are_unverified_inferences": True,
              "experiments_executed": 0, "model_calls": 0, "network_requests": 0,
              "execution_authorized": False, "trading_allowed": False,
              "account_simulation_allowed": False, "sealed_holdout_access_allowed": False}
    out_bytes = _canonical(record)
    path = root / "agent/mechanism_discovery" / ("protocol-review-" + _sha(out_bytes)[:12] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(out_bytes)
    except FileExistsError:
        if path.read_bytes() != out_bytes:
            raise ValueError("Content-addressed protocol archive conflict")
    return {"status": status, "report_path": str(path), "report_sha256": _sha(out_bytes),
            "source_doi": source["doi"], "experiments_executed": 0, "network_requests": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-mechanism", description="offline P2-A protocol review; no LLM/network/experiment")
    parser.add_argument("--home", type=Path, default=Path("runtime"))
    parser.add_argument("--evidence-report", required=True, help="relative to home, archived abstract-evidence-v1 report")
    parser.add_argument("--proposal", help="relative to home, externally authored JSON proposal; no model calls")
    args = parser.parse_args(argv)
    try:
        result = review(args.home, args.evidence_report, args.proposal)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in ("NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW", "PAUSED", "NO_MODEL_PROPOSAL_UNDER_CURRENT_PERMISSIONS") else 1
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "STOP_PROTOCOL_VALIDATION_ERROR", "error": str(exc)[:240],
                          "experiments_executed": 0, "network_requests": 0}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
