"""P2B-002: one independently approved LLM attempt on P2B-001 frozen, verified evidence.

No literature/network source calls, no P2B-001 writes, no strategy code execution,
no retry and no P0/P1 scheduler integration. One model request at most.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError

from . import abstract_evidence as ae
from . import mechanism_discovery as gate
from . import p2b_pilot as old

ID = "P2B_DISCOVERY_PILOT_002"
PREVIOUS_ID = old.ID
PREVIOUS_MODEL = "chatgpt/gpt6.2-sol"       # Exactly what the rejected request used.
APPROVED_MODEL = "chatgpt/gpt-6.2-sol"      # Exact LiteLLM YAML model_name.
PREVIOUS_RESULT_HASH = "bf07acbb0d831fa4893209eee3bb00073e52debf1c1b33ac6ad13cfe9e98e66e"
PREVIOUS_RESULT_NAME = "result-" + PREVIOUS_RESULT_HASH[:12] + ".json"
MAX_SPEND_USD = 10


def _read(root: Path, rel: str, limit: int) -> bytes:
    return gate._read_local(root, rel, limit)


def verified_replay(root: Path) -> dict:
    """Prove frozen first-attempt request equals our regenerated verified DOI evidence.

    Zero file writes. Refuse changed, missing or mixed first-attempt artifacts.
    """
    previous = root / "p2b" / PREVIOUS_ID
    if not previous.is_dir() or previous.is_symlink():
        raise ValueError("Previous pilot archive unavailable")
    result_raw = _read(previous, PREVIOUS_RESULT_NAME, 100_000)
    if old.sha(result_raw) != PREVIOUS_RESULT_HASH:
        raise ValueError("Original terminal result SHA256 mismatch")
    terminal = json.loads(result_raw)
    if (terminal.get("status") != "STOP_MODEL_OR_PROVENANCE_ERROR"
            or terminal.get("reason_type") != "HTTPError"
            or terminal.get("model_calls") != 1
            or terminal.get("network_requests") != 4
            or terminal.get("experiments_executed") != 0
            or terminal.get("id") != PREVIOUS_ID):
        raise ValueError("Previous pilot terminal record inconsistent")
    if not (previous / "attempt.claim").is_file() or (previous / "model-response.json").exists():
        raise ValueError("Previous attempt claim/model response state inconsistent")

    selection_raw = _read(previous, "source-selection.json", 50_000)
    selected = json.loads(selection_raw)
    if not isinstance(selected, list) or not 1 <= len(selected) <= 3:
        raise ValueError("No frozen source selection")
    selected_dois = []
    for p in selected:
        if (not isinstance(p, dict) or set(p) != {"doi", "title", "published"}
                or ae._doi(p["doi"]) != p["doi"] or
                not isinstance(p["title"], str) or not p["title"].strip() or
                not isinstance(p["published"], str)):
            raise ValueError("Frozen source selection malformed")
        selected_dois.append(p["doi"])
    if len(set(selected_dois)) != len(selected_dois):
        raise ValueError("Frozen selection contains duplicate DOI")

    # Archive search bytes must exist and selected DOIs must occur in the same order.
    search_raw = _read(previous, "search-crossref.json", 1_000_000)
    search = json.loads(search_raw)
    rows = search.get("message", {}).get("items") if search.get("status") == "ok" else None
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValueError("Previous Crossref search archive malformed")
    positions = []
    for p in selected:
        matches = [i for i, row in enumerate(rows) if isinstance(row, dict)
                   and ae._doi(row.get("DOI")) == p["doi"]
                   and isinstance(row.get("title"), list) and row["title"]
                   and isinstance(row["title"][0], str)
                   and " ".join(row["title"][0].split()) == p["title"]
                   and old._published(row) == p["published"]]
        if len(matches) != 1:
            raise ValueError("Frozen selection mismatches original search bytes")
        positions.append(matches[0])
    if positions != sorted(set(positions)):
        raise ValueError("Frozen DOI selection reordered")

    original_adapter = previous / "p2a-adapter"
    if not original_adapter.is_dir() or original_adapter.is_symlink():
        raise ValueError("P2B-001 evidence adapter missing")
    reports_dir = original_adapter / "agent/reports"
    reports = sorted(reports_dir.glob("abstract-evidence-v1-*.json")) if reports_dir.is_dir() else []
    if len(reports) != 1 or reports[0].is_symlink():
        raise ValueError("Expected one unique original evidence report")
    relative_report = "agent/reports/" + reports[0].name
    report_raw = _read(original_adapter, relative_report, 2_000_000)
    if old.sha(report_raw)[:12] != reports[0].name.removeprefix("abstract-evidence-v1-").removesuffix(".json"):
        raise ValueError("Original report content address mismatch")
    report = json.loads(report_raw)
    if (report.get("version") != "P2B_EVIDENCE_ADAPTER_V1"
            or report.get("experiments_executed") != 0 or report.get("trading_allowed") is not False):
        raise ValueError("Previous evidence report not P2B hash adapter")
    entries = report.get("entries")
    if not isinstance(entries, list) or [e.get("doi") for e in entries if isinstance(e, dict)] != selected_dois:
        raise ValueError("Frozen report entry list differs from selection")

    sources, raw_artifacts = [], []
    for selected_paper, entry in zip(selected, entries):
        if not isinstance(entry, dict) or entry.get("title") != selected_paper["title"]:
            raise ValueError("Selected DOI title mismatch in archived report")
        if entry.get("abstract_status") == "NOT_AVAILABLE":
            continue
        if entry.get("abstract_status") != "AVAILABLE":
            raise ValueError("Unknown original abstract status")
        verified = gate.verified_evidence(original_adapter, relative_report, selected_paper["doi"])
        items = entry.get("provenance")
        if not isinstance(items, list) or len(items) != 1:
            raise ValueError("Frozen P2B provider provenance not unique")
        item = items[0]
        relpath = item.get("raw_path")
        if (not isinstance(relpath, str) or
                not relpath.startswith("agent/evidence_enrichment/raw/") or
                item.get("raw_sha256") != verified["raw_sha256"] or
                item.get("provider") != verified["provider"]):
            raise ValueError("Frozen provider response provenance mismatch")
        raw = _read(original_adapter, relpath, 500_000)
        if old.sha(raw) != verified["raw_sha256"]:
            raise ValueError("Archived DOI provider bytes tampered")
        raw_artifacts.append((relpath, raw))
        sources.append({"doi": selected_paper["doi"], "title": selected_paper["title"],
                        "published": selected_paper["published"], "abstract": verified["abstract"],
                        "source_provider": verified["provider"], "source_sha256": verified["raw_sha256"]})
    if not sources:
        raise ValueError("Previous pilot has no verified abstract")
    if len({s["doi"] for s in sources}) != len(sources):
        raise ValueError("Duplicate evidence DOI")

    # Require byte-for-byte match to the exact, previously submitted model payload,
    # rather than selecting/rewriting sources or choosing attractive hypotheses.
    old_request_raw = _read(previous, "model-request.json", old.MAX_INPUT_BYTES)
    expected = old.prepare_request(sources, {"model": PREVIOUS_MODEL, "custom": True})
    if old_request_raw != expected:
        raise ValueError("Previous model request not reproducible from verified DOI evidence")

    fingerprint = {
        "previous_result_sha256": PREVIOUS_RESULT_HASH,
        "source_selection_sha256": old.sha(selection_raw),
        "crossref_search_sha256": old.sha(search_raw),
        "evidence_report_sha256": old.sha(report_raw),
        "previous_model_request_sha256": old.sha(old_request_raw),
        "selected_dois": selected_dois,
        "verified_dois": [e["doi"] for e in sources],
    }
    return {"fingerprint": fingerprint, "sources": sources,
            "report_path": relative_report, "report_bytes": report_raw,
            "provider_bytes": raw_artifacts, "previous_request": old_request_raw}


def replay_request(previous_raw: bytes, cfg: dict) -> bytes:
    data = json.loads(previous_raw)
    if (data.get("model") != PREVIOUS_MODEL or
            data.get("instructions") != old.INSTRUCTIONS or
            data.get("max_output_tokens") != old.MAX_OUTPUT_TOKENS or
            data.get("tools") != []):
        raise ValueError("Previous request details are not frozen as expected")
    text = data["input"][0]["content"][0]["text"]
    evidence = json.loads(text)
    if evidence.get("experiment_id") != PREVIOUS_ID:
        raise ValueError("Old request experiment ID mismatch")
    evidence["experiment_id"] = ID
    data["input"][0]["content"][0]["text"] = json.dumps(evidence, ensure_ascii=False)
    data["model"] = cfg["model"]
    result = old.encoded(data)
    if len(result) > old.MAX_INPUT_BYTES:
        raise ValueError("Replay model payload exceeds original input cap")
    return result


def approval_template(root: Path, *, verified: dict | None = None) -> dict:
    cfg = old.model_config()
    if not cfg["custom"] or cfg["model"] != APPROVED_MODEL or cfg["api_key_env"] != "LLM_API_KEY":
        raise ValueError("P2B-002 requires exact approved LiteLLM Responses model alias")
    proof = verified or verified_replay(root.resolve())
    request_bytes = replay_request(proof["previous_request"], cfg)
    return {
        "experiment_id": ID,
        "approved": False,
        "approval_reference": "REPLACE_WITH_NEW_P2B_002_OWNER_APPROVAL",
        "approved_at_utc": "REPLACE_WITH_CURRENT_UTC_TIME",
        "model_provider": "openai_compatible_gateway",
        "model_id": APPROVED_MODEL,
        "endpoint": cfg["endpoint"],
        "model_api_key_env": "LLM_API_KEY",
        "model_user_agent": cfg["user_agent"],
        "model_code_sha256": old.sha(Path(__file__).read_bytes()),
        "instructions_sha256": old.sha(old.INSTRUCTIONS.encode()),
        "replay_request_sha256": old.sha(request_bytes),
        "replay_evidence": proof["fingerprint"],
        "max_source_requests": 0, "max_model_calls": 1, "max_spend_usd": MAX_SPEND_USD,
        "max_input_bytes": old.MAX_INPUT_BYTES,
        "max_output_tokens": old.MAX_OUTPUT_TOKENS,
        "input_price_usd_per_m": 2.0, "output_price_usd_per_m": 10.0,
        "pricing_reference": "REPLACE_WITH_OPERATOR_VERIFIED_GATEWAY_BILLING_REFERENCE",
        "pricing_verified_at_utc": "REPLACE_WITH_CURRENT_UTC_TIME",
        "trading_allowed": False, "account_simulation_allowed": False,
        "ticket_generation_allowed": False, "sealed_holdout_access_allowed": False,
        "arbitrary_generated_code_execution_allowed": False,
    }


def check_approval(path: Path, expected: dict, now: datetime) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 30_000:
        raise ValueError("Independent P2B-002 owner approval file missing")
    actual = json.loads(path.read_bytes())
    if type(actual) is not dict or set(actual) != set(expected):
        raise ValueError("P2B-002 approval shape mismatch")
    mutable = {"approved", "approval_reference", "approved_at_utc", "pricing_verified_at_utc",
               "pricing_reference"}
    for k, v in expected.items():
        if k not in mutable and (type(actual[k]) is not type(v) or actual[k] != v):
            raise ValueError("P2B-002 approved code, evidence, provider or budget changed: " + k)
    if (actual["approved"] is not True or not isinstance(actual["approval_reference"], str)
            or len(actual["approval_reference"]) < 16
            or "REPLACE_WITH" in actual["approval_reference"]):
        raise ValueError("Separate owner signature required for P2B-002")
    reference = actual["pricing_reference"]
    if (not isinstance(reference, str) or len(reference) < 20 or len(reference) > 500
            or "REPLACE_WITH" in reference):
        raise ValueError("Missing locally reviewed gateway billing basis")
    for field in ("approved_at_utc", "pricing_verified_at_utc"):
        try:
            t = datetime.fromisoformat(actual[field].replace("Z", "+00:00"))
        except (AttributeError, ValueError, TypeError) as exc:
            raise ValueError("Approval timestamp malformed") from exc
        if t.utcoffset() != timedelta(0) or not timedelta(0) <= now - t <= timedelta(hours=24):
            raise ValueError("P2B-002 approval / pricing verification older than 24 hours")
    return actual


def run(root: Path, *, now: datetime | None = None, invoke_model=None) -> dict:
    root = root.resolve()
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() != timedelta(0):
        raise ValueError("UTC clock required")
    if (root / "PAUSED").exists():
        return {"status": "PAUSED", "model_calls": 0, "network_requests": 0}
    verified = verified_replay(root)
    cfg = old.model_config()
    expected = approval_template(root, verified=verified)
    folder = root / "p2b" / ID
    approved = check_approval(folder / "owner-approval.json", expected, now)
    if not os.getenv("LLM_API_KEY") and invoke_model is None:
        raise ValueError("LLM_API_KEY not provided; no model request made")
    request_raw = replay_request(verified["previous_request"], cfg)
    if old.sha(request_raw) != approved["replay_request_sha256"]:
        raise ValueError("Owner-approved model request SHA changed")
    estimated = (12000 * approved["input_price_usd_per_m"] * 1.25 +
                 old.MAX_OUTPUT_TOKENS * approved["output_price_usd_per_m"]) / 1_000_000
    if estimated > approved["max_spend_usd"]:
        raise ValueError("Approved one-call billing ceiling violated")
    if folder.is_symlink():
        raise ValueError("P2B-002 output folder symlink forbidden")

    # Create the unrepeatable claim before any external request, including error paths.
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "attempt.claim").open("x", encoding="utf-8") as handle:
        handle.write(json.dumps({"claimed_at": now.isoformat(),
                                 "approved_sha256": old.sha(old.encoded(approved)),
                                 "previous_result_sha256": PREVIOUS_RESULT_HASH}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    counts = {"network_requests": 0, "model_calls": 0, "experiments_executed": 0}
    try:
        adapter = folder / "p2a-adapter"
        old._write_once(adapter / verified["report_path"], verified["report_bytes"])
        for rel, raw in verified["provider_bytes"]:
            old._write_once(adapter / rel, raw)
        old._write_once(folder / "replay-evidence-fingerprint.json",
                        old.encoded(verified["fingerprint"]))
        old._write_once(folder / "model-request.json", request_raw)
        counts["model_calls"] = 1
        old._record_network(folder / "outbound-claims.jsonl", "MODEL",
                            cfg["endpoint"], old.MAX_OUTPUT_TOKENS)
        try:
            response_raw = (invoke_model(request_raw) if invoke_model is not None
                            else old._model_get(request_raw, cfg))
        except HTTPError as exc:
            # Preserve gateway error body LOCALLY; do not disclose it or retry.
            err = exc.read(4097)
            path = folder / "gateway-http-error.raw"
            old._write_once(path, err[:4096])
            path.chmod(0o600)
            raise ValueError(f"Gateway returned HTTP {exc.code}; archived error body locally") from exc
        if not isinstance(response_raw, bytes) or len(response_raw) > 1_000_000:
            raise ValueError("Response too large or invalid")
        old._write_once(folder / "model-response.json", response_raw)
        decision, usage = old.parse_response(response_raw, cfg)
        old._write_once(folder / "model-decision.json", old.encoded(decision))
        old._write_once(folder / "model-usage.json", old.encoded(usage))
        if decision["decision"] == "ABSTAIN":
            if (decision["proposal"] is not None
                    or decision["reason_code"] not in
                    ("NO_NEW_FEASIBLE_MECHANISM", "INSUFFICIENT_SOURCE_EVIDENCE",
                     "NO_PLAUSIBLE_POINT_IN_TIME_DATA")
                    or not isinstance(decision["reason"], str)
                    or len(decision["reason"]) < 12):
                raise ValueError("Invalid model abstention")
            status = "NO_NEW_FEASIBLE_MECHANISM"
        elif decision["decision"] == "PROPOSE":
            proposal = decision["proposal"]
            if (not isinstance(proposal, dict) or decision["reason"] is not None
                    or decision["reason_code"] is not None
                    or proposal.get("doi") not in verified["fingerprint"]["verified_dois"]):
                raise ValueError("Unverified or invalid proposed DOI")
            proposal_path = "agent/proposal.json"
            old._write_once(adapter / proposal_path, old.encoded(proposal))
            review = gate.review(adapter, verified["report_path"], proposal_path)
            old._write_once(folder / "p2a-result.json", old.encoded(review))
            status = ("AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW"
                      if review["status"] in
                      ("NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW", "NEEDS_HUMAN_SOURCE_SCOPE_REVIEW")
                      else "NO_NEW_FEASIBLE_MECHANISM")
        else:
            raise ValueError("Unexpected model decision")
        result = {"status": status, "id": ID, "model": cfg["model"],
                  "evidence_reused": True,
                  "verified_dois": verified["fingerprint"]["verified_dois"],
                  **counts}
    except Exception as exc:
        result = {"status": "STOP_MODEL_OR_PROVENANCE_ERROR", "id": ID,
                  "reason_type": type(exc).__name__, "reason": str(exc)[:200],
                  **counts}
    raw = old.encoded(result)
    target = folder / ("result-" + old.sha(raw)[:12] + ".json")
    old._write_once(target, raw)
    return {**result, "report_path": str(target), "report_sha256": old.sha(raw)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quant-p2b-replay",
                                 description="P2B-002 replay frozen P2B-001 evidence, one model call")
    ap.add_argument("--home", type=Path, default=Path("runtime"))
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("approval-template", help="Offline, validated, unapproved JSON template")
    sub.add_parser("run", help="One externally authorized model request; never repeat")
    args = ap.parse_args(argv)
    try:
        root = args.home.resolve()
        result = approval_template(root) if args.command == "approval-template" else run(root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == "approval-template":
            return 0
        return 0 if result["status"] in ("NO_NEW_FEASIBLE_MECHANISM",
                                         "AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW", "PAUSED") else 1
    except (ValueError, OSError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "STOP_P2B_002_PRECHECK",
                          "reason": str(exc)[:200], "model_calls": 0,
                          "network_requests": 0}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
