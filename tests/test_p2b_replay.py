"""P2B-002 mocked tests: frozen DOI replay, alias correction, zero source calls."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quant_research_agent import p2b_pilot as old
from quant_research_agent import p2b_replay as p
from quant_research_agent import mechanism_discovery as gate

NOW = datetime(2026, 11, 21, 3, 30, tzinfo=timezone.utc)
DOI = "10.1234/settlement-constraints"
TITLE = "Settlement Constraints and Cryptocurrency Price Dispersion"
ABSTRACT = "We study settlement frictions and price dispersion across cryptocurrency venues."


def response(decision=None):
    if decision is None:
        decision = {
            "decision": "ABSTAIN", "proposal": None,
            "reason_code": "NO_NEW_FEASIBLE_MECHANISM",
            "reason": "The available evidence does not justify a new executable economic hypothesis.",
        }
    return json.dumps({"status": "completed", "model": p.APPROVED_MODEL,
                       "usage": {"input_tokens": 2500, "output_tokens": 400},
                       "output": [{"type": "message", "content": [
                           {"type": "output_text", "text": json.dumps(decision)}
                       ]}]}).encode()


class ReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.old = self.root / "p2b" / old.ID
        self.old.mkdir(parents=True)
        self.old_adapter = self.old / "p2a-adapter"
        self.old_adapter.mkdir()
        self.old.joinpath("attempt.claim").write_text("irreversible", encoding="utf-8")
        result = {"experiments_executed": 0, "id": old.ID,
                  "model_calls": 1, "network_requests": 4,
                  "reason": "HTTP Error 400: Bad Request", "reason_type": "HTTPError",
                  "status": "STOP_MODEL_OR_PROVENANCE_ERROR"}
        raw = old.encoded(result)
        self.assertEqual(old.sha(raw), p.PREVIOUS_RESULT_HASH)
        self.old.joinpath(p.PREVIOUS_RESULT_NAME).write_bytes(raw)
        selected = [{"doi": DOI, "title": TITLE, "published": "2025-06-03"}]
        self.old.joinpath("source-selection.json").write_bytes(old.encoded(selected))
        search = {"status": "ok", "message": {"items": [
            {"DOI": DOI, "title": [TITLE], "published": {"date-parts": [[2025, 6, 3]]}},
        ]}}
        self.old.joinpath("search-crossref.json").write_bytes(old.encoded(search))
        provider_data = old.encoded({"status": "ok", "message": {
            "DOI": DOI, "title": [TITLE], "abstract": ABSTRACT}})
        rel = "agent/evidence_enrichment/raw/raw-example-crossref.json"
        (self.old_adapter / rel).parent.mkdir(parents=True)
        (self.old_adapter / rel).write_bytes(provider_data)
        entries = [{"doi": DOI, "title": TITLE, "abstract_status": "AVAILABLE",
                    "abstract_sha256": old.sha(ABSTRACT.encode()),
                    "provenance": [{"provider": "Crossref", "raw_path": rel,
                                    "raw_sha256": old.sha(provider_data),
                                    "has_abstract": True, "doi_verified": True,
                                    "observed_at": "2026-11-21T03:01:00+00:00"}]}]
        report = {"version": "P2B_EVIDENCE_ADAPTER_V1", "entries": entries,
                  "experiments_executed": 0, "trading_allowed": False}
        report_raw = old.encoded(report)
        self.report_rel = "agent/reports/abstract-evidence-v1-" + old.sha(report_raw)[:12] + ".json"
        (self.old_adapter / self.report_rel).parent.mkdir(parents=True)
        (self.old_adapter / self.report_rel).write_bytes(report_raw)
        sources = [{"doi": DOI, "title": TITLE, "published": "2025-06-03",
                    "abstract": ABSTRACT, "source_provider": "Crossref",
                    "source_sha256": old.sha(provider_data)}]
        wrong_request = old.prepare_request(sources, {"model": p.PREVIOUS_MODEL, "custom": True})
        self.old.joinpath("model-request.json").write_bytes(wrong_request)
        self.env = {"BASE_URL": "https://gateway.example.test:9443/v1",
                    "LLM_API_STYLE": "responses",
                    "LLM_MODEL": p.APPROVED_MODEL,
                    "LLM_API_KEY": "mock_only_not_real_key"}
        self.envpatch = patch.dict(os.environ, self.env, clear=True)
        self.envpatch.start()
        self.addCleanup(self.envpatch.stop)
        self.calls = []
        self.approval_path = self.root / "p2b" / p.ID / "owner-approval.json"
        self.approval_path.parent.mkdir(parents=True)
        self.approve()
        self.original_snapshot = {str(path.relative_to(self.old)): old.sha(path.read_bytes())
                                  for path in self.old.rglob("*") if path.is_file()}

    def approve(self):
        a = p.approval_template(self.root)
        a.update({"approved": True,
                  "approval_reference": "owner-explicit-approved-P2B-002-2026-11-21",
                  "approved_at_utc": "2026-11-21T03:00:00Z",
                  "pricing_verified_at_utc": "2026-11-21T03:00:00Z",
                  "pricing_reference": "Owner-verified gateway GPT-6.2 Sol Standard price parity"})
        self.approval_path.write_bytes(old.encoded(a))

    def model(self, body):
        self.calls.append(body)
        req = json.loads(body)
        self.assertEqual(req["model"], "chatgpt/gpt-6.2-sol")
        self.assertEqual(req["input"][0]["role"], "user")
        self.assertEqual(json.loads(req["input"][0]["content"][0]["text"])["experiment_id"], p.ID)
        self.assertEqual(json.loads(req["input"][0]["content"][0]["text"])["evidence"][0]["doi"], DOI)
        self.assertEqual(req["tools"], [])
        self.assertLessEqual(len(body), old.MAX_INPUT_BYTES)
        return response()

    def assert_original_unchanged(self):
        new_snapshot = {str(path.relative_to(self.old)): old.sha(path.read_bytes())
                        for path in self.old.rglob("*") if path.is_file()}
        self.assertEqual(self.original_snapshot, new_snapshot)

    def test_offline_template_pins_immutable_evidence_and_correct_alias(self):
        template = p.approval_template(self.root)
        self.assertFalse(template["approved"])
        self.assertEqual(template["model_id"], "chatgpt/gpt-6.2-sol")
        self.assertEqual(template["max_source_requests"], 0)
        self.assertEqual(template["max_model_calls"], 1)
        self.assertEqual(template["max_spend_usd"], 10)
        self.assertEqual(template["replay_evidence"]["verified_dois"], [DOI])
        self.assertEqual(template["replay_evidence"]["previous_result_sha256"], p.PREVIOUS_RESULT_HASH)
        self.assert_original_unchanged()

    def test_replay_once_abstain_zero_evidence_network_and_no_retry(self):
        result = p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(result["status"], "NO_NEW_FEASIBLE_MECHANISM")
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["experiments_executed"], 0)
        self.assertEqual(len(self.calls), 1)
        self.assert_original_unchanged()
        self.assertTrue((self.root / "p2b" / p.ID / "model-response.json").is_file())
        with self.assertRaises(FileExistsError):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(len(self.calls), 1)

    def test_replay_p2a_verified_in_independent_new_adapter(self):
        decision = {"decision": "PROPOSE", "proposal": {"doi": DOI},
                    "reason_code": None, "reason": None}
        def invoke(body):
            self.calls.append(body)
            return response(decision)
        def review(adapter, report, proposed):
            data = gate.verified_evidence(adapter, report, DOI)
            self.assertEqual(data["abstract"], ABSTRACT)
            self.assertEqual(json.loads((adapter / proposed).read_text())["doi"], DOI)
            self.assertTrue(str(adapter).endswith("P2B_DISCOVERY_PILOT_002/p2a-adapter"))
            return {"status": "NEEDS_HUMAN_PROTOCOL_AND_DATA_REVIEW"}
        with patch.object(p.gate, "review", side_effect=review):
            output = p.run(self.root, now=NOW, invoke_model=invoke)
        self.assertEqual(output["status"], "AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW")
        self.assert_original_unchanged()

    def test_failure_consumes_attempt_and_does_not_retry(self):
        def broken(_):
            self.calls.append("error")
            raise OSError("Gateway unavailable")
        result = p.run(self.root, now=NOW, invoke_model=broken)
        self.assertEqual(result["status"], "STOP_MODEL_OR_PROVENANCE_ERROR")
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["model_calls"], 1)
        self.assert_original_unchanged()
        with self.assertRaises(FileExistsError):
            p.run(self.root, now=NOW, invoke_model=broken)
        self.assertEqual(len(self.calls), 1)

    def test_absent_separate_approval_no_attempt_or_model(self):
        self.approval_path.unlink()
        with self.assertRaisesRegex(ValueError, "approval"):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertFalse((self.approval_path.parent / "attempt.claim").exists())
        self.assertEqual(self.calls, [])

    def test_env_model_drift_prevents_run(self):
        with patch.dict(os.environ, {"LLM_MODEL": "chatgpt/gpt6.2-sol"}):
            with self.assertRaisesRegex(ValueError, "exact approved"):
                p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(self.calls, [])

    def test_original_source_byte_tamper_fails_before_model(self):
        source_file = self.old_adapter / "agent/evidence_enrichment/raw/raw-example-crossref.json"
        source_file.write_bytes(b'{"status":"ok","message":{}}')
        with self.assertRaisesRegex(ValueError, "digest mismatch|DOI|SHA256"):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.approval_path.parent / "attempt.claim").exists())

    def test_original_model_request_tamper_fails_before_model(self):
        oldreq = self.old / "model-request.json"
        data = json.loads(oldreq.read_bytes())
        data["model"] = p.APPROVED_MODEL
        oldreq.write_bytes(old.encoded(data))
        with self.assertRaisesRegex(ValueError, "not reproducible"):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(self.calls, [])

    def test_original_search_select_tamper_fails_before_model(self):
        src = self.old / "search-crossref.json"
        src.write_bytes(old.encoded({"status": "ok", "message": {"items": []}}))
        with self.assertRaisesRegex(ValueError, "mismatches original"):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(self.calls, [])

    def test_original_result_tamper_fails_before_model(self):
        src = self.old / p.PREVIOUS_RESULT_NAME
        src.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(self.calls, [])

    def test_old_approval_not_authorization_for_002(self):
        old_authorization = json.loads(self.approval_path.read_text())
        old_authorization["experiment_id"] = old.ID
        self.approval_path.write_bytes(old.encoded(old_authorization))
        with self.assertRaisesRegex(ValueError, "changed"):
            p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(self.calls, [])

    def test_paused_is_no_model_request(self):
        (self.root / "PAUSED").touch()
        result = p.run(self.root, now=NOW, invoke_model=self.model)
        self.assertEqual(result["status"], "PAUSED")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
