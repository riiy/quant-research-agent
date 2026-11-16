"""Constrained and budgeted idea funnel; does NOT execute a strategy or consult holdout."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from urllib import error, request

from .evidence import AVAILABLE_DATA, MECHANISMS, SOURCES, mechanism_screen, next_feasible_mechanism


class Idea:
    FIELDS = {"title", "mechanism_id", "economic_mechanism", "signal_proposal", "falsifier", "source_ids"}

    def __init__(self, payload: dict, *, selected_mechanism: str):
        if not isinstance(payload, dict):
            raise ValueError("Idea must be a JSON object")
        missing, extra = self.FIELDS - payload.keys(), payload.keys() - self.FIELDS
        if missing or extra:
            raise ValueError(f"Idea schema mismatch: missing={sorted(missing)}, unexpected={sorted(extra)}")
        if payload["mechanism_id"] != selected_mechanism:
            raise ValueError("Model changed the preselected research mechanism")
        for name in ("title", "economic_mechanism", "signal_proposal", "falsifier"):
            value = payload[name]
            if not isinstance(value, str) or not 25 <= len(value.strip()) <= 900:
                raise ValueError(f"Idea {name} must be a substantive 25..900-character string")
        ids = payload["source_ids"]
        allowed = set(MECHANISMS[selected_mechanism]["sources"])
        if not isinstance(ids, list) or not ids or len(ids) > 3 or len(ids) != len(set(ids)) or any(type(i) is not str or i not in allowed for i in ids):
            raise ValueError("Idea citations must use relevant, verified source IDs only")
        self.value = dict(payload)


class IdeaStore:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.path = root / "ideas.sqlite3"
        with sqlite3.connect(self.path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ideas (
                idea_id TEXT PRIMARY KEY, mechanism_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, status TEXT NOT NULL,
                idea_json TEXT NOT NULL, screening_json TEXT NOT NULL,
                discovery_json TEXT NOT NULL)""")

    def seen(self) -> set[str]:
        with sqlite3.connect(self.path) as conn:
            return {row[0] for row in conn.execute("SELECT mechanism_id FROM ideas")}

    def list(self) -> list[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT * FROM ideas ORDER BY created_at DESC")]

    def save(self, idea: Idea, screen: dict, discovery: dict) -> str:
        identifier = uuid.uuid4().hex[:12]
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO ideas (idea_id,mechanism_id,created_at,status,idea_json,screening_json,discovery_json) VALUES (?,?,?,?,?,?,?)",
                (identifier, idea.value["mechanism_id"], datetime.now(timezone.utc).isoformat(),
                 "AWAITING_RULE_DESIGN_NOT_BACKTESTED", json.dumps(idea.value, ensure_ascii=False),
                 json.dumps(screen, ensure_ascii=False), json.dumps(discovery, ensure_ascii=False)))
        return identifier


def api_idea(mechanism_id: str) -> tuple[Idea, dict]:
    # Use the legacy .env loader for the same operator workflow as quant-agent.
    from .discovery import load_env_file
    load_env_file(".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for paid independent API; ChatGPT Plus does not include API calls")
    model = os.getenv("QUANT_MODEL", "gpt-6-luna")
    notes = {sid: SOURCES[sid] for sid in MECHANISMS[mechanism_id]["sources"]}
    schema = {"type": "object", "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "mechanism_id": {"type": "string", "enum": [mechanism_id]},
            "economic_mechanism": {"type": "string"},
            "signal_proposal": {"type": "string"},
            "falsifier": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string", "enum": list(notes)}},
        },
        "required": ["title", "mechanism_id", "economic_mechanism", "signal_proposal", "falsifier", "source_ids"]}
    details = MECHANISMS[mechanism_id]
    prompt = (
        "You are screening a RESEARCH IDEA, not searching parameters or writing a trade strategy. "
        "Give ONE skeptical, falsifiable BTCUSDT SPOT DAILY long/cash idea grounded only in supplied sources. "
        "No unverified BTC alpha claims or fabricated citations. Report evidence-transfer risk. "
        "Only daily_ohlcv (UTC open/high/low/close/volume) is available; no Google Trends, order book, or on-chain data. "
        "Do NOT suggest SMA, momentum lookback, channel breakout or relabel trend persistence. "
        "Signal proposal should be testable from lagged daily OHLCV; do not optimize any parameters. "
        "Include a measurable predeclared failure criterion with fees and a risk/exposure-aware comparison. "
        "This is a hypothesis note and MUST NOT be treated as an executable backtest instruction. "
        f"Mechanism: {mechanism_id}. Question: {details['question']}. "
        f"Evidence scope: {details['evidence_scope']}. Comparator: {details['baseline']}. "
        f"Kill test: {details['failure_rule']}. Source notes: {json.dumps(notes, ensure_ascii=False)}"
    )
    user_text = (
        "Return ONLY an unwrapped JSON object with EXACTLY title, mechanism_id, economic_mechanism, "
        "signal_proposal, falsifier, source_ids. All descriptive fields must be meaningful sentences, "
        "25..900 characters each. source_ids must cite the supplied note IDs. "
        "For signal_proposal, specify observable lagged daily OHLCV and when a signal is known. "
        "For falsifier, spell out costs, comparison, and what evidence would reject the idea. " + prompt
    )
    payload = {"model": model, "instructions": prompt,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
        "max_output_tokens": 1100,
        "text": {"format": {"type": "json_schema", "name": "research_idea", "strict": True, "schema": schema}}}
    endpoint = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")
    req = request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST",
                          headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)
    except error.HTTPError as exc:
        raise RuntimeError(f"Model provider HTTP {exc.code}; inspect gateway/structured-output configuration") from None
    if result.get("status") not in (None, "completed"):
        raise RuntimeError(f"Model response status is not completed: {result.get('status')}")
    chunks = [c.get("text", "") for item in result.get("output", [])
              for c in item.get("content", []) if c.get("type") == "output_text"]
    if not chunks:
        raise RuntimeError("No idea JSON returned by provider")
    parsed = json.loads("".join(chunks))
    if isinstance(parsed, dict) and set(parsed) == {"idea"}:
        parsed = parsed["idea"]
    return Idea(parsed, selected_mechanism=mechanism_id), {
        "mode": "api", "model": model, "response_id": result.get("id"),
        "usage": result.get("usage", {}), "source_registry": "curated-v2"}


def seed_idea(mechanism_id: str) -> Idea:
    return Idea({
        "title": "Volatility-regime BTC spot exposure research idea (offline example)",
        "mechanism_id": mechanism_id,
        "economic_mechanism": "Volatility persistence may make risk exposure vary over time, but evidence comes from non-crypto factors and BTC transfer is unproven.",
        "signal_proposal": "Use only trailing daily close-to-close volatility known after the preceding UTC daily close; compare rule design alternatives only before locking a test.",
        "falsifier": "Reject if risk-adjusted or exposure-matched performance fails to improve over the BTC comparator after fees, with no holdout reuse.",
        "source_ids": ["moreira_muir2017"],
    }, selected_mechanism=mechanism_id)


def markdown_report(path: Path, record_id: str, idea: Idea, screen: dict, discovery: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    m = MECHANISMS[idea.value["mechanism_id"]]
    lines = [f"# Idea {record_id}: {idea.value['title']}", "",
        "- Status: **AWAITING_RULE_DESIGN_NOT_BACKTESTED**", "- Trading permission: **NONE**",
        f"- Mechanism: `{idea.value['mechanism_id']}`", f"- Evidence scope: `{m['evidence_scope']}`",
        f"- Discoverer: {discovery['mode']}", "",
        "## Mechanism", "", idea.value["economic_mechanism"], "",
        "## Proposed signal (not executable)", "", idea.value["signal_proposal"], "",
        "## Explicit falsifier", "", idea.value["falsifier"], "",
        "## Fixed evidence and transfer limitations", ""]
    for sid in idea.value["source_ids"]:
        x = SOURCES[sid]
        lines.extend([f"- [{x['title']}]({x['url']}): {x['finding']} ({x['universe']})"])
    lines += ["", "## Deterministic screening", "",
        f"- Score (triage only, not alpha probability): {screen['score']['total']} / 6",
        f"- Baseline: {screen['baseline']}", f"- Kill test: {screen['kill_test']}",
        f"- Execution: **{screen['execution_status']}**", "",
        "**No historical backtest, strategy optimization, 2025 holdout, or trading authorization.**", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def discover(root: Path, mode: str = "api") -> dict:
    store = IdeaStore(root)
    if (root / "PAUSED").exists():
        raise RuntimeError("Research is paused")
    mechanism_id = next_feasible_mechanism(store.seen())
    if mechanism_id is None:
        return {"status": "NO_NEW_FEASIBLE_MECHANISMS", "api_calls": 0,
                "reason": "All available mechanisms are already screened or require unavailable data; stop, do not reword trend parameters"}
    screen = mechanism_screen(mechanism_id, store.seen())
    if mode == "seed":
        # Demonstration does not consume uniqueness or create research archives.
        return {"status": "DEMO_NOT_ARCHIVED", "idea": seed_idea(mechanism_id).value, "screening": screen, "api_calls": 0}
    if mode != "api":
        raise ValueError("Mode must be api or seed")
    from .storage import Store
    # Quota is shared with the legacy research API to avoid hidden second budgets.
    # Read .env before taking the reservation; no automatic paid retries.
    from .discovery import load_env_file
    load_env_file(".env")
    max_calls = int(os.getenv("QUANT_MAX_API_CALLS_MONTH", "20"))
    if not 1 <= max_calls <= 1000:
        raise ValueError("QUANT_MAX_API_CALLS_MONTH must be 1..1000")
    old_store = Store(root)
    attempt = old_store.reserve_api_call(os.getenv("QUANT_MODEL", "gpt-6-luna"), max_calls)
    idea, meta = api_idea(mechanism_id)
    old_store.record_usage(attempt, meta.get("usage", {}))
    current = store.seen()
    if mechanism_id in current:
        return {"status": "DUPLICATE_MECHANISM_RACE_REJECTED", "api_calls": 1}
    screen = mechanism_screen(mechanism_id, current)
    if screen["status"] != "ELIGIBLE_FOR_IDEA_ONLY":
        return {"status": "SCREEN_REJECTED", "screening": screen, "api_calls": 1}
    try:
        identifier = store.save(idea, screen, meta)
    except sqlite3.IntegrityError:
        return {"status": "DUPLICATE_MECHANISM_RACE_REJECTED", "api_calls": 1}
    path = root / "ideas" / (identifier + ".md")
    markdown_report(path, identifier, idea, screen, meta)
    return {"status": "AWAITING_RULE_DESIGN_NOT_BACKTESTED", "id": identifier,
            "mechanism_id": mechanism_id, "screening": screen, "report": str(path), "api_calls": 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-ideas", description="Evidence-first, no-backtest idea screening")
    parser.add_argument("--home", type=Path, default=Path(os.getenv("QUANT_HOME", "runtime")))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sources", help="Show curated, scope-tagged research sources")
    commands.add_parser("preview", help="Offline feasibility/novelty review; no API call")
    discover_cmd = commands.add_parser("discover", help="Generate one new, non-trend idea, then archive its screening")
    discover_cmd.add_argument("--mode", choices=("api", "seed"), default="api")
    commands.add_parser("list", help="List screened idea metadata and records")
    args = parser.parse_args(argv)
    try:
        if args.command == "sources":
            output = SOURCES
        elif args.command == "preview":
            seen = IdeaStore(args.home).seen()
            output = {key: mechanism_screen(key, seen) for key in MECHANISMS}
        elif args.command == "list":
            output = IdeaStore(args.home).list()
        else:
            output = discover(args.home, args.mode)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
