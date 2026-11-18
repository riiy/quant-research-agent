"""Offline end-to-end bounded research-loop tests (no live network or exchange)."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quant_research_agent import autonomous_loop as a, weekday_mechanism as w

START = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)


def policy():
    return {"schema_version": 1, "research_only": True, **{k: False for k in a.FLAGS},
            "source": "crossref", "search_query": a.APPROVED_QUERY,
            "max_results": 20, "poll_interval_hours": 24,
            "max_requests_per_utc_day": 1, "template": a.APPROVED_TEMPLATE,
            "spot_path": "data/BTCUSDT-1d.csv"}


def item(doi="10.1016/j.najef.2025.102441", title="Day-of-the-week effects on Bitcoin spot daily returns",
         abstract="<jats:p>We analyze day-of-the-week calendar effects on Bitcoin spot daily returns.</jats:p>"):
    return {"DOI": doi, "type": "journal-article", "title": [title],
            "published": {"date-parts": [[2025, 1, 1]]}, "abstract": abstract}


def response(items=None):
    return json.dumps({"status":"ok", "message":{"items":items if items is not None else [item()]}},
                      ensure_ascii=False).encode()


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/"runtime"
        self.config = Path(self.temp.name)/"policy.json"
        self.write_policy(policy())

    def write_policy(self, p):
        self.config.write_text(json.dumps(p), encoding="utf8")

    def go(self, raw=None, now=START, fetcher=None):
        cb = fetcher or (lambda p: response() if raw is None else raw)
        return a.cycle(self.root, self.config, now=now, fetcher=cb)

    def test_discovery_doi_title_and_missing_spot(self):
        x = self.go()
        self.assertEqual(x["status"], "BLOCKED_MISSING_SPOT")
        self.assertEqual(x["study_status"], "WAITING_DATA")
        st = a.status(self.root)
        self.assertEqual(st["paper_counts"], [{"decision":"ELIGIBLE_FOR_FROZEN_TEMPLATE", "count":1}])
        self.assertEqual(st["studies"][0]["doi"], "10.1016/j.najef.2025.102441")
        self.assertFalse(st["trading_allowed"])

    def test_same_day_or_before_interval_never_refetches(self):
        self.go(raw=response([]))
        calls = []
        def fetch(p):
            calls.append(p)
            return response([])
        self.assertEqual(self.go(now=START+timedelta(hours=1), fetcher=fetch)["status"], "IDLE_POLL_INTERVAL")
        self.assertFalse(calls)
        self.assertEqual(self.go(now=START+timedelta(days=1), fetcher=fetch)["status"], "NO_NEW_EVIDENCE")
        self.assertEqual(len(calls), 1)

    def test_paper_metadata_alone_not_empirical_validation(self):
        papers = [item("10.1234/a", "Trading volume in Bitcoin weekend sessions", abstract=None),
                  item("10.1234/b", "Revisiting seasonality in cryptocurrencies", abstract=None)]
        x = self.go(raw=response(papers))
        self.assertEqual(x["status"], "EVIDENCE_ARCHIVED_NO_NEW_EXECUTABLE_STUDY")
        self.assertEqual(x["eligible_title_cues"], 0)
        self.assertFalse(a.status(self.root)["studies"])

    def test_unsafe_policy_fails_closed_before_http(self):
        for key in a.FLAGS:
            p=policy();p[key]=True; self.write_policy(p)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.go(fetcher=lambda _: self.fail("Network must not be called"))
        p=policy();p["source"]="http://169.254.169.254";self.write_policy(p)
        with self.assertRaisesRegex(ValueError,"frozen"):
            self.go(fetcher=lambda _: self.fail("Network must not be called"))
        p=policy();p["spot_path"]="../2025.csv";self.write_policy(p)
        with self.assertRaisesRegex(ValueError,"frozen"):
            self.go(fetcher=lambda _: self.fail("Network must not be called"))

    def test_policy_drift_refused(self):
        self.go(raw=response([]))
        p=policy();p["max_results"]=10;self.write_policy(p)
        with self.assertRaisesRegex(ValueError,"POLICY_DRIFT_BLOCKED"):
            self.go(now=START+timedelta(days=1),fetcher=lambda _: self.fail("No calls"))

    def test_source_failure_recorded_and_not_retried_immediately(self):
        def fail(_): raise OSError("Offline")
        result=self.go(fetcher=fail)
        self.assertEqual(result["status"],"STOP_SOURCE_UNAVAILABLE")
        self.assertEqual(result["reason"],"OSError")
        self.assertEqual(self.go(now=START+timedelta(hours=1),fetcher=lambda _: self.fail("No retry"))["status"],"IDLE_POLL_INTERVAL")
        self.assertEqual(a.status(self.root)["last_poll"]["status"],"FAILED")

    def test_pause_respects_p0_marker(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/"PAUSED").write_text("Paused")
        self.assertEqual(self.go(fetcher=lambda _: self.fail("No call"))["status"], "PAUSED")
        self.assertIsNone(a.status(self.root)["last_poll"])

    def test_malformed_crossref_blocks_no_research(self):
        self.assertEqual(self.go(raw=b'{"error":true}')["status"],"STOP_SOURCE_UNAVAILABLE")
        self.assertEqual(a.status(self.root)["studies"],[])

    def test_new_title_cue_runs_single_template_and_archives(self):
        spot=self.root/"data/BTCUSDT-1d.csv"
        spot.parent.mkdir(parents=True)
        spot.write_text("existing pinned fixture mocked for this test", encoding="utf8")
        result = {"status":"STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
                  "gates":{"fixed": False},"trading_allowed":False,"holdout_evaluated":False}
        with patch.object(w, "run", return_value=result) as mock:
            first=self.go()
            self.assertEqual(first["status"],"STOP_INSUFFICIENT_INCREMENTAL_INFORMATION")
            self.assertEqual(mock.call_count, 1)
            report_path=Path(first["research_report"])
            self.assertTrue(report_path.exists())
            doc=json.loads(report_path.read_text())
            self.assertEqual(doc["evidence"]["doi"],"10.1016/j.najef.2025.102441")
            self.assertTrue(doc["autonomous_discovery"])
            self.assertFalse(doc["trading_allowed"])
            self.assertEqual(doc["falsification"]["status"],"STOP_INSUFFICIENT_INCREMENTAL_INFORMATION")
            with patch.object(w, "run", side_effect=AssertionError("Second run forbidden")):
                second=self.go(now=START+timedelta(days=1),
                    fetcher=lambda _:self.fail("Saturated P1 must not poll Crossref"))
            self.assertEqual(second["status"],"IDLE_TEMPLATE_SATURATED")
            st=a.status(self.root)
            self.assertEqual(st["studies"][0]["status"],"STOP_INSUFFICIENT_INCREMENTAL_INFORMATION")
            self.assertEqual(len(st["studies"]),1)

    def test_waiting_study_can_run_offline_without_second_http_call(self):
        self.assertEqual(self.go()["status"],"BLOCKED_MISSING_SPOT")
        spot=self.root/"data/BTCUSDT-1d.csv"
        spot.parent.mkdir(parents=True)
        spot.write_text("mocked")
        with patch.object(w, "run", return_value={"status":"STOP_INSUFFICIENT_INCREMENTAL_INFORMATION","gates":{}}):
            res=self.go(now=START+timedelta(hours=1),fetcher=lambda _:self.fail("No second HTTP"))
        self.assertEqual(res["status"],"STOP_INSUFFICIENT_INCREMENTAL_INFORMATION")

    def test_failed_study_is_not_rescued(self):
        spot=self.root/"data/BTCUSDT-1d.csv"
        spot.parent.mkdir(parents=True)
        spot.write_text("mocked")
        with patch.object(w,"run",side_effect=ValueError("bad raw data")):
            self.assertEqual(self.go()["status"],"FAILED_REVIEW_REQUIRED")
        with patch.object(w,"run",side_effect=AssertionError("Rerun forbidden")):
            self.go(now=START+timedelta(days=1))
        self.assertEqual(a.status(self.root)["studies"][0]["status"],"FAILED_REVIEW_REQUIRED")

    def test_interrupted_pending_claim_requires_review(self):
        self.go()
        db=a.connect(self.root)
        with db:
            db.execute("UPDATE studies SET status='RUNNING'")
        db.close()
        self.assertEqual(self.go(now=START+timedelta(hours=1))["status"],"INTERRUPTED_REVIEW_REQUIRED")
        self.assertEqual(a.status(self.root)["studies"][0]["status"],"INTERRUPTED_REVIEW_REQUIRED")

    def test_cli_status_exit_without_top_level_status(self):
        output=StringIO()
        with redirect_stdout(output):
            code=a.main(["--home",str(self.root),"status"])
        self.assertEqual(code,0)
        self.assertNotIn("status",json.loads(output.getvalue()))

    def test_legacy_waiting_data_bad_paper_is_blocked_before_spot_backtest(self):
        bad = item("10.1016/j.frl.2025.108661",
                   "A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns",
                   abstract=None)
        first = self.go(raw=response([bad]))
        self.assertEqual(first["status"], "EVIDENCE_ARCHIVED_NO_NEW_EXECUTABLE_STUDY")
        # Simulate a previously title-only approved WAITING_DATA record.
        db=a.connect(self.root)
        with db:
            db.execute("INSERT INTO studies(template_id,doi,status,created_at) VALUES(?,?,?,?)",
                       (a.APPROVED_TEMPLATE, bad["DOI"], "WAITING_DATA", START.isoformat()))
        db.close()
        spot=self.root/"data/BTCUSDT-1d.csv"
        spot.parent.mkdir(parents=True, exist_ok=True)
        spot.write_text("mock spot")
        with patch.object(w, "run", side_effect=AssertionError("Source mismatch must stop before prices")):
            outcome=self.go(now=START+timedelta(hours=1),
                            fetcher=lambda _:self.fail("No HTTP for waiting records"))
        self.assertEqual(outcome["status"], "SOURCE_FIT_REVIEW_REQUIRED")
        self.assertFalse(outcome["experiment_executed"])
        self.assertEqual(a.status(self.root)["studies"][0]["status"], "SOURCE_FIT_REVIEW_REQUIRED")

    def test_new_crossref_stock_target_paper_is_never_executed(self):
        bad = item("10.1016/j.frl.2025.108661",
                   "A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns",
                   abstract="Weekend cryptocurrency returns predict Monday stock returns.")
        with patch.object(w, "run", side_effect=AssertionError("Never execute")):
            out=self.go(raw=response([bad]))
        self.assertEqual(out["status"], "EVIDENCE_ARCHIVED_NO_NEW_EXECUTABLE_STUDY")
        self.assertEqual(a.status(self.root)["paper_counts"][0]["decision"],
                         "REJECT_TARGET_MISMATCH")
        self.assertEqual(a.status(self.root)["studies"], [])

    def test_explicit_title_without_abstract_requires_human_review(self):
        paper=item(abstract=None)
        with patch.object(w, "run", side_effect=AssertionError("Missing abstract must not auto-execute")):
            out=self.go(raw=response([paper]))
        self.assertEqual(out["status"], "EVIDENCE_ARCHIVED_NO_NEW_EXECUTABLE_STUDY")
        self.assertEqual(a.status(self.root)["paper_counts"][0]["decision"],
                         "NEEDS_HUMAN_SOURCE_REVIEW")

    def test_cli_relevance_audit_no_network_and_historical_snapshot(self):
        self.go(raw=response([item("10.1016/j.frl.2025.108661",
            "A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns",
            abstract=None)]))
        output=StringIO()
        with redirect_stdout(output):
            code=a.main(["--home",str(self.root),"relevance-audit"])
        self.assertEqual(code,0)
        report=json.loads(output.getvalue())
        self.assertEqual(report["status"], "SOURCE_FIT_AUDIT_COMPLETED")
        self.assertEqual(report["paper_count"],1)
        self.assertFalse(report["experiments_rerun"])
        self.assertEqual(report["decision_counts"]["REJECT_TARGET_MISMATCH"],1)

    def test_paper_normalization_deduplication(self):
        papers=a.parse_papers(response([item(), item(doi="10.1016/J.NAJEF.2025.102441")]),20,START)
        self.assertEqual(len(papers),1)
        self.assertEqual(papers[0]["url"],"https://doi.org/10.1016/j.najef.2025.102441")

    def test_raw_crossref_evidence_archived_bytes_and_hash(self):
        raw=response([item()])
        self.go(raw=raw)
        archived=self.root/"agent/evidence/crossref-poll-1.json"
        self.assertEqual(archived.read_bytes(),raw)
        self.assertEqual(a.status(self.root)["last_poll"]["response_sha"],a.sha(raw))



class WeekdayTest(unittest.TestCase):
    def make_prices(self, monday_alpha: float):
        d=date(2020,1,1);p=10000.;result={}
        for n in range(1461):
            # Mechanical synthetic weekly mean effect, no source claim.
            shock=0.009*((n*13)%17-8)/8
            uplift=monday_alpha if d.weekday()==0 else 0.
            p*=__import__("math").exp(shock+uplift)
            result[d]=(p,1000.+(n*71)%300)
            d+=timedelta(days=1)
        return result

    def test_data_joins_and_strict_calendar(self):
        train,test=w.build_rows(self.make_prices(0.0))
        self.assertEqual(len(test),730)
        self.assertEqual(test[0]["day"],date(2022,1,1))
        self.assertEqual(test[-1]["day"],date(2023,12,31))
        self.assertTrue(all(x["day"].year <= 2021 for x in train))
        self.assertEqual([len([x for x in test if x["day"].year==y]) for y in (2022,2023)],[365,365])

    def test_synthetic_known_monday_effect_is_detectable(self):
        report=w.evaluate(self.make_prices(0.03))
        self.assertEqual(report["status"],"PASS_RETROSPECTIVE_MECHANISM_ONLY")
        self.assertGreater(report["metrics"]["relative_mse_gain"],0.02)
        self.assertTrue(all(report["gates"].values()))
        self.assertFalse(report["trading_allowed"])

    def test_pinned_loader_stops_before_2024_values_and_rejects_modified_prefix(self):
        import hashlib
        from unittest.mock import patch
        data = self.make_prices(0.0)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"spot.csv"
            lines=["day,open,high,low,close,volume"]
            for day,(close,vol) in data.items():
                lines.append(f"{day},{close},{close},{close},{close},{vol}")
            lines += ["2024-01-01,NOT_A_NUMBER,THIS_IS_SEALED,0,0,0"]
            path.write_text("\n".join(lines)+"\n",encoding="utf8")
            # Synthetic prefix: patch only the expected SHA, never bypass coverage checks.
            h=hashlib.sha256()
            for day,(close,vol) in data.items():
                vals=[close,close,close,close,vol]
                h.update((str(day)+","+",".join(format(v,".17g") for v in vals)+"\n").encode())
            with patch.object(w,"SPOT_PREFIX_SHA",h.hexdigest()):
                prices,prov=w.load_spot(path)
                self.assertEqual(len(prices),1461)
                self.assertEqual(prov["last"],"2023-12-31")
                # Altered prefix must fail even though the suffix is unread.
                path.write_text(path.read_text().replace("2020-01-01,", "2020-01-01,999,"),encoding="utf8")
                with self.assertRaises(ValueError):
                    w.load_spot(path)

    def test_frozen_single_calendar_feature(self):
        x=w.evaluate(self.make_prices(0.0))
        self.assertEqual(x["research_id"],"BTC_WEEKDAY_INFORMATION_v1")
        self.assertEqual(len(x["model_fits"]["baseline"]["intercept_and_standardized_coefficients"]),4)
        self.assertEqual(len(x["model_fits"]["monday_augmented"]["intercept_and_standardized_coefficients"]),5)
        self.assertFalse(x["holdout_evaluated"])


if __name__=="__main__":unittest.main()
