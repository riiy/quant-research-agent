"""Contract checks for the bounded, 2018-2023-only volatility mechanism screen."""
from __future__ import annotations

import csv
from contextlib import closing
from datetime import date, timedelta
import json
import math
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from quant_research_agent.idea_funnel import main as ideas_main
from quant_research_agent.volatility_kill_test import (
    FIRST, LAST, CAL_END, EVAL_START, LOOKBACK, BOOTSTRAPS,
    build_observations, evaluate, load_development_closes, load_prior_idea, run,
)


def make_csv(path: Path, *, bad_future: bool = False):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "open", "high", "low", "close", "volume"])
        day, price, i = FIRST, 100, 0
        while day <= LAST:
            # All regimes have strictly positive prices; development path is synthetic.
            amplitude = 0.004 if day.year < 2021 else (0.03 if (i // 90) % 2 == 0 else 0.005)
            step = amplitude * math.sin(i * 0.83) + 0.0004
            price *= math.exp(step)
            writer.writerow([day, price, price * 1.01, price * 0.99, price, 1])
            i += 1
            day += timedelta(days=1)
        if bad_future:
            writer.writerow(["2024-01-01", "not-a-price", "not-a-price", "0", "0", "0"])


def make_idea(root: Path, *, idea_id: str = "4b7cb9282852"):
    raw = {
        "title": "Volatility exposure as a mechanism-only hypothesis",
        "mechanism_id": "volatility_exposure",
        "signal_proposal": "30 completed daily returns, with the median calibrated in an earlier sample.",
        "source_ids": ["moreira_muir2017"],
    }
    with closing(sqlite3.connect(root / "ideas.sqlite3")) as c:
        c.execute("CREATE TABLE ideas (idea_id TEXT PRIMARY KEY, status TEXT, mechanism_id TEXT, idea_json TEXT)")
        c.execute("INSERT INTO ideas VALUES (?,?,?,?)", (idea_id,
            "AWAITING_RULE_DESIGN_NOT_BACKTESTED", "volatility_exposure", json.dumps(raw)))
        c.commit()
    return idea_id


class MechanismTests(unittest.TestCase):
    def test_ignores_2024_suffix_and_freezes_data(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data.csv"
            make_csv(data, bad_future=True)
            values, meta = load_development_closes(data)
            self.assertEqual(values[0][0], FIRST)
            self.assertEqual(values[-1][0], LAST)
            self.assertEqual(len(values), 2191)
            self.assertEqual(meta["last"], "2023-12-31")
            self.assertEqual(len(meta["development_ohlcv_sha256"]), 64)

    def test_lagged_indicator_and_split_are_fixed(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "synthetic.csv"
            make_csv(p)
            values, _ = load_development_closes(p)
            cutoff, observations = build_observations(values)
            self.assertGreater(cutoff, 0)
            self.assertEqual(len(observations), 1095)
            # A jump on an evaluation day must not change that same day's label.
            k = next(i for i, x in enumerate(values) if x[0] == EVAL_START)
            changed = values.copy()
            changed[k] = (values[k][0], values[k][1] * 15)
            cutoff2, obs2 = build_observations(changed)
            self.assertEqual(cutoff2, cutoff)
            self.assertEqual(obs2[0][0], observations[0][0])
            self.assertNotEqual(obs2[0][1], observations[0][1])

    def test_provenance_and_immutable_output(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            make_csv(root / "data" / "BTCUSDT-1d.csv")
            idea_id = make_idea(root)
            first = run(root, idea_id)
            self.assertEqual(first["evaluation"]["dates"], "2021-01-01..2023-12-31")
            self.assertEqual(first["calibration"]["lagged_vol_window"], LOOKBACK)
            self.assertEqual(first["gates"]["block_bootstrap_reps"], BOOTSTRAPS)
            second = run(root, idea_id)
            self.assertEqual(first, second)
            report = Path(first["report"])
            self.assertTrue(report.exists())
            # Report must refuse silent rewriting on a changed value.
            report.write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "will not overwrite"):
                run(root, idea_id)

    def test_strong_synthetic_regime_can_pass_mechanism_gate(self):
        obs = []
        for i in range(600):
            if i % 2:
                obs.append((True, 0.025 if i % 4 == 1 else -0.025))
            else:
                obs.append((False, 0.003 if i % 4 == 0 else -0.002))
        result = evaluate(obs)
        self.assertEqual(result["status"], "PASS_MECHANISM_GATE_ONLY")
        self.assertGreater(result["metrics"]["risk_ratio_block_bootstrap_lower_95_one_sided"], 1)

    def test_command_uses_existing_idea_and_emits_frozen_report(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            make_csv(root / "data" / "BTCUSDT-1d.csv", bad_future=True)
            idea_id = make_idea(root)
            out = StringIO()
            with redirect_stdout(out):
                code = ideas_main(["--home", str(root), "kill-test", "--idea-id", idea_id])
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["idea_id"], idea_id)
            self.assertEqual(payload["data"]["last"], "2023-12-31")
            self.assertTrue(Path(payload["report"]).exists())
            self.assertIn(payload["status"], (
                "PASS_MECHANISM_GATE_ONLY", "STOP_INSUFFICIENT_MECHANISM_EVIDENCE"))

    def test_reject_unregistered_idea(self):
        with TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "database missing"):
                load_prior_idea(Path(td), "4b7cb9282852")

    def test_reject_low_evidence_and_require_nontrivial_regimes(self):
        # Equal risks with small regime means do not pass, even with many samples.
        obs = [(i % 2 == 0, 0.002 * (-1 if i % 4 < 2 else 1)) for i in range(400)]
        result = evaluate(obs)
        self.assertEqual(result["status"], "STOP_INSUFFICIENT_MECHANISM_EVIDENCE")
        self.assertTrue(any("20%" in r for r in result["reasons"]))
        result = evaluate([(True, 0.01)] * 390 + [(False, 0.005)] * 10)
        self.assertTrue(any("100" in r for r in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
