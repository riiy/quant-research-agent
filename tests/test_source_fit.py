"""Fail-closed source-target-predictor checks and offline legacy audit."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from quant_research_agent import autonomous_loop as loop
from quant_research_agent import source_fit as fit
from quant_research_agent import source_fit_audit as audit

NOW = datetime(2026, 11, 18, 11, 40, 39, tzinfo=timezone.utc)
BAD_DOI = "10.1016/j.frl.2025.108661"
BAD_TITLE = "A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns"
GOOD_TITLE = "Day-of-the-week effects on Bitcoin spot daily returns"
GOOD_ABSTRACT = "<jats:p>We evaluate day-of-the-week patterns in Bitcoin spot daily returns, including Mondays.</jats:p>"


def article(doi: str, title: str, abstract=None):
    obj = {"DOI": doi, "type": "journal-article", "title": [title],
           "published": {"date-parts": [[2025, 6, 1]]}}
    if abstract is not None:
        obj["abstract"] = abstract
    return obj


def crossref(items):
    return json.dumps({"status": "ok", "message": {"items": items}}, ensure_ascii=False).encode()


class SourceFitTest(unittest.TestCase):
    def check(self, title, abstract, expected):
        actual = fit.assess_source(title, abstract)
        self.assertEqual(actual["decision"], expected)
        self.assertTrue(actual["not_a_paper_replication"])
        self.assertEqual(actual["expected_target"], "BTC_SPOT_DAILY_LOG_RETURN")
        return actual

    def test_actual_misidentified_crypto_to_stocks_doi(self):
        found = self.check(BAD_TITLE, None, fit.REJECT_TARGET)
        self.assertEqual(found["reason_code"], "STOCK_RETURNS_ARE_PREDICTED_OUTCOME")

    def test_valid_btc_monday_with_abstract(self):
        self.check("Monday effects in Bitcoin spot returns",
                   "This paper investigates Monday effects in Bitcoin spot returns.", fit.AUTO)

    def test_day_of_week_btc_scope_is_relevant_without_presuming_positive_effect(self):
        self.check(GOOD_TITLE, GOOD_ABSTRACT, fit.AUTO)
        self.check(GOOD_TITLE,
                   "We find NO day-of-the-week return predictability for Bitcoin spot returns.", fit.AUTO)

    def test_no_abstract_forces_review_even_if_title_clear(self):
        x = self.check(GOOD_TITLE, None, fit.REVIEW)
        self.assertEqual(x["reason_code"], "ABSTRACT_UNAVAILABLE_TO_CONFIRM_DIRECTION")

    def test_generic_cryptocurrency_not_explicit_btc_target(self):
        self.check("Calendar effects on returns and volatility: Evidence from crypto markets",
                   "We investigate calendar effects in cryptocurrency returns.", fit.REVIEW)

    def test_weekend_only_does_not_authorize_monday_dummy(self):
        self.check("Weekend seasonality in Bitcoin spot returns",
                   "We investigate Bitcoin spot returns during weekends.", fit.REVIEW)

    def test_stock_target_in_abstract_overrides_positive_title(self):
        self.check(GOOD_TITLE,
                   "Bitcoin returns predict Monday stock returns; we examine day-of-the-week volatility.", fit.REJECT_TARGET)

    def test_btc_futures_is_wrong_market(self):
        self.check("Day-of-the-week effects on Bitcoin futures returns",
                   "We analyze day-of-the-week effects on Bitcoin futures returns.", fit.REJECT_MARKET)

    def test_using_weekend_crypto_returns_not_monday_indicator(self):
        self.check("Monday Bitcoin returns predicted using weekend cryptocurrency returns",
                   "We use weekend cryptocurrency returns to predict Monday Bitcoin returns.", fit.REJECT_PREDICTOR)

    def test_stock_is_comparator_not_dependent_variable(self):
        self.check("Monday effects in Bitcoin spot returns compared with stock markets",
                   "Bitcoin spot returns exhibit Monday effects unlike broad equity markets.", fit.AUTO)

    def test_jats_abstract_cleaning_safe_and_nonexecuting(self):
        out = fit.clean_abstract('<jats:p>Bitcoin <jats:italic>daily</jats:italic> returns &amp; weekday seasonality.</jats:p>')
        self.assertEqual(out, "Bitcoin daily returns & weekday seasonality.")
        self.assertEqual(fit.clean_abstract("x" * 30000), "")


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "runtime"
        agent = self.root / "agent"
        (agent / "evidence").mkdir(parents=True)
        self.dbfile = agent / "autonomous_loop.sqlite3"
        with sqlite3.connect(self.dbfile) as db:
            db.executescript(loop.SQL)

    def populate(self, items, *, prior_study=True):
        raw = crossref(items)
        digest = hashlib.sha256(raw).hexdigest()
        (self.root / "agent/evidence/crossref-poll-1.json").write_bytes(raw)
        parsed = loop.parse_papers(raw, 20, NOW)
        with sqlite3.connect(self.dbfile) as db:
            db.execute("INSERT INTO polls(id,at,status,response_sha) VALUES(?,?,?,?)",
                       (1, NOW.isoformat(), "COMPLETED", digest))
            for p in parsed:
                db.execute("INSERT INTO papers(doi,title,publication_year,url,at,response_sha,decision,research_template) VALUES(?,?,?,?,?,?,?,?)",
                    (p["doi"], p["title"], p["publication_year"], p["url"], NOW.isoformat(), digest,
                     "ELIGIBLE_TITLE_CUE_ONLY", loop.APPROVED_TEMPLATE))
            if prior_study:
                db.execute("INSERT INTO studies(template_id,doi,status,created_at,completed_at,report_path,report_sha) VALUES(?,?,?,?,?,?,?)",
                    (loop.APPROVED_TEMPLATE, parsed[0]["doi"], "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
                     NOW.isoformat(), NOW.isoformat(), "agent/reports/BTC_WEEKDAY_INFORMATION_v1.json", "a"*64))
        return raw, digest

    def test_offline_legacy_mismatch_archive_audit_no_state_mutation(self):
        self.populate([article(BAD_DOI, BAD_TITLE)])
        original_db = self.dbfile.read_bytes()
        archived = self.root / "agent/reports/BTC_WEEKDAY_INFORMATION_v1.json"
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(b"pre-existing immutable report; do not replace")
        old_report = archived.read_bytes()
        result = audit.audit_existing(self.root)
        self.assertEqual(result["paper_count"], 1)
        self.assertEqual(result["decision_counts"][fit.REJECT_TARGET], 1)
        self.assertEqual(result["previous_study_source_fit"][0]["doi"], BAD_DOI)
        self.assertFalse(result["experiments_rerun"])
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(archived.read_bytes(), old_report)
        self.assertEqual(self.dbfile.read_bytes(), original_db)
        report = Path(result["audit_path"])
        self.assertTrue(report.is_file())
        self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), result["audit_sha256"])
        self.assertEqual(audit.audit_existing(self.root)["audit_path"], result["audit_path"])

    def test_existing_paper_collection_reassessed_not_rerun(self):
        papers = [article(BAD_DOI, BAD_TITLE), article("10.1234/positive1", GOOD_TITLE, GOOD_ABSTRACT)]
        papers += [article(f"10.1234/unknown{i}", "Generic cryptocurrency market volatility") for i in range(13)]
        self.populate(papers)
        x = audit.audit_existing(self.root)
        self.assertEqual(x["paper_count"], 15)
        self.assertEqual(x["decision_counts"][fit.REJECT_TARGET], 1)
        self.assertEqual(x["decision_counts"][fit.AUTO], 1)
        self.assertEqual(x["decision_counts"][fit.REVIEW], 13)

    def test_mismatched_raw_digest_fails_closed(self):
        self.populate([article(BAD_DOI, BAD_TITLE)])
        path = self.root / "agent/evidence/crossref-poll-1.json"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            audit.audit_existing(self.root)

    def test_missing_raw_fails_closed(self):
        self.populate([article(BAD_DOI, BAD_TITLE)])
        (self.root / "agent/evidence/crossref-poll-1.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing/out-of-root"):
            audit.audit_existing(self.root)

    def test_missing_db_never_creates_research(self):
        self.dbfile.unlink()
        with self.assertRaisesRegex(ValueError, "No existing P1"):
            audit.audit_existing(self.root)
        self.assertFalse(self.dbfile.exists())

    def test_title_db_tampering_blocked(self):
        self.populate([article(BAD_DOI, BAD_TITLE)])
        with sqlite3.connect(self.dbfile) as db:
            db.execute("UPDATE papers SET title='False article title'")
        with self.assertRaisesRegex(ValueError, "does not match original"):
            audit.audit_existing(self.root)


if __name__ == "__main__":
    unittest.main()
