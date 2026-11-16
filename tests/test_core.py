from __future__ import annotations

import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_research_agent.discovery import discover
from quant_research_agent.backtest import simulate, signal
from quant_research_agent.cli import finalize, main, run_once
from quant_research_agent.data import Bar, load_csv, parse_row, parse_timestamp, prefix_hash, verify_bars, sha256_file
from quant_research_agent.models import Candidate, seed_candidate
from quant_research_agent.storage import Store


def make_bars(start=date(2018, 1, 1), end=date(2025, 12, 31)):
    result, day, i = [], start, 0
    while day <= end:
        # Smooth trends separated by lower periods; no claim of market realism.
        price = 5000.0 * (1.0007 ** i) * (1 + 0.03 * __import__('math').sin(i / 25))
        result.append(Bar(day, price, price * 1.01, price * .99, price, 100))
        day += timedelta(days=1)
        i += 1
    return result


def write_csv(path, bars):
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['day','open','high','low','close','volume'])
        for b in bars:
            w.writerow([b.day, b.open, b.high, b.low, b.close, b.volume])


class DiscoveryContractTests(unittest.TestCase):
    def test_api_discovery_sends_responses_input_as_message_list(self):
        from io import BytesIO
        expected = seed_candidate().as_dict()
        payload = {
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(expected)}
            ]}],
            "usage": {"input_tokens": 12, "output_tokens": 34},
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-key",
                                      "QUANT_MODEL": "test-model"}):
            with patch("quant_research_agent.discovery.request.urlopen",
                       return_value=BytesIO(json.dumps(payload).encode())) as mocked:
                candidate, meta = discover("api")

        request_obj = mocked.call_args.args[0]
        body = json.loads(request_obj.data)
        self.assertIsInstance(body["input"], list)
        self.assertEqual(body["input"][0]["role"], "user")
        self.assertEqual(body["input"][0]["content"][0]["type"], "input_text")
        self.assertIn("Select one hypothesis", body["input"][0]["content"][0]["text"])
        self.assertIn("EXACTLY these five top-level keys", body["input"][0]["content"][0]["text"])
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertEqual(candidate.as_dict(), expected)
        self.assertEqual(meta["usage"], payload["usage"])


    def test_candidate_envelope_is_accepted_only_when_unambiguous(self):
        from io import BytesIO
        expected = seed_candidate().as_dict()
        wrapped = {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps({"candidate": expected})}
        ]}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}):
            with patch("quant_research_agent.discovery.request.urlopen",
                       return_value=BytesIO(json.dumps(wrapped).encode())):
                candidate, meta = discover("api")
        self.assertEqual(candidate.as_dict(), expected)
        self.assertTrue(meta["response_envelope_unwrapped"])

    def test_gateway_schema_mismatch_shows_key_names_not_response_values(self):
        from io import BytesIO
        malformed = {
            "title": "Unique private hypothesis details",
            "family": "momentum", "params": {"lookback": 180},
            "source_ids": ["moskowitz2012"], "commentary": "SECRET RESPONSE VALUE"
        }
        payload = {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps(malformed)}
        ]}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-key"}):
            with patch("quant_research_agent.discovery.request.urlopen",
                       return_value=BytesIO(json.dumps(payload).encode())):
                with self.assertRaisesRegex(ValueError, "missing=\\['rationale'\\]") as caught:
                    discover("api")
        message = str(caught.exception)
        self.assertIn("unexpected=['commentary']", message)
        self.assertNotIn("SECRET RESPONSE VALUE", message)
        self.assertNotIn("Unique private hypothesis details", message)

    def test_unexpected_wrapper_extra_field_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unexpected="):
            Candidate.from_dict({"candidate": seed_candidate().as_dict(),
                                 "explanation": "not allowed"})

class CandidateTests(unittest.TestCase):
    def test_reject_untrusted_code_or_parameters(self):
        c = seed_candidate().as_dict()
        c['params'] = {'lookback': 180, 'code': '__import__("os")'}
        with self.assertRaises(ValueError):
            Candidate.from_dict(c)
        c = seed_candidate().as_dict()
        c['source_ids'] = ['fake-paper']
        with self.assertRaises(ValueError):
            Candidate.from_dict(c)

    def test_fingerprint_independent_of_wording(self):
        c = seed_candidate()
        alt = c.as_dict(); alt['title'] = 'A different momentum hypothesis'
        self.assertEqual(c.fingerprint, Candidate.from_dict(alt).fingerprint)


class DataTests(unittest.TestCase):
    def test_binance_milliseconds_and_microseconds(self):
        self.assertEqual(date(2024, 12, 31), parse_timestamp('1735603200000'))
        self.assertEqual(date(2025, 1, 1), parse_timestamp('1735689600000000'))
        b = parse_row(['1735689600000000', '10', '12', '9', '11', '100'])
        self.assertEqual(b.day, date(2025, 1, 1))
        self.assertEqual(b.close, 11)

    def test_missing_dates_rejected(self):
        b = make_bars(date(2024, 1, 1), date(2024, 1, 4))
        with self.assertRaisesRegex(ValueError, 'Missing'):
            verify_bars([b[0], b[2], b[3]])

    def test_prefix_unchanged_when_holdout_appended(self):
        b = make_bars()
        self.assertEqual(prefix_hash(b[:-365], date(2024, 12, 31)),
                         prefix_hash(b, date(2024, 12, 31)))

    def test_invalid_local_csv(self):
        with TemporaryDirectory() as t:
            f = Path(t) / 'bad.csv'
            f.write_text('day,open,high,low,close,volume\n2024-01-01,1,2,3,1,3\n')
            with self.assertRaises(ValueError):
                load_csv(f)


class ExecutionTests(unittest.TestCase):
    def test_no_lookahead_next_open(self):
        c = Candidate.from_dict({'title':'BTC short momentum for test only', 'rationale':'Check the next day open execution without future data', 'family':'momentum', 'params':{'lookback':60}, 'source_ids':['moskowitz2012']})
        bars = make_bars(date(2024,1,1), date(2024,4,1))
        first = bars[0].day
        # 60 close observations available only at the end of day 61.
        self.assertFalse(signal(c, [x.close for x in bars], 59))
        self.assertTrue(signal(c, [x.close for x in bars], 60))
        m = simulate(bars, c, first, bars[-1].day, fee=0.0, slippage=0.0)
        self.assertGreaterEqual(m.entries, 1)
        # The close at day 61 cannot be used at the open of the same day.
        shortened = simulate(bars[:61], c, first, bars[60].day, fee=0, slippage=0)
        self.assertEqual(shortened.entries, 0)

    def test_same_day_jump_does_not_create_instant_profit(self):
        bars = [Bar(date(2024,1,1)+timedelta(days=i), 100, 200, 90, (101 if i < 61 else 199), 100)
                for i in range(65)]
        c = seed_candidate()
        # Momentum 180 not enough history => no entry despite last-day spikes.
        r = simulate(bars, c, bars[0].day, bars[-1].day)
        self.assertEqual(r.entries, 0)
        self.assertAlmostEqual(r.total_return, 0)

    def test_fee_slippage_and_baseline_costs(self):
        bars = make_bars(date(2024,1,1), date(2024,12,31))
        c = seed_candidate()
        free = simulate(bars, c, bars[0].day, bars[-1].day, fee=0, slippage=0)
        paid = simulate(bars, c, bars[0].day, bars[-1].day, fee=.001, slippage=.0005)
        self.assertGreater(free.total_return, paid.total_return)
        self.assertGreater(free.buy_hold_return, paid.buy_hold_return)


class ArchiveTests(unittest.TestCase):
    def test_seed_closed_loop_and_no_fake_ai_claim(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            path = root / 'sample.csv'
            write_csv(path, make_bars())
            run_id = run_once(root, path, 'seed')
            store = Store(root)
            row = store.get(run_id)
            self.assertEqual(row['status'], 'DEMO_SEEDED_HYPOTHESIS')
            result = json.loads(row['result_json'])
            self.assertIn('validation_double_cost', result)
            self.assertNotIn('holdout', result)
            self.assertIn('Trading permission: **NONE**', Path(row['report_path']).read_text())
            self.assertEqual(run_once(root, path, 'seed'), run_id)
            self.assertEqual(len(store.list()), 1)
            with self.assertRaisesRegex(ValueError, 'Not eligible'):
                finalize(root, path, run_id)
            self.assertEqual(main(['--home', str(root), 'status']), 0)

    def test_pause_blocks_new_experiments(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            Store(root).set_paused(True)
            with self.assertRaisesRegex(RuntimeError, 'paused'):
                run_once(root, root / 'absent.csv', 'seed')

    def test_api_monthly_quota(self):
        with TemporaryDirectory() as t:
            store = Store(Path(t))
            store.reserve_api_call('test', 1)
            with self.assertRaisesRegex(RuntimeError, 'limit reached'):
                store.reserve_api_call('test', 1)


if __name__ == '__main__':
    unittest.main()

class FinalHoldoutTests(unittest.TestCase):
    def test_holdout_locked_and_one_time(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            path = root / 'dataset.csv'
            bars = make_bars()
            write_csv(path, bars)
            manifest = {'source': 'binance-public-data-spot-monthly',
                        'rows': len(bars), 'csv_sha256': sha256_file(path)}
            path.with_suffix('.manifest.json').write_text(json.dumps(manifest))
            store = Store(root)
            c = seed_candidate()
            meta = {'discovery': {'mode':'api','is_ai_discovery':True},
                    'data': {'pre_holdout_prefix_sha256':prefix_hash(bars, date(2024,12,31)),
                             'source':'binance-public-data-spot-monthly', 'sha256': sha256_file(path)}}
            out = root/'reports'/'fake.md'
            rid = store.save(c.fingerprint, c.as_dict(), meta, {'reasons': []}, 'PENDING_SEALED_HOLDOUT', out)
            finalize(root, path, rid)
            row = store.get(rid)
            self.assertEqual(row['holdout_evaluated'], 1)
            self.assertIn('holdout', json.loads(row['result_json']))
            with self.assertRaisesRegex(ValueError, 'Not eligible'):
                finalize(root, path, rid)

    def test_changed_training_history_blocks_final_test(self):
        with TemporaryDirectory() as t:
            root = Path(t); path = root/'dataset.csv'
            bars = make_bars(); write_csv(path, bars)
            path.with_suffix('.manifest.json').write_text(json.dumps({
                'source':'binance-public-data-spot-monthly','rows':len(bars), 'csv_sha256':sha256_file(path)}))
            c = seed_candidate()
            rid = Store(root).save(c.fingerprint, c.as_dict(), {
                'data':{'pre_holdout_prefix_sha256':'bad-hash'}, 'discovery':{'mode':'api','is_ai_discovery':True}
            }, {'reasons':[]}, 'PENDING_SEALED_HOLDOUT', root/'test.md')
            with self.assertRaisesRegex(ValueError, 'Pre-holdout data changed'):
                finalize(root, path, rid)
            self.assertEqual(Store(root).get(rid)['holdout_evaluated'], 0)
