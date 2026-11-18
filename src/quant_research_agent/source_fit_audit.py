"""Offline, read-only reclassification of immutable P1 Crossref metadata.

Does not alter legacy papers, study status, frozen report or the P1 scheduler.
The only new filesystem output is a content-addressed audit report.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3

from .autonomous_loop import APPROVED_TEMPLATE, parse_papers, sha, write_immutable
from .source_fit import GATE_VERSION, assess_source


def verified_stored_paper(root: Path, db: sqlite3.Connection, doi: str) -> dict:
    """Verify archived Crossref bytes, original DOI/title and poll provenance.

    Called before executing a *previously waiting* study. No network calls,
    SQLite writes or strategy evaluation are performed here.
    """
    stored = db.execute(
        "SELECT doi,title,publication_year,url,response_sha FROM papers WHERE doi=?",
        (doi,)).fetchone()
    if stored is None:
        raise ValueError("Archived study references an unknown DOI")
    poll = db.execute(
        "SELECT id,at FROM polls WHERE status='COMPLETED' AND response_sha=? ORDER BY id LIMIT 1",
        (stored["response_sha"],)).fetchone()
    if poll is None:
        raise ValueError("Archived DOI has no completed source poll")
    root = root.resolve()
    source_path = root / "agent/evidence" / f"crossref-poll-{poll['id']}.json"
    if not source_path.resolve().is_relative_to(root) or not source_path.is_file():
        raise ValueError("Archived DOI source response missing or outside runtime")
    if source_path.stat().st_size > 1_000_000:
        raise ValueError("Archived DOI source response too large")
    raw = source_path.read_bytes()
    if sha(raw) != stored["response_sha"]:
        raise ValueError("Archived DOI source SHA256 mismatch")
    found = parse_papers(raw, 20, datetime.fromisoformat(poll["at"]))
    matching = [paper for paper in found if paper["doi"] == doi]
    if len(matching) != 1:
        raise ValueError("Archived DOI absent from its source response")
    paper = matching[0]
    if (paper["title"] != stored["title"] or
            paper["publication_year"] != stored["publication_year"] or
            paper["url"] != stored["url"]):
        raise ValueError("Archived DOI metadata drifted from source response")
    return paper


def audit_existing(root: Path) -> dict:
    root = root.resolve()
    database = root / "agent/autonomous_loop.sqlite3"
    if not database.is_file():
        raise ValueError("No existing P1 research database; audit cannot create research")
    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        papers = [dict(r) for r in db.execute(
            "SELECT doi,title,publication_year,url,at,response_sha,decision "
            "FROM papers ORDER BY doi")]
        polls = [dict(r) for r in db.execute(
            "SELECT id,at,status,response_sha FROM polls "
            "WHERE status='COMPLETED' ORDER BY id")]
        studies = [dict(r) for r in db.execute(
            "SELECT template_id,doi,status,report_sha FROM studies ORDER BY template_id")]
    finally:
        db.close()
    if not polls and papers:
        raise ValueError("Papers exist without completed evidence polls")

    # Verify original bytes, their stored SHA and the exact database title/year
    # before evaluating relevance; a SQL row alone is not evidence.
    originals: dict[tuple[str, str], dict] = {}
    poll_hashes = []
    for poll in polls:
        source_path = root / "agent/evidence" / f"crossref-poll-{poll['id']}.json"
        if not source_path.resolve().is_relative_to(root) or not source_path.is_file():
            raise ValueError("Missing/out-of-root archived Crossref response")
        raw = source_path.read_bytes()
        actual_sha = sha(raw)
        if actual_sha != poll["response_sha"]:
            raise ValueError("Archived Crossref response SHA256 mismatch")
        found = parse_papers(raw, 20, datetime.fromisoformat(poll["at"]))
        for paper in found:
            originals[(paper["doi"], actual_sha)] = paper
        poll_hashes.append({"poll_id": poll["id"], "response_sha256": actual_sha})

    decisions: dict[str, int] = {}
    entries = []
    selected = {s["doi"]: s for s in studies if s["template_id"] == APPROVED_TEMPLATE}
    for paper in papers:
        metadata = originals.get((paper["doi"], paper["response_sha"]))
        if not metadata:
            raise ValueError(f"Missing source DOI for archived row {paper['doi']}")
        if (metadata["title"] != paper["title"] or
                metadata["publication_year"] != paper["publication_year"] or
                metadata["url"] != paper["url"]):
            raise ValueError(f"Stored DOI metadata does not match original source: {paper['doi']}")
        assessment = assess_source(metadata["title"], metadata.get("abstract"))
        decisions[assessment["decision"]] = decisions.get(assessment["decision"], 0) + 1
        entries.append({
            "doi": paper["doi"], "title": paper["title"],
            "publication_year": paper["publication_year"],
            "source_sha256": paper["response_sha"],
            "legacy_title_only_decision": paper["decision"],
            "source_fit": assessment,
            "previous_frozen_study": selected.get(paper["doi"]),
        })

    report = {
        "gate_version": GATE_VERSION,
        "purpose": "Offline source-to-frozen-experiment match only; not paper finding verification",
        "original_evidence_polls": poll_hashes,
        "papers": entries,
        "decision_counts": dict(sorted(decisions.items())),
        "legacy_studies": studies,
        "prior_reports_modified": False,
        "new_experiments_executed": False,
        "network_requests": 0,
    }
    raw_report = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    audit_sha = sha(raw_report)
    output = root / "agent/reports" / f"source-fit-audit-v1-{audit_sha[:12]}.json"
    write_immutable(output, raw_report)
    previously_used = [e for e in entries if e["previous_frozen_study"]]
    return {
        "status": "SOURCE_FIT_AUDIT_COMPLETED",
        "paper_count": len(entries),
        "decision_counts": dict(sorted(decisions.items())),
        "previous_study_source_fit": [{"doi": e["doi"],
                                      "decision": e["source_fit"]["decision"],
                                      "reason_code": e["source_fit"]["reason_code"]}
                                     for e in previously_used],
        "audit_path": str(output),
        "audit_sha256": audit_sha,
        "network_requests": 0,
        "experiments_rerun": False,
    }
