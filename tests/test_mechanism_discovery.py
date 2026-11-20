"""P2-A safety tests: synthetic fixtures do NOT establish scientific novelty."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from quant_research_agent import mechanism_discovery as m

DOI = "10.1234/inventory.paper"
TITLE = "Limits to Arbitrage and Bitcoin Spot Inventory Constraints"
ABSTRACT = ("We examine binding inventory constraints and price dislocations across Bitcoin spot venues "
            "using settlement-level order imbalances. Large position limits restrict arbitrage supply.")


def proposal():
    return {
        "schema_version": 1, "doi": DOI, "mechanism_id": "inventory_constraints_v1",
        "execution_authorized": False,
        "mechanism": {
            "name": "Inventory constrained arbitrage provision", "family": "inventory_capacity",
            "actors": "Balance sheet constrained spot liquidity providers",
            "friction_or_incentive": "Finite settlement inventory impedes arbitrage supply",
            "causal_chain": "Binding inventory capacity can cause temporary cross-venue price deviations",
            "conditions": "Venue-level settlement inventory scarcity during cross-venue imbalance episodes",
            "why_not_indicator": "Balance-sheet settlement friction is institution-specific rather than a price moving average",
            "counterevidence": "If inventory constraints do not co-move with price dislocations, stop",
        },
        "source_quotes": [
            {"quote": "binding inventory constraints and price dislocations across Bitcoin spot venues",
             "interpretation": "Abstract suggests an inventory friction; predictive effect remains unproven"}
        ],
        "novelty": {
            "closest_archived": "liquidity_reversal",
            "shared_features": "Both involve liquidity provision",
            "economic_difference": "The proposed friction is venue settlement inventory, not cross-sectional coin illiquidity",
            "relabel_risk": "May be old liquidity reversal wearing a new label, subject to independent review",
        },
        "protocol": {
            "hypothesis": "Lagged venue inventory imbalance predicts next-period cross-venue price convergence",
            "null": "Conditional inventory imbalance has no predictive information beyond contemporaneous basis",
            "falsifier": "Stop if imbalance fails to add an OOS improvement over venue-price controls",
            "target": {"market": "Bitcoin spot", "instrument": "BTC spot pairs",
                       "variable": "Cross-venue basis convergence", "frequency": "daily", "horizon": "next full UTC day"},
            "predictor": {"variable": "Lagged inventory imbalance", "proxy": "Signed settlement balance changes",
                          "available_at": "Only after settlement snapshot timestamp",
                          "publication_lag": "one full UTC day"},
            "data": [{"name": "Venue inventory panel", "provider": "Unverified exchange archive",
                      "availability": "UNVERIFIED", "point_in_time": "Must verify historical immutable publication snapshots",
                      "timestamp_rule": "No feature timestamp later than prior-day UTC close"}],
            "sample": {"calibration": "Pre-2022 historical window if available",
                       "evaluation": "2022-2023 if not previously consumed",
                       "sealed_holdout_excluded": True},
            "baseline": "Same cross-venue basis prediction excluding inventory proxy",
            "method": "Frozen univariate incremental OOS regression or permutation test",
            "oos": "Chronological forward validation across two years without parameter optimization",
            "metrics": ["Out-of-sample squared error difference", "Block bootstrap paired confidence lower bound"],
            "pass_rule": "At least two percent OOS improvement and one-sided 95 percent lower bound above zero",
            "stop_rule": "Stop on unavailable point-in-time data, nonpositive OOS lift or failed stability",
            "leakage_checks": ["Snapshot lag before target starts", "No revisions or final-year selection"],
            "costs_and_execution": "No strategy backtest; later execution must include venue fees, latency and transfer limits",
            "budget": {"max_research_hours": 4, "max_new_network_requests": 0,
                       "max_model_calls": 0, "max_spend_usd": 0},
            "human_escalation": "Verify source-to-hypothesis and actual dataset rights before any test approval",
        },
    }


class MechanismGateTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name).resolve()
        self.source_file = self.root / "agent/evidence_enrichment/raw/test-crossref.json"
        self.source_file.parent.mkdir(parents=True)
        self.entry = {}
        self.update_source(TITLE, ABSTRACT)
        self.write_proposal(proposal())

    def update_source(self, title, abstract):
        raw = json.dumps({"status": "ok", "message": {
            "DOI": DOI, "title": [title], "abstract": abstract
        }}).encode()
        self.source_file.write_bytes(raw)
        self.entry = {
            "doi": DOI, "title": title, "abstract_status": "AVAILABLE",
            "abstract_sha256": m._sha(abstract.encode()),
            "provenance": [{"provider": "Crossref", "has_abstract": True,
                            "doi_verified": True, "raw_path": "agent/evidence_enrichment/raw/test-crossref.json",
                            "raw_sha256": m._sha(raw), "observed_at": "2026-11-20T00:00:00Z"}],
        }
        report = json.dumps({"entries": [self.entry], "experiments_executed": 0,
                             "trading_allowed": False}).encode()
        self.report = "agent/reports/abstract-evidence-v1-" + m._sha(report)[:12] + ".json"
        path = self.root / self.report
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(report)

    def write_proposal(self, p):
        self.proposal_file = "agent/proposal.json"
        path = self.root / self.proposal_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(p))

    def evaluate(self, p):
        self.write_proposal(p)
        return m.review(self.root, self.report, self.proposal_file)

    def test_complete_review_is_safe_and_idempotent(self):
        output = self.evaluate(proposal())
        self.assertEqual(output["status"], "NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW")
        self.assertEqual(output, m.review(self.root, self.report, self.proposal_file))
        record = json.loads(Path(output["report_path"]).read_text())
        self.assertFalse(record["execution_authorized"])
        self.assertTrue(record["causal_claims_and_novelty_are_unverified_inferences"])
        self.assertEqual(record["experiments_executed"], 0)
        self.assertNotIn("abstract", record["source"])

    def test_no_model_proposal_safe_abstention(self):
        out = m.review(self.root, self.report, None)
        self.assertEqual(out["status"], "NO_MODEL_PROPOSAL_UNDER_CURRENT_PERMISSIONS")
        self.assertEqual(out["network_requests"], 0)

    def test_archived_mechanism_relabels_rejected(self):
        variants = [
            ("trend_persistence", "inventory capacity"),
            ("inventory_capacity", "moving average crossover"),
            ("inventory_capacity", "perpetual funding pressure"),
            ("inventory_capacity", "Google Trends investor attention"),
            ("inventory_capacity", "Monday effect in BTC returns"),
        ]
        for family, phrase in variants:
            with self.subTest(phrase=phrase):
                p = proposal()
                p["mechanism"]["family"] = family
                p["mechanism"]["causal_chain"] = phrase + " affects the spot price signal"
                self.assertEqual(self.evaluate(p)["status"], "REJECT_ARCHIVED_MECHANISM")

    def test_wrong_target_stock_to_btc_stops(self):
        phrase = "Weekend cryptocurrency returns predict Monday stock returns."
        self.update_source("Predicting Monday stock returns using weekend cryptocurrency returns", phrase)
        p = proposal()
        p["source_quotes"] = [{"quote": phrase, "interpretation": "This predicts stocks not BTC itself, so transfers remain unverified"}]
        self.assertEqual(self.evaluate(p)["status"], "REJECT_SOURCE_TARGET_MISMATCH")

    def test_hallucinated_source_quote_blocked(self):
        p = proposal()
        p["source_quotes"][0]["quote"] = "An impossible quoted result never present in the abstract"
        with self.assertRaisesRegex(ValueError, "Invented"):
            self.evaluate(p)

    def test_no_data_or_self_asserted_data_blocked(self):
        p = proposal()
        p["protocol"]["data"] = []
        with self.assertRaisesRegex(ValueError, "dataset"):
            self.evaluate(p)
        p = proposal()
        p["protocol"]["data"][0]["availability"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "self-certify"):
            self.evaluate(p)

    def test_no_unapproved_execution_model_budget_or_holdout(self):
        p = proposal()
        p["execution_authorized"] = True
        with self.assertRaisesRegex(ValueError, "cannot authorize"):
            self.evaluate(p)
        p = proposal()
        p["protocol"]["budget"]["max_model_calls"] = 1
        with self.assertRaisesRegex(ValueError, "budget"):
            self.evaluate(p)
        p = proposal()
        p["protocol"]["sample"]["sealed_holdout_excluded"] = False
        with self.assertRaisesRegex(ValueError, "Sealed"):
            self.evaluate(p)

    def test_schema_and_novelty_comparison_mandatory(self):
        p = proposal()
        p["generated_python"] = "print('bad')"
        with self.assertRaisesRegex(ValueError, "exact schema"):
            self.evaluate(p)
        p = proposal()
        p["novelty"]["closest_archived"] = "no_previous_work"
        with self.assertRaisesRegex(ValueError, "comparison"):
            self.evaluate(p)

    def test_source_hashes_are_checked(self):
        self.source_file.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.evaluate(proposal())
        (self.root / self.report).write_text("tampered")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.evaluate(proposal())

    def test_pause_is_respected(self):
        (self.root / "PAUSED").touch()
        self.assertEqual(self.evaluate(proposal())["status"], "PAUSED")


if __name__ == "__main__":
    unittest.main()
