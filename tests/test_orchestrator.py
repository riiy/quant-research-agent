"""Offline controller tests. No market data, APIs, shell or live provider calls."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from quant_research_agent import orchestrator as a

UTC = timezone.utc
START = datetime(2026, 11, 17, 0, 0, tzinfo=UTC)


def policy(tasks=None):
    return {
        "schema_version": 1, "research_only": True,
        **{key: False for key in a.BLOCKED_POLICY_FLAGS},
        "max_attempts": 2,
        "archived_mechanisms": ["trend_persistence", "volatility_exposure", "attention_demand", "derivatives_leverage_pressure"],
        "tasks": tasks if tasks is not None else [{"id": "catalog-screen-a", "kind": "screen_curated"}],
    }


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "runtime"
        self.config = self.dir / "policy.json"
        self.write_policy(policy())

    def write_policy(self, p):
        self.config.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")

    def do_tick(self, now=START):
        return a.tick(self.root, self.config, now=now)

    def test_one_screen_scans_and_persists(self):
        result = self.do_tick()
        self.assertEqual(result["status"], "NO_NEW_FEASIBLE_MECHANISMS")
        self.assertEqual(result["result"]["eligible_mechanisms"], [])
        self.assertFalse(result["result"]["new_public_research_retrieved"])
        db = a.status(self.root)
        self.assertEqual(db["tasks"][0]["status"], "NO_NEW_FEASIBLE_MECHANISMS")
        self.assertEqual(db["tasks"][0]["attempts"], 1)

    def test_duplicate_ticks_are_idle_not_duplicate_api_calls(self):
        self.do_tick()
        self.assertEqual(self.do_tick(START + timedelta(minutes=3))["status"], "IDLE_NO_APPROVED_TASKS")
        self.assertEqual(len(a.status(self.root)["tasks"]), 1)

    def test_no_tasks_is_valid_idle(self):
        self.write_policy(policy([]))
        self.assertEqual(self.do_tick()["status"], "IDLE_NO_APPROVED_TASKS")
        self.assertEqual(a.status(self.root)["tasks"], [])

    def test_policy_rejects_every_privileged_capability(self):
        for flag in a.BLOCKED_POLICY_FLAGS:
            p = policy()
            p[flag] = True
            self.write_policy(p)
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "research-only"):
                self.do_tick()
        self.assertEqual(a.status(self.root)["tasks"], [])

    def test_policy_does_not_unarchive_prior_studies(self):
        p = policy()
        p["archived_mechanisms"].remove("volatility_exposure")
        self.write_policy(p)
        with self.assertRaisesRegex(ValueError, "cannot be unarchived"):
            self.do_tick()

    def test_policy_rejects_arbitrary_code_url_and_holdout(self):
        for kind in ["python", "run_shell", "strategy_backtest", "finalize_holdout", "fetch_url"]:
            self.write_policy(policy([{"id": "unsafe-task-a", "kind": kind}]))
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "not allowlisted"):
                self.do_tick()

    def test_paused_is_safe_and_does_not_register_tasks(self):
        self.root.mkdir(parents=True)
        (self.root / "PAUSED").write_text("pause\n")
        self.assertEqual(self.do_tick()["status"], "PAUSED")
        self.assertEqual(a.status(self.root)["tasks"], [])
        self.assertEqual(a.status(self.root)["last_heartbeat"]["outcome"], "PAUSED")

    def test_changed_approval_task_id_must_be_new(self):
        self.do_tick()
        p = policy()
        p["archived_mechanisms"].append("liquidity_reversal")
        self.write_policy(p)
        with self.assertRaisesRegex(ValueError, "POLICY_DRIFT_BLOCKED"):
            self.do_tick(START + timedelta(days=1))
        self.assertEqual(a.status(self.root)["tasks"][0]["attempts"], 1)

    def test_adding_new_approved_task_to_queue(self):
        self.do_tick()
        p = policy([{"id": "catalog-screen-a", "kind": "screen_curated"},
                    {"id": "catalog-screen-b", "kind": "screen_curated"}])
        self.write_policy(p)
        second = self.do_tick(START + timedelta(hours=1))
        self.assertEqual(second["task_id"], "catalog-screen-b")
        self.assertEqual(len(a.status(self.root)["tasks"]), 2)

    def make_report_task(self, *, content=None, sha=None):
        content = content or {
            "research_id": "BTC_ATTENTION_DEMAND_v1", "status": "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
            "strategy_backtest_allowed": False, "trading_allowed": False, "holdout_evaluated": False,
        }
        raw = (json.dumps(content, sort_keys=True) + "\n").encode()
        artifact = "attention/BTCUSDT-attention-phase1-retrospective-kill-v1.json"
        path = self.root / artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        task = {"id": "verify-attention-a", "kind": "verify_archived_report", "artifact": artifact,
                "research_id": "BTC_ATTENTION_DEMAND_v1", "expected_status": "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
                "sha256": sha or hashlib.sha256(raw).hexdigest()}
        self.write_policy(policy([task]))
        return path, task

    def test_verified_report_requires_frozen_sha_and_fields(self):
        self.make_report_task()
        result = self.do_tick()
        self.assertEqual(result["status"], "ARCHIVED_REPORT_VERIFIED")
        self.assertIn("not recomputed", result["result"]["scope"])
        self.assertEqual(result["result"]["reported_status"], "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION")

    def test_report_digest_failure_no_result_overwrite(self):
        file, task = self.make_report_task()
        file.write_text("{}")
        result = self.do_tick()
        self.assertEqual(result["status"], "FAILED_REVIEW_REQUIRED")
        self.assertIn("mismatch", result["result"]["reason"])
        self.assertEqual(self.do_tick(START + timedelta(days=1))["status"], "IDLE_NO_APPROVED_TASKS")

    def test_report_safety_flag_invalid(self):
        self.make_report_task(content={"research_id": "BTC_ATTENTION_DEMAND_v1",
            "status": "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION", "strategy_backtest_allowed": True,
            "trading_allowed": False, "holdout_evaluated": False})
        self.assertEqual(self.do_tick()["status"], "FAILED_REVIEW_REQUIRED")

    def test_missing_report_blocks_with_no_file_creation(self):
        file, task = self.make_report_task()
        file.unlink()
        self.assertEqual(self.do_tick()["status"], "BLOCKED_MISSING_INPUT")
        self.assertFalse(file.exists())

    def test_only_approved_report_paths_and_ids(self):
        p = policy([{"id": "steal-report-a", "kind": "verify_archived_report", "artifact": "../../2025.csv",
                     "research_id": "BTC_ATTENTION_DEMAND_v1", "expected_status": "STOP_INSUFFICIENT_INCREMENTAL_INFORMATION",
                     "sha256": "a" * 64}])
        self.write_policy(p)
        with self.assertRaisesRegex(ValueError, "not approved"):
            self.do_tick()
        p["tasks"][0]["artifact"] = "attention/BTCUSDT-attention-phase1-retrospective-kill-v1.json"
        p["tasks"][0]["research_id"] = "BTC_PERP_FUNDING_PRESSURE_v1"
        self.write_policy(p)
        with self.assertRaisesRegex(ValueError, "Only already-archived"):
            self.do_tick()

    def test_stale_claim_replayed_once_with_bounded_attempts(self):
        p = policy([{"id": "catalog-screen-a", "kind": "screen_curated"}])
        self.write_policy(p)
        task = a._claim(self.root, p, START)
        self.assertEqual(task["id"], "catalog-screen-a")
        self.assertEqual(a.status(self.root)["tasks"][0]["status"], "RUNNING")
        self.assertEqual(self.do_tick(START + timedelta(seconds=100))["status"], "IDLE_NO_APPROVED_TASKS")
        got = self.do_tick(START + timedelta(seconds=a.LEASE_SECONDS+1))
        self.assertEqual(got["status"], "NO_NEW_FEASIBLE_MECHANISMS")
        self.assertEqual(a.status(self.root)["tasks"][0]["attempts"], 2)
        self.assertEqual(self.do_tick(START + timedelta(hours=1))["status"], "IDLE_NO_APPROVED_TASKS")

    def test_second_interrupted_claim_stops_needs_review(self):
        p = policy()
        a._claim(self.root,p,START)
        a._claim(self.root,p,START+timedelta(seconds=a.LEASE_SECONDS+1))
        result = self.do_tick(START + timedelta(seconds=2*a.LEASE_SECONDS+2))
        self.assertEqual(result["status"], "IDLE_NO_APPROVED_TASKS")
        self.assertEqual(a.status(self.root)["tasks"][0]["status"], "INTERRUPTED_REVIEW_REQUIRED")

    def test_seven_day_heartbeat_gate_does_not_claim_live_uptime(self):
        self.do_tick(START)
        for day in range(1, 7):
            self.do_tick(START + timedelta(days=day))
        score = a.acceptance(self.root, now=START+timedelta(days=6))
        self.assertEqual(score["status"], "PASS_UNATTENDED_CONTROLLER_GATE_ONLY")
        self.assertEqual(score["observed_distinct_utc_days"], 7)
        self.assertIn("not host uptime", score["note"])
        short = a.acceptance(self.root, now=START+timedelta(days=5))
        self.assertEqual(short["status"], "NOT_YET")

    def test_seven_day_controller_gate_fails_without_completions(self):
        self.write_policy(policy([]))
        for day in range(7):
            self.do_tick(START + timedelta(days=day))
        self.assertEqual(a.acceptance(self.root, now=START+timedelta(days=6))["status"], "NOT_YET")

    def test_curated_eligible_requires_human_approval(self):
        # The only currently in-scope mechanisms are archived/blocked; a fake
        # newly reviewed registry entry checks the safety of future expansion.
        import unittest.mock
        new_registry = {"new_external_demand": {
            "priority": 0, "sources": [], "required_data": [],
            "execution_status": "RULE_NOT_IMPLEMENTED", "evidence_points": 1}}
        with unittest.mock.patch.dict(a.MECHANISMS, new_registry):
            with unittest.mock.patch.object(a, "mechanism_screen", side_effect=lambda k, seen:
                    {"status": "ELIGIBLE_FOR_IDEA_ONLY", "reasons": []} if k == "new_external_demand"
                    else {"status": "BLOCKED", "reasons": ["Archived"]}):
                outcome = self.do_tick()
        self.assertEqual(outcome["status"], "AWAITING_HUMAN_PROTOCOL_APPROVAL")
        self.assertEqual(outcome["result"]["eligible_mechanisms"], ["new_external_demand"])


if __name__ == "__main__":
    unittest.main()
