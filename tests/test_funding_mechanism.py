"""Synthetic-only tests: no Binance downloads, API use, trading, or holdout."""
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from random import Random
import tempfile
import unittest
from unittest.mock import patch

from quant_research_agent import funding_mechanism as m


def fixture(root: Path, *, effect=True) -> str:
    data = root / 'data'
    fund = root / 'funding'
    data.mkdir(parents=True)
    fund.mkdir(parents=True)
    start = date(2020, 1, 1)
    rng = Random(123)
    n = m.EXPECTED_DAYS
    funding = {}
    for i in range(n):
        day = start + timedelta(days=i)
        # 9.1% calibration extremes, 14.3% evaluation extremes.
        funding[day] = 0.002 if (i % (11 if day.year <= 2021 else 7)) == 0 else 0.0001
    funding_file = fund / 'BTCUSDT-funding-2020-2023.v2.csv'
    with funding_file.open('w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(m.FUNDING_SCHEMA)
        for i in range(n):
            day = start + timedelta(days=i)
            stamp = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
            for h in (0, 8, 16):
                w.writerow((stamp + h * 3600000 + (47 if i % 3 == 0 else 0), 8, funding[day]))
    sha = hashlib.sha256(funding_file.read_bytes()).hexdigest()
    audit = {
        'protocol': m.AUDIT_PROTOCOL,
        'status': 'DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED',
        'issues': [],
        'observed_rows': m.EXPECTED_FUNDING_ROWS,
        'expected_settlements': m.EXPECTED_FUNDING_ROWS,
        'unique_nominal_settlement_slots': m.EXPECTED_FUNDING_ROWS,
        'range': {'from': '2020-01-01', 'through': '2023-12-31'},
        'canonical_csv_sha256': sha,
    }
    (fund / 'BTCUSDT-funding-2020-2023.audit.v2.json').write_text(json.dumps(audit))
    spot = data / 'BTCUSDT-1d.csv'
    px = 15000.0
    with spot.open('w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(m.SPOT_SCHEMA)
        for i in range(n):
            day = start + timedelta(days=i)
            prevday = day - timedelta(days=2)
            is_event = day.year >= 2022 and prevday in funding and funding[prevday] > 0.001
            if effect and is_event:
                ret = -0.065 + rng.gauss(0, 0.004)
            else:
                ret = rng.gauss(0.003, 0.009)
            new = px * math.exp(ret)
            w.writerow((str(day), px, max(px, new) * 1.01, min(px, new) * 0.99, new, 1.0))
            px = new
    return sha


class FundingMechanismTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sha = fixture(self.root)
        self.hash_patch = patch.object(m, 'EXPECTED_FUNDING_SHA', self.sha)
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def test_strong_negative_effect_passes_information_only(self):
        # Balanced observational strata, strong independent synthetic signal.
        rng = Random(77)
        rows = []
        for i in range(730):
            day = date(2022, 1, 1) + timedelta(days=i)
            event = i % 7 == 0
            target = (-.06 if event else .001) + rng.gauss(0, .006)
            rows.append({'day': day, 'stratum': 9*(day.year-2022)+i%9,
                         'event': event, 'target': target,
                         'downside': float(target <= -.02)})
        result = m.evaluate(rows)
        self.assertEqual(result['status'], 'PASS_INCREMENTAL_INFORMATION_ONLY', result['reasons'])
        self.assertTrue(result['metrics']['directional_pass'])
        self.assertGreaterEqual(result['sample']['event_days'], 40)
        self.assertGreaterEqual(result['sample']['event_14day_calendar_blocks'], 8)

    def test_end_to_end_stratum_overlap_failure_stops(self):
        result = m.run(self.root)
        self.assertEqual(result['status'], 'STOP_INSUFFICIENT_INCREMENTAL_INFORMATION')
        self.assertTrue(result['sample']['sparse_control_strata'])
        self.assertFalse(result['strategy_backtest_allowed'])
        self.assertFalse(result['holdout_evaluated'])
        self.assertEqual(result['evaluation']['days'], 730)

    def test_identical_rerun_is_idempotent_and_pre2024_only(self):
        first = m.run(self.root)
        spot = self.root / 'data' / 'BTCUSDT-1d.csv'
        with spot.open('a') as f:
            f.write('2024-01-01,NOT_A_NUMBER,INVALID,INVALID,INVALID,INVALID\n')
        second = m.run(self.root)
        self.assertEqual(first['data'], second['data'])
        self.assertEqual(first['metrics'], second['metrics'])

    def test_sha_provenance_mismatch_fails_closed(self):
        with patch.object(m, 'EXPECTED_FUNDING_SHA', '0' * 64):
            with self.assertRaisesRegex(m.MechanismError, 'data gate'):
                m.run(self.root)

    def test_malformed_settlement_offset_fails_without_changing_audit(self):
        funding = self.root / 'funding' / 'BTCUSDT-funding-2020-2023.v2.csv'
        lines = funding.read_text().splitlines()
        fields = lines[1].split(',')
        fields[0] = str(int(fields[0]) + 101)
        lines[1] = ','.join(fields)
        funding.write_text('\n'.join(lines) + '\n')
        # Even an incorrectly re-signed audit CSV cannot bypass timestamp validation.
        new_sha = hashlib.sha256(funding.read_bytes()).hexdigest()
        audit = self.root / 'funding' / 'BTCUSDT-funding-2020-2023.audit.v2.json'
        record = json.loads(audit.read_text())
        record['canonical_csv_sha256'] = new_sha
        audit.write_text(json.dumps(record))
        with patch.object(m, 'EXPECTED_FUNDING_SHA', new_sha):
            with self.assertRaisesRegex(m.MechanismError, 'outside the frozen'):
                m.run(self.root)

    def test_missing_price_date_fails_closed(self):
        spot = self.root / 'data' / 'BTCUSDT-1d.csv'
        lines = spot.read_text().splitlines()
        spot.write_text('\n'.join(lines[:100] + lines[101:]) + '\n')
        with self.assertRaisesRegex(m.MechanismError, 'Missing/duplicate'):
            m.run(self.root)

    def test_duplicate_funding_slot_fails_even_with_different_ms(self):
        funding = self.root / 'funding' / 'BTCUSDT-funding-2020-2023.v2.csv'
        lines = funding.read_text().splitlines()
        fields = lines[2].split(',')
        fields[0] = str(int(lines[1].split(',')[0]) + 1)
        lines[2] = ','.join(fields)
        funding.write_text('\n'.join(lines) + '\n')
        sha = hashlib.sha256(funding.read_bytes()).hexdigest()
        audit = self.root / 'funding' / 'BTCUSDT-funding-2020-2023.audit.v2.json'
        x = json.loads(audit.read_text())
        x['canonical_csv_sha256'] = sha
        audit.write_text(json.dumps(x))
        with patch.object(m, 'EXPECTED_FUNDING_SHA', sha):
            with self.assertRaisesRegex(m.MechanismError, 'Duplicate / unordered'):
                m.run(self.root)

    def test_signal_uses_t_minus_2_not_t_minus_1(self):
        funding, _ = m.load_verified_funding(
            self.root / 'funding' / 'BTCUSDT-funding-2020-2023.v2.csv',
            self.root / 'funding' / 'BTCUSDT-funding-2020-2023.audit.v2.json')
        closes, _ = m.load_spot_closes(self.root / 'data' / 'BTCUSDT-1d.csv')
        _, evaluation = m.build_observations(funding, closes)
        row = evaluation[0]
        self.assertEqual(row['day'], date(2022, 1, 1))
        self.assertAlmostEqual(row['funding'], funding[date(2021, 12, 30)])
        original = row['funding']
        funding[date(2021, 12, 31)] = 0.5
        _, still_same = m.build_observations(funding, closes)
        self.assertEqual(still_same[0]['funding'], original)
        funding[date(2021, 12, 30)] = 0.35
        _, now_changes = m.build_observations(funding, closes)
        self.assertEqual(now_changes[0]['funding'], 0.35)
        self.assertEqual(m.SIGNAL_LAG_DAYS, 2)

    def test_mutating_existing_report_rejected(self):
        result = m.run(self.root)
        output = Path(result['report'])
        output.write_text('{"tampered":true}\n')
        with self.assertRaisesRegex(m.MechanismError, 'refusing overwrite'):
            m.run(self.root)

    def test_null_effect_is_not_promoted_to_information(self):
        # Test statistic on null synthetic evaluation rows, no filesystem dependency.
        r = Random(777)
        rows = []
        for i in range(730):
            day = date(2022, 1, 1) + timedelta(days=i)
            target = r.gauss(0, .01)
            rows.append({'day':day, 'stratum':9*(day.year-2022)+i%9,
                         'event':i%7==0, 'target':target, 'downside':float(target<=-.02)})
        result = m.evaluate(rows)
        self.assertEqual(result['status'], 'STOP_INSUFFICIENT_INCREMENTAL_INFORMATION')

    def test_insufficient_event_support_stops_without_sweeping(self):
        rows=[]
        for i in range(730):
            day = date(2022,1,1)+timedelta(days=i)
            rows.append({'day':day,'stratum':9*(day.year-2022)+i%9,'event':i%50==0,
                         'target':-.08 if i%50==0 else 0.001,
                         'downside':1.0 if i%50==0 else 0.0})
        result=m.evaluate(rows)
        self.assertEqual(result['status'], 'STOP_INSUFFICIENT_INCREMENTAL_INFORMATION')
        self.assertIn('Fewer than 40', result['reasons'][0])

    def test_reject_events_confined_to_single_year(self):
        rows = []
        for i in range(730):
            day = date(2022, 1, 1) + timedelta(days=i)
            event = day.year == 2022 and i % 6 == 0
            target = -0.06 if event else 0.002
            rows.append({'day': day, 'stratum': 9*(day.year-2022)+i%9,
                         'event': event, 'target': target,
                         'downside': float(target <= -0.02)})
        result = m.evaluate(rows)
        self.assertEqual(result['status'], 'STOP_INSUFFICIENT_INCREMENTAL_INFORMATION')
        self.assertTrue(any('either evaluation year' in x for x in result['reasons']))

    def test_funding_threshold_calibration_ignores_evaluation_values(self):
        funding, _ = m.load_verified_funding(
            self.root / 'funding' / 'BTCUSDT-funding-2020-2023.v2.csv',
            self.root / 'funding' / 'BTCUSDT-funding-2020-2023.audit.v2.json')
        closes, _ = m.load_spot_closes(self.root / 'data' / 'BTCUSDT-1d.csv')
        cal, _ = m.build_observations(funding, closes)
        base = m.freeze_thresholds(funding, cal)
        funding[date(2023, 7, 1)] = .5
        updated = m.freeze_thresholds(funding, cal)
        self.assertEqual(base, updated)

    def test_no_backtest_import_and_frozen_scope(self):
        import inspect
        source=inspect.getsource(m)
        self.assertNotIn('backtest.simulate',source)
        self.assertNotIn('2025-',source)
        self.assertEqual(m.LAST, date(2023,12,31))


if __name__ == '__main__':
    unittest.main()
