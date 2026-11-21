"""Offline P2-B guard tests; no actual Crossref/OpenAlex/model network calls."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from quant_research_agent import p2b_pilot as p

NOW = datetime(2026, 11, 20, 13, 0, tzinfo=timezone.utc)
D1 = "10.1234/novel-a"
D2 = "10.1234/novel-b"
TITLE = "Cross Venue Settlement Constraints and Cryptocurrency Spot Prices"
ABSTRACT = "We investigate settlement constraints and cross-venue price dispersion in cryptocurrency spot markets."


def search(doi=D1, extra=None):
    rows = [{
        "DOI": doi,
        "title": [TITLE],
        "published": {"date-parts": [[2025, 6, 3]]},
    }]
    if extra:
        rows.extend(extra)
    return json.dumps({"status": "ok", "message": {"items": rows}}).encode()


def crossref(doi=D1, abstract=ABSTRACT):
    v = {"DOI": doi, "title": [TITLE]}
    if abstract is not None:
        v["abstract"] = abstract
    return json.dumps({"status": "ok", "message": v}).encode()


def abstain_response():
    decision = {"decision": "ABSTAIN", "proposal": None,
                "reason_code": "NO_NEW_FEASIBLE_MECHANISM",
                "reason": "No independently credible and feasible mechanism can be established from the given abstracts."}
    return json.dumps({"status": "completed", "model": p.MODEL, "service_tier": "default",
                       "usage": {"input_tokens": 3500, "output_tokens": 200},
                       "output": [{"content": [{"type": "output_text", "text": json.dumps(decision)}]}]}).encode()


class PilotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        dbp = self.root / "agent/autonomous_loop.sqlite3"
        dbp.parent.mkdir(parents=True)
        with sqlite3.connect(dbp) as db:
            db.execute("CREATE TABLE papers(doi TEXT)")
            db.execute("INSERT INTO papers VALUES(?)", ("10.1234/old",))
        self.calls = []
        a = p.approval_template()
        a["approved"] = True
        a["approval_reference"] = "owner-reviewed-P2B-2026-11-20-explicit-model-id"
        a["approved_at_utc"] = "2026-11-20T12:30:00+00:00"
        a["pricing_verified_at_utc"] = "2026-11-20T12:30:00+00:00"
        self.approval = a
        self.store_approval()

    def store_approval(self):
        path = self.root / "p2b" / p.ID / "owner-approval.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.approval))

    def fetch(self, url, size):
        self.calls.append(("source", url))
        if url == p.SEARCH_URL:
            return search()
        if "api.crossref.org" in url:
            return crossref()
        return json.dumps({"results": []}).encode()

    def model(self, body):
        self.calls.append(("model", p.MODEL))
        self.assertIn(b'"service_tier":"default"', body)
        self.assertIn(b'"tools":[]', body)
        self.assertLessEqual(len(body), p.MAX_INPUT_BYTES)
        return abstain_response()

    def test_frozen_query_and_first_unseen_do_not_cherrypick(self):
        raw = search("10.1234/old", extra=[
            {"DOI": D1, "title": [TITLE], "published": {"date-parts": [[2025, 2, 4]]}},
            {"DOI": D2, "title": [TITLE], "published": {"date-parts": [[2025, 2, 4]]}},
        ])
        self.assertEqual([v["doi"] for v in p.choose(raw, {"10.1234/old"})], [D1, D2])
        self.assertIn("query.bibliographic=cryptocurrency+markets", p.SEARCH_URL)
        self.assertLessEqual(p.MAX_SOURCE_CALLS, 7)

    def test_without_explicit_approval_zero_requests(self):
        self.approval["approved"] = False
        self.store_approval()
        with self.assertRaisesRegex(ValueError, "approval"):
            p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "p2b" / p.ID / "attempt.claim").exists())

    def test_wrong_model_or_policy_drift_fails_closed(self):
        self.approval["model_id"] = "gpt-6-luna"
        self.store_approval()
        with self.assertRaisesRegex(ValueError, "policy drift"):
            p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
        self.assertEqual(self.calls, [])

    def test_expired_price_or_invalid_code_hash_fails_before_request(self):
        self.approval["pricing_verified_at_utc"] = "2026-11-18T00:00:00Z"
        self.store_approval()
        with self.assertRaisesRegex(ValueError, "24 UTC hours"):
            p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
        self.approval["pricing_verified_at_utc"] = "2026-11-20T12:30:00Z"
        self.approval["model_code_sha256"] = "0" * 64
        self.store_approval()
        with self.assertRaisesRegex(ValueError, "policy drift"):
            p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)

    def test_one_shot_abstention_and_no_second_attempt(self):
        output = p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
        self.assertEqual(output["status"], "NO_NEW_FEASIBLE_MECHANISM")
        self.assertEqual(output["network_requests"], 2)
        self.assertEqual(output["model_calls"], 1)
        self.assertEqual(output["experiments_executed"], 0)
        self.assertEqual([x[0] for x in self.calls], ["source", "source", "model"])
        self.assertTrue((self.root / "p2b" / p.ID / "model-response.json").exists())
        with self.assertRaises(FileExistsError):
            p.run(self.root, now=NOW, fetch=lambda *_: self.fail("No retry"), invoke_model=self.model)
        self.assertEqual(len(self.calls), 3)

    def test_no_valid_candidates_does_not_call_model(self):
        self.fetch = lambda url, size: search("10.1234/old")
        out = p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=lambda _: self.fail("No model"))
        self.assertEqual(out["status"], "STOP_INSUFFICIENT_VERIFIED_SOURCE")
        self.assertEqual(out["network_requests"], 1)
        self.assertEqual(out["model_calls"], 0)

    def test_source_failure_is_terminal_no_retry(self):
        def broken(url, size):
            raise OSError("Network unavailable")
        out = p.run(self.root, now=NOW, fetch=broken, invoke_model=self.model)
        self.assertEqual(out["status"], "STOP_MODEL_OR_PROVENANCE_ERROR")
        self.assertEqual(out["network_requests"], 1)
        self.assertEqual(out["model_calls"], 0)
        self.assertTrue((self.root / "p2b" / p.ID / "outbound-claims.jsonl").exists())
        with self.assertRaises(FileExistsError):
            p.run(self.root, now=NOW, fetch=broken, invoke_model=self.model)

    def test_model_wrong_identity_or_cited_doi_is_terminal(self):
        wrong = json.loads(abstain_response())
        wrong["model"] = "gpt-6-luna"
        out = p.run(self.root, now=NOW, fetch=self.fetch,
                    invoke_model=lambda _: json.dumps(wrong).encode())
        self.assertEqual(out["status"], "STOP_MODEL_OR_PROVENANCE_ERROR")
        self.assertEqual(out["model_calls"], 1)

    def test_paused_stops_before_claim(self):
        (self.root / "PAUSED").touch()
        out = p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
        self.assertEqual(out["status"], "PAUSED")
        self.assertFalse((self.root / "p2b" / p.ID / "attempt.claim").exists())


    def test_p2a_adapter_is_hash_verified_and_awaits_human_review(self):
        decision = {"decision": "PROPOSE", "proposal": {"doi": D1},
                    "reason_code": None, "reason": None}
        def fake_model(body):
            self.calls.append(("model", p.MODEL))
            return json.dumps({"status": "completed", "model": p.MODEL, "service_tier": "default",
                               "usage": {"input_tokens": 1500, "output_tokens": 250},
                               "output": [{"content": [{"type": "output_text", "text": json.dumps(decision)}]}]}).encode()
        def review(adapter, report, proposal):
            verified = p.gate.verified_evidence(adapter, report, D1)
            self.assertEqual(verified["doi"], D1)
            self.assertEqual(verified["abstract"], ABSTRACT)
            self.assertEqual(json.loads((adapter / proposal).read_text())["doi"], D1)
            return {"status": "NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW"}
        with patch.object(p.gate, "review", side_effect=review):
            output = p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=fake_model)
        self.assertEqual(output["status"], "AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW")
        self.assertEqual(output["experiments_executed"], 0)
        self.assertEqual(output["network_requests"], 2)
        self.assertEqual(output["model_calls"], 1)

    def test_selected_doi_without_abstract_is_not_replaced(self):
        events = []
        def fetch(url, size):
            events.append(url)
            if url == p.SEARCH_URL:
                return search()
            if "api.crossref.org" in url:
                return crossref(abstract=None)
            return json.dumps({"results": []}).encode()
        out = p.run(self.root, now=NOW, fetch=fetch, invoke_model=lambda _: self.fail("No model for absent abstract"))
        self.assertEqual(out["status"], "STOP_INSUFFICIENT_VERIFIED_SOURCE")
        self.assertEqual(out["network_requests"], 3)
        self.assertEqual(out["model_calls"], 0)
        self.assertEqual(len(events), 3)


    def test_gateway_requires_explicit_billing_proof_before_any_call(self):
        env = {"BASE_URL": "https://gateway.example.test:9443/v1",
               "LLM_MODEL": "chatgpt/gpt6.2-sol", "LLM_API_STYLE": "responses",
               "LLM_API_KEY": "fake-only-for-mocked-tests", "LLM_USER_AGENT": "curl/8.5.0"}
        with patch.dict(os.environ, env, clear=True):
            self.approval = p.approval_template()
            self.approval["approved"] = True
            self.approval["approval_reference"] = "operator-reviewed-specific-gateway-model-proposal"
            self.approval["approved_at_utc"] = "2026-11-20T12:30:00Z"
            self.approval["pricing_verified_at_utc"] = "2026-11-20T12:30:00Z"
            self.store_approval()
            self.assertEqual(self.approval["model_provider"], "openai_compatible_gateway")
            self.assertEqual(self.approval["endpoint"], "https://gateway.example.test:9443/v1/responses")
            self.assertEqual(self.approval["input_price_usd_per_m"], 0.0)
            with self.assertRaisesRegex(ValueError, "rates"):
                p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
            self.assertEqual(self.calls, [])
            self.assertFalse((self.root / "p2b" / p.ID / "attempt.claim").exists())

    def test_gateway_explicit_rates_alias_and_no_service_tier(self):
        env = {"BASE_URL": "https://gateway.example.test:9443/v1",
               "LLM_MODEL": "chatgpt/gpt6.2-sol", "LLM_API_STYLE": "responses",
               "LLM_API_KEY": "fake-only-for-mocked-tests", "LLM_USER_AGENT": "curl/8.5.0"}
        with patch.dict(os.environ, env, clear=True):
            self.approval = p.approval_template()
            self.approval.update({"approved": True,
                                  "approval_reference": "operator-reviewed-specific-gateway-model-proposal",
                                  "approved_at_utc": "2026-11-20T12:30:00Z",
                                  "pricing_verified_at_utc": "2026-11-20T12:30:00Z",
                                  "pricing_reference": "operator-verified gateway billing dashboard 2026-11-20",
                                  "input_price_usd_per_m": 2.0,
                                  "output_price_usd_per_m": 10.0})
            self.store_approval()
            def model(body):
                self.assertIn(b'"model":"chatgpt/gpt6.2-sol"', body)
                self.assertNotIn(b'"service_tier"', body)
                self.assertLessEqual(len(body), p.MAX_INPUT_BYTES)
                response = json.loads(abstain_response())
                response["model"] = "chatgpt/gpt6.2-sol"
                response.pop("service_tier")
                return json.dumps(response).encode()
            output = p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=model)
        self.assertEqual(output["status"], "NO_NEW_FEASIBLE_MECHANISM")
        self.assertEqual(output["network_requests"], 2)
        self.assertEqual(output["model_calls"], 1)
        self.assertEqual(output["model"], "chatgpt/gpt6.2-sol")

    def test_gateway_drift_and_bad_style_rejected_before_source_calls(self):
        env = {"BASE_URL": "https://gateway.example.test:9443/v1",
               "LLM_MODEL": "chatgpt/gpt6.2-sol", "LLM_API_STYLE": "responses",
               "LLM_API_KEY": "fake-only-for-mocked-tests"}
        with patch.dict(os.environ, env, clear=True):
            self.approval = p.approval_template()
            self.approval.update({"approved": True,
                                  "approval_reference": "operator-reviewed-specific-gateway-model-proposal",
                                  "approved_at_utc": "2026-11-20T12:30:00Z",
                                  "pricing_verified_at_utc": "2026-11-20T12:30:00Z",
                                  "pricing_reference": "operator-verified gateway billing dashboard 2026-11-20",
                                  "input_price_usd_per_m": 2.0,
                                  "output_price_usd_per_m": 10.0})
            self.store_approval()
            with patch.dict(os.environ, {"LLM_MODEL": "chatgpt/different-model"}):
                with self.assertRaisesRegex(ValueError, "policy drift"):
                    p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
            with patch.dict(os.environ, {"LLM_API_STYLE": "chat_completions"}):
                with self.assertRaisesRegex(ValueError, "Gateway requires"):
                    p.run(self.root, now=NOW, fetch=self.fetch, invoke_model=self.model)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "p2b" / p.ID / "attempt.claim").exists())


if __name__ == "__main__":
    unittest.main()
