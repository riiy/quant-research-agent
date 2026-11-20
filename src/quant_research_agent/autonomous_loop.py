"""Autonomous evidence -> prescreen -> single frozen mechanism Kill Test -> archive.

P1 bounded research-only spike. External Crossref *metadata* alone, one explicitly
preapproved calendar mechanism test, no LLM generated code, trades, or holdouts.
Does not change/replace the already deployed P0 controller or its database.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib import parse, request

from . import weekday_mechanism as weekday
from . import source_fit

SOURCE = "https://api.crossref.org/works"
HOST = "api.crossref.org"
APPROVED_QUERY = "bitcoin cryptocurrency calendar day of week weekend returns"
APPROVED_TEMPLATE = weekday.RESEARCH_ID
MAX_SOURCE_BYTES = 1_000_000
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s<>]{1,160}$", re.I)
FLAGS = ("trading_allowed", "account_simulation_allowed", "ticket_generation_allowed",
         "holdout_access_allowed", "model_calls_allowed", "arbitrary_code_allowed",
         "strategy_backtest_allowed")
SQL = """
CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS polls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
 status TEXT NOT NULL, response_sha TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS papers (
 doi TEXT PRIMARY KEY, title TEXT NOT NULL, publication_year INTEGER NOT NULL,
 url TEXT NOT NULL, at TEXT NOT NULL, response_sha TEXT NOT NULL,
 decision TEXT NOT NULL, research_template TEXT);
CREATE TABLE IF NOT EXISTS studies (
 template_id TEXT PRIMARY KEY, doi TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, completed_at TEXT, report_path TEXT, report_sha TEXT);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
 kind TEXT NOT NULL, details TEXT NOT NULL);
"""


def jdump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_policy(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > 10000:
        raise ValueError("Research loop policy too large")
    p = json.loads(raw)
    required = {"schema_version", "research_only", "source", "search_query", "max_results",
                "poll_interval_hours", "max_requests_per_utc_day", "template", "spot_path", *FLAGS}
    if type(p) is not dict or set(p) != required:
        raise ValueError("Research loop policy requires exact frozen schema")
    if (type(p["schema_version"]) is not int or p["schema_version"] != 1 or p["research_only"] is not True
            or any(p[k] is not False for k in FLAGS)):
        raise ValueError("All research-only safety flags must remain false")
    expected = {"source": "crossref", "search_query": APPROVED_QUERY,
                "template": APPROVED_TEMPLATE, "spot_path": "data/BTCUSDT-1d.csv"}
    if any(p[k] != v for k, v in expected.items()):
        raise ValueError("External host, query, template and spot path are frozen in P1")
    for field, low, high in (("max_results", 5, 20), ("poll_interval_hours", 24, 168),
                             ("max_requests_per_utc_day", 1, 1)):
        if type(p[field]) is not int or not low <= p[field] <= high:
            raise ValueError(f"Invalid research loop bound: {field}")
    return p


def connect(root: Path) -> sqlite3.Connection:
    dir = root / "agent"
    dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(dir / "autonomous_loop.sqlite3", timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript(SQL)
    db.commit()
    return db


def log(db: sqlite3.Connection, when: datetime, kind: str, detail: dict) -> None:
    db.execute("INSERT INTO events(at,kind,details) VALUES(?,?,?)", (when.isoformat(), kind, jdump(detail)))


def policy_guard(db: sqlite3.Connection, p: dict) -> None:
    digest = sha(jdump(p).encode())
    row = db.execute("SELECT value FROM settings WHERE name='approved_policy_digest'").fetchone()
    if row is not None and row["value"] != digest:
        raise ValueError("POLICY_DRIFT_BLOCKED: v1 requires a separate reviewed deployment")
    if row is None:
        db.execute("INSERT INTO settings(name,value) VALUES('approved_policy_digest',?)", (digest,))


def fetch_crossref(p: dict) -> bytes:
    """Exactly one HTTPS request to Crossref; no arbitrary URLs or redirects."""
    query = parse.urlencode({"query.bibliographic": p["search_query"],
                             "rows": str(p["max_results"]),
                             "filter": "type:journal-article",
                             "select": "DOI,title,published,URL,type,created,indexed,abstract"})
    url = SOURCE + "?" + query
    req = request.Request(url, headers={"User-Agent": "quant-research-agent-p1/0.1 (+research-only; no bulk harvesting)",
                                        "Accept": "application/json"})
    # Disallow cross-domain redirects, including redirects to internal network.
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("Crossref redirect forbidden")
    opener = request.build_opener(NoRedirect)
    with opener.open(req, timeout=15) as resp:
        final = parse.urlparse(resp.geturl())
        if final.scheme != "https" or final.hostname != HOST:
            raise ValueError("Unexpected source origin")
        if resp.status != 200:
            raise ValueError("Crossref HTTP status not OK")
        raw = resp.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("Crossref response oversized")
        return raw


def parse_papers(raw: bytes, max_results: int, now: datetime) -> list[dict]:
    result = json.loads(raw)
    if (type(result) is not dict or result.get("status") != "ok" or
            type(result.get("message")) is not dict or type(result["message"].get("items")) is not list):
        raise ValueError("Unexpected Crossref response schema")
    items = result["message"]["items"]
    if len(items) > max_results:
        raise ValueError("Source delivered more items than requested")
    cleaned = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "journal-article":
            continue
        doi = item.get("DOI")
        title = item.get("title")
        published = item.get("published")
        if (not isinstance(doi, str) or not DOI_PATTERN.fullmatch(doi.strip())
                or not isinstance(title, list) or len(title) != 1 or not isinstance(title[0], str)
                or not isinstance(published, dict)):
            continue
        title = " ".join(title[0].split())
        if not 8 <= len(title) <= 350:
            continue
        date_parts = published.get("date-parts")
        if (not isinstance(date_parts, list) or len(date_parts) != 1 or not isinstance(date_parts[0], list)
                or not date_parts[0] or type(date_parts[0][0]) is not int):
            continue
        year = date_parts[0][0]
        if not 2018 <= year <= now.year:
            continue
        doi = doi.lower().strip()
        if doi in seen:
            continue
        seen.add(doi)
        cleaned.append({"doi": doi, "url": "https://doi.org/" + doi,
                        "title": title, "publication_year": year,
                        "abstract": item.get("abstract") if isinstance(item.get("abstract"), str) else None})
    return cleaned


def classify(title: str, abstract: str | None = None) -> str:
    """Conservative source-to-frozen-test fit, NOT an empirical paper validation."""
    return source_fit.assess_source(title, abstract)["decision"]


def archived_study(db: sqlite3.Connection) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM studies WHERE template_id=?", (APPROVED_TEMPLATE,)).fetchone()


def _report_bytes(study: dict, source_digest: str, result: dict, fit: dict) -> bytes:
    document = {"research_id": APPROVED_TEMPLATE, "evidence": study,
                "discovery_source": "Crossref title/abstract/DOI metadata, NOT verified causal results",
                "response_sha256": source_digest, "source_fit": fit, "falsification": result,
                "autonomous_discovery": True, "auto_generated_code": False,
                "holdout_evaluated": False, "trading_allowed": False,
                "account_simulation_allowed": False}
    return (json.dumps(document, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_immutable(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("ARCHIVE_CONFLICT: immutable output differs")
        return
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def execute_study(root: Path, db: sqlite3.Connection, now: datetime) -> dict:
    row = archived_study(db)
    if row is None:
        return {"status": "IDLE_NO_STUDY"}
    if row["status"] != "WAITING_DATA":
        return {"status": "IDLE_STUDY_ALREADY_RECORDED", "study_status": row["status"]}
    # A historical WAITING_DATA record may have been claimed by the old title-
    # only classifier. Recheck *verified original bytes* before accessing prices.
    # No legacy result is rewritten or given another shot at the hypothesis.
    from .source_fit_audit import verified_stored_paper
    try:
        verified = verified_stored_paper(root, db, row["doi"])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        with db:
            db.execute("UPDATE studies SET status='FAILED_REVIEW_REQUIRED' "
                       "WHERE template_id=? AND status='WAITING_DATA'", (APPROVED_TEMPLATE,))
            log(db, now, "SOURCE_VERIFICATION_FAILED", {"reason": type(exc).__name__})
        return {"status": "FAILED_REVIEW_REQUIRED", "reason": "ORIGINAL_SOURCE_NOT_VERIFIABLE"}
    source_assessment = source_fit.assess_source(verified["title"], verified.get("abstract"))
    if source_assessment["decision"] != source_fit.AUTO:
        with db:
            db.execute("UPDATE studies SET status='SOURCE_FIT_REVIEW_REQUIRED' "
                       "WHERE template_id=? AND status='WAITING_DATA'", (APPROVED_TEMPLATE,))
            log(db, now, "SOURCE_TO_TEST_GATE_BLOCKED",
                {"doi": row["doi"], "assessment": source_assessment})
        return {"status": "SOURCE_FIT_REVIEW_REQUIRED", "doi": row["doi"],
                "source_fit": source_assessment, "experiment_executed": False}
    spot = root / "data/BTCUSDT-1d.csv"
    if not spot.is_file():
        return {"status": "BLOCKED_MISSING_SPOT", "study_status": "WAITING_DATA",
                "required_path": "runtime/data/BTCUSDT-1d.csv"}
    # A crashed/failed study is *never* rerun without review, even if file remains.
    with db:
        cur = db.execute("UPDATE studies SET status='RUNNING' WHERE template_id=? AND status='WAITING_DATA'",
                         (APPROVED_TEMPLATE,))
        if cur.rowcount != 1:
            raise ValueError("Concurrent study claim denied")
        log(db, now, "STUDY_CLAIMED", {"template": APPROVED_TEMPLATE, "doi": row["doi"]})
    try:
        result = weekday.run(spot)
        paper = db.execute("SELECT doi,title,publication_year,url,at,response_sha FROM papers WHERE doi=?", (row["doi"],)).fetchone()
        if paper is None:
            raise ValueError("Source paper unavailable; refusing unverifiable research")
        raw = _report_bytes(dict(paper), paper["response_sha"], result, source_assessment)
        out = root / "agent/reports/BTC_WEEKDAY_INFORMATION_v1.json"
        write_immutable(out, raw)
        outcome = result["status"]
        with db:
            db.execute("UPDATE studies SET status=?,completed_at=?,report_path=?,report_sha=? WHERE template_id=? AND status='RUNNING'",
                       (outcome, now.isoformat(), "agent/reports/BTC_WEEKDAY_INFORMATION_v1.json", sha(raw), APPROVED_TEMPLATE))
            log(db, now, "RESEARCH_ARCHIVED", {"status": outcome, "sha256": sha(raw),
                                                "doi": row["doi"], "template": APPROVED_TEMPLATE})
        return {"status": outcome, "doi": row["doi"], "research_report": str(out),
                "report_sha256": sha(raw), "gate_results": result["gates"],
                "scope": "retrospective mechanism-only; no tradable strategy"}
    except Exception as exc:
        with db:
            db.execute("UPDATE studies SET status='FAILED_REVIEW_REQUIRED' WHERE template_id=? AND status='RUNNING'",
                       (APPROVED_TEMPLATE,))
            log(db, now, "STUDY_FAILED", {"error_type": type(exc).__name__,
                                          "reason": str(exc)[:180]})
        return {"status": "FAILED_REVIEW_REQUIRED", "reason": type(exc).__name__,
                "details": str(exc)[:180]}


def cycle(root: Path, policy_path: Path, *, now: datetime | None = None,
          fetcher=None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("UTC time required")
    root = root.resolve()
    p = load_policy(policy_path)
    if (root / "PAUSED").exists():
        return {"status": "PAUSED"}
    db = connect(root)
    try:
        with db:
            policy_guard(db, p)
        pending = archived_study(db)
        if pending and pending["status"] == "WAITING_DATA":
            return execute_study(root, db, now)
        if pending and pending["status"] == "RUNNING":
            with db:
                db.execute("UPDATE studies SET status='INTERRUPTED_REVIEW_REQUIRED' WHERE template_id=?", (APPROVED_TEMPLATE,))
                log(db, now, "INTERRUPTED_NO_RETRY", {"template": APPROVED_TEMPLATE})
            return {"status": "INTERRUPTED_REVIEW_REQUIRED"}
        if pending:
            # Only one frozen study can ever be run in P1. There is no purpose
            # in repeatedly polling the same query after its terminal decision.
            return {"status": "IDLE_TEMPLATE_SATURATED", "study_status": pending["status"],
                    "network_requests": 0, "experiment_executed": False}
        last = db.execute("SELECT at FROM polls ORDER BY id DESC LIMIT 1").fetchone()
        if last and now - datetime.fromisoformat(last["at"]) < timedelta(hours=p["poll_interval_hours"]):
            return {"status": "IDLE_POLL_INTERVAL", "next_eligible_at":
                    (datetime.fromisoformat(last["at"]) + timedelta(hours=p["poll_interval_hours"])).isoformat()}
        with db:
            # Claim network request BEFORE I/O, across concurrent controller processes.
            db.execute("BEGIN IMMEDIATE")
            recent = db.execute("SELECT at FROM polls ORDER BY id DESC LIMIT 1").fetchone()
            if recent and now - datetime.fromisoformat(recent["at"]) < timedelta(hours=p["poll_interval_hours"]):
                return {"status": "IDLE_POLL_INTERVAL"}
            count = db.execute("SELECT COUNT(*) FROM polls WHERE at LIKE ?", (now.date().isoformat() + "%",)).fetchone()[0]
            if count >= p["max_requests_per_utc_day"]:
                return {"status": "IDLE_DAILY_SOURCE_BUDGET"}
            cur = db.execute("INSERT INTO polls(at,status) VALUES(?,?)", (now.isoformat(), "STARTED"))
            poll_id = cur.lastrowid
        try:
            data = (fetcher or fetch_crossref)(p)
            if type(data) is not bytes or len(data) > MAX_SOURCE_BYTES:
                raise ValueError("Invalid source response bytes")
            papers = parse_papers(data, p["max_results"], now)
        except Exception as exc:
            with db:
                db.execute("UPDATE polls SET status='FAILED',error=? WHERE id=?", (type(exc).__name__, poll_id))
                log(db, now, "SOURCE_UNAVAILABLE", {"reason": type(exc).__name__, "details": str(exc)[:160]})
            return {"status": "STOP_SOURCE_UNAVAILABLE", "reason": type(exc).__name__}
        source_digest = sha(data)
        # Keep inspectable original source metadata bytes, not just a citation URL.
        # A second invocation cannot alter an already archived response.
        try:
            write_immutable(root / f"agent/evidence/crossref-poll-{poll_id}.json", data)
        except Exception as exc:
            with db:
                db.execute("UPDATE polls SET status='FAILED',error=? WHERE id=?",
                           (type(exc).__name__, poll_id))
                log(db, now, "SOURCE_ARCHIVE_FAILURE", {"reason": str(exc)[:160]})
            return {"status": "FAILED_REVIEW_REQUIRED", "reason": "SOURCE_ARCHIVE_FAILURE"}
        new_count, eligible_count = 0, 0
        with db:
            db.execute("UPDATE polls SET status='COMPLETED',response_sha=? WHERE id=?", (source_digest, poll_id))
            for paper in papers:
                c = classify(paper["title"], paper.get("abstract"))
                cur = db.execute("INSERT OR IGNORE INTO papers(doi,title,publication_year,url,at,response_sha,decision,research_template) VALUES(?,?,?,?,?,?,?,?)",
                                 (paper["doi"],paper["title"],paper["publication_year"],paper["url"],now.isoformat(),
                                  source_digest,c,APPROVED_TEMPLATE if c == source_fit.AUTO else None))
                new_count += cur.rowcount
                eligible_count += cur.rowcount if c == source_fit.AUTO else 0
            log(db, now, "EXTERNAL_EVIDENCE_SCREENED", {"received": len(papers), "new": new_count,
                                                        "eligible_title_cues": eligible_count,
                                                        "response_sha256": source_digest})
            if archived_study(db) is None:
                # Crossref sends results in relevance order. Use the first eligible
                # title cue; no search through study outcomes or alternative days.
                first = next((paper["doi"] for paper in papers
                              if classify(paper["title"], paper.get("abstract")) == source_fit.AUTO), None)
                if first:
                    db.execute("INSERT INTO studies(template_id,doi,status,created_at) VALUES(?,?,?,?)",
                               (APPROVED_TEMPLATE,first,"WAITING_DATA",now.isoformat()))
                    log(db, now, "FROZEN_TEMPLATE_REGISTERED", {"template": APPROVED_TEMPLATE, "doi": first})
        if archived_study(db) and archived_study(db)["status"] == "WAITING_DATA":
            return execute_study(root, db, now)
        return {"status": "EVIDENCE_ARCHIVED_NO_NEW_EXECUTABLE_STUDY" if new_count else "NO_NEW_EVIDENCE",
                "new_papers": new_count, "eligible_title_cues": eligible_count,
                "source_response_sha256": source_digest,
                "note": "Nonmatching/unsupported evidence is archived for human review"}
    finally:
        db.close()


def status(root: Path) -> dict:
    db = connect(root.resolve())
    try:
        last = db.execute("SELECT at,status,response_sha,error FROM polls ORDER BY id DESC LIMIT 1").fetchone()
        studies = [dict(x) for x in db.execute("SELECT * FROM studies ORDER BY created_at")]
        counts = [dict(x) for x in db.execute("SELECT decision,COUNT(*) AS count FROM papers GROUP BY decision")]
        return {"paused": (root / "PAUSED").exists(), "last_poll": dict(last) if last else None,
                "studies": studies, "paper_counts": counts, "network_only": "Crossref REST API",
                "autonomous_new_code": False, "trading_allowed": False}
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-research-loop", description="bounded research-only evidence-to-falsification cycle")
    parser.add_argument("--home", type=Path, default=Path(os.getenv("QUANT_HOME", "runtime")))
    cmds = parser.add_subparsers(dest="command", required=True)
    c = cmds.add_parser("cycle", help="At most one bounded Crossref metadata query and one frozen study")
    c.add_argument("--policy", type=Path, required=True)
    cmds.add_parser("status", help="Inspect durable evidence and study outcomes")
    cmds.add_parser("relevance-audit", help="Offline source fit audit of existing Crossref records; no studies or HTTP")
    p = cmds.add_parser("evidence-plan", help="Offline DOI-verified plan for <=5 abstracts; no network")
    p.add_argument("--max-papers", type=int, default=5)
    e = cmds.add_parser("evidence-enrich", help="Opt-in <=5 Crossref/OpenAlex DOI abstracts; never backtests")
    e.add_argument("--max-papers", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        if args.command == "cycle":
            output = cycle(args.home, args.policy)
        elif args.command == "relevance-audit":
            from .source_fit_audit import audit_existing
            output = audit_existing(args.home)
        elif args.command in ("evidence-plan", "evidence-enrich"):
            from .abstract_evidence import plan, enrich
            output = plan(args.home, args.max_papers) if args.command == "evidence-plan" else enrich(args.home, args.max_papers)
        else:
            output = status(args.home)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
        if args.command in ("status", "relevance-audit", "evidence-plan", "evidence-enrich"):
            return 0
        return 1 if output["status"].startswith(("FAILED_", "STOP_", "INTERRUPTED_")) else 0
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        print(json.dumps({"status":"STOP_RESEARCH_LOOP_ERROR", "reason":str(exc)[:240]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
