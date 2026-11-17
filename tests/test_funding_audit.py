"""Offline, synthetic-data checks for frozen BTC funding archive audit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import hashlib
import json
import unittest
from unittest.mock import patch
import zipfile

from quant_research_agent.funding_audit import (
    EXPECTED_ROWS, MAX_POST_SETTLEMENT_DELAY_MS, FundingAuditError, SCHEMA, audit_rows, load_verified_archive,
    main, months, read_month, run_audit,
)


def stamp(day, hour):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc, hour=hour).timestamp() * 1000)


def rows_for_month(month):
    y, m = map(int, month.split('-'))
    first = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)
    rows = []
    current = first
    while current < end:
        for hour in (0, 8, 16):
            rows.append((int(current.replace(hour=hour).timestamp() * 1000), 8, '0.00010000'))
        current += timedelta(days=1)
    return rows


def zip_payload(month, rows=None, header=SCHEMA):
    rows = rows if rows is not None else rows_for_month(month)
    output = StringIO(newline='')
    w = csv.writer(output, lineterminator='\n')
    w.writerow(header)
    w.writerows(rows)
    buf = BytesIO()
    name = f'BTCUSDT-fundingRate-{month}.csv'
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, output.getvalue())
    return buf.getvalue()


def populate(root, mutation=None):
    cache = root/'funding'/'archive'
    cache.mkdir(parents=True)
    for month in months():
        rows = rows_for_month(month)
        if mutation is not None:
            rows = mutation(month, rows)
        data = zip_payload(month, rows)
        name = f'BTCUSDT-fundingRate-{month}.zip'
        (cache/name).write_bytes(data)
        (cache/(name + '.CHECKSUM')).write_text(f'{hashlib.sha256(data).hexdigest()}  {name}\n')


class AuditTests(unittest.TestCase):
    def test_full_2020_2023_period_passes_and_repeats_immutably(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            populate(root)
            first = run_audit(root, offline=True)
            self.assertEqual(first['status'], 'DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED')
            self.assertEqual(first['observed'], EXPECTED_ROWS)
            self.assertEqual(first['issues'], [])
            report = json.loads(Path(first['report']).read_text())
            self.assertEqual(report['yearly_counts'], {'2020':1098,'2021':1095,'2022':1095,'2023':1095})
            self.assertEqual(len(report['archives']), 48)
            self.assertNotIn('2024-01', Path(first['canonical_csv']).read_text())
            self.assertEqual(run_audit(root, offline=True), first)
            self.assertEqual(main(['--home', str(root), 'audit', '--offline']), 0)

    def test_missing_and_duplicate_stamps_fail_with_full_diagnostics(self):
        def mutated(month, rows):
            if month == '2021-02':
                return rows[1:] + [rows[-1]]
            return rows
        with TemporaryDirectory() as t:
            root = Path(t)
            populate(root, mutation=mutated)
            out = run_audit(root, offline=True)
            self.assertEqual(out['status'], 'STOP_DATA_AUDIT_FAILED')
            kinds = {i['issue'] for i in out['issues']}
            self.assertIn('DUPLICATE_SETTLEMENT_TIMES', kinds)
            self.assertIn('MISSING_EXPECTED_SETTLEMENTS', kinds)
            self.assertFalse((root/'funding'/'BTCUSDT-funding-2020-2023.v2.csv').exists())
            self.assertEqual(main(['--home', str(root), 'audit', '--offline']), 2)

    def test_realistic_positive_jitter_passes_without_rewriting_raw_stamps(self):
        def jitter(_month, rows):
            # Deterministic offsets including the largest observed real-data offset.
            pattern = (0, 1, 2, 7, 15, 32, 47)
            return [(stamp + pattern[i % len(pattern)], interval, rate)
                    for i, (stamp, interval, rate) in enumerate(rows)]
        with TemporaryDirectory() as t:
            root = Path(t)
            populate(root, mutation=jitter)
            # Keep an original v1 failed report: new version cannot overwrite it.
            legacy = root/'funding'/'BTCUSDT-funding-2020-2023.audit.json'
            legacy.write_text('original v1 failure report\n', encoding='utf-8')
            first = run_audit(root, offline=True)
            self.assertEqual(first['status'], 'DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED')
            self.assertEqual(first['issues'], [])
            report = json.loads(Path(first['report']).read_text())
            timing = report['timestamp_alignment']
            self.assertEqual(timing['maximum_offset_ms'], 47)
            self.assertEqual(timing['minimum_offset_ms'], 0)
            self.assertGreater(timing['nonzero_offset_rows'], 0)
            self.assertEqual(report['unique_nominal_settlement_slots'], EXPECTED_ROWS)
            self.assertEqual(report['protocol'], 'BTC_PERP_FUNDING_PRESSURE_v2_timestamp_jitter_audit_2020_2023')
            self.assertEqual(legacy.read_text(), 'original v1 failure report\n')
            self.assertIn('.audit.v2.json', first['report'])
            with Path(first['canonical_csv']).open(newline='') as f:
                records = list(csv.DictReader(f))
            original_first = rows_for_month('2020-01')
            self.assertEqual(int(records[1]['calc_time']), original_first[1][0] + 1)
            self.assertEqual(run_audit(root, offline=True), first)

    def test_positive_100ms_max_tolerance_and_101ms_rejected(self):
        rows = [row for month in months() for row in rows_for_month(month)]
        stamp, interval, rate = rows[42]
        rows[42] = (stamp + MAX_POST_SETTLEMENT_DELAY_MS, interval, rate)
        good, _ = audit_rows(rows, [])
        self.assertEqual(good['status'], 'DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED')
        rows[42] = (stamp + MAX_POST_SETTLEMENT_DELAY_MS + 1, interval, rate)
        bad, _ = audit_rows(rows, [])
        self.assertEqual(bad['status'], 'STOP_DATA_AUDIT_FAILED')
        self.assertIn('OFF_8H_UTC_GRID', [i['issue'] for i in bad['issues']])

    def test_negative_offset_and_distinct_times_same_slot_rejected(self):
        rows = [row for month in months() for row in rows_for_month(month)]
        stamp, interval, rate = rows[32]
        rows[32] = (stamp - 1, interval, rate)
        bad, _ = audit_rows(rows, [])
        self.assertIn('OFF_8H_UTC_GRID', [i['issue'] for i in bad['issues']])
        # Two raw events +1/+2ms to same nominal slot cannot pass.
        rows = [row for month in months() for row in rows_for_month(month)]
        stamp, interval, rate = rows[32]
        rows[32] = (stamp + 1, interval, rate)
        rows[33] = (stamp + 2, interval, rate)
        collision, _ = audit_rows(rows, [])
        self.assertIn('DUPLICATE_NOMINAL_SETTLEMENT_SLOTS',
                      [i['issue'] for i in collision['issues']])
        self.assertIn('MISSING_EXPECTED_SETTLEMENTS',
                      [i['issue'] for i in collision['issues']])

    def test_missing_cache_offline_never_networks(self):
        with TemporaryDirectory() as t:
            with patch('quant_research_agent.funding_audit._get_fixed', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(FundingAuditError, 'Missing locally cached'):
                    run_audit(Path(t), offline=True)

    def test_sha_integrity_detects_corruption(self):
        with TemporaryDirectory() as t:
            root=Path(t)
            populate(root)
            (root/'funding'/'archive'/'BTCUSDT-fundingRate-2020-01.zip').write_bytes(b'corrupted')
            with self.assertRaisesRegex(FundingAuditError, 'Checksum mismatch'):
                run_audit(root, offline=True)

    def test_schema_and_epoch_unit_fail_closed(self):
        with self.assertRaisesRegex(FundingAuditError, 'columns'):
            read_month(zip_payload('2020-01', header=('time','hours','rate')), '2020-01')
        rows = rows_for_month('2020-01')
        rows[0] = (rows[0][0] * 1000, 8, '0.0001')
        with self.assertRaisesRegex(FundingAuditError, 'timestamp unit'):
            read_month(zip_payload('2020-01', rows), '2020-01')

    def test_off_grid_and_interval_mismatch_are_explicit(self):
        rows = [row for month in months() for row in rows_for_month(month)]
        rows[20] = (rows[20][0]+3_600_000, 4, rows[20][2])
        report, _=audit_rows(rows, [])
        self.assertEqual(report['status'],'STOP_DATA_AUDIT_FAILED')
        kinds={x['issue'] for x in report['issues']}
        self.assertTrue({'OFF_8H_UTC_GRID','NON_8H_INTERVAL'} <= kinds)
        self.assertNotIn('MISSING_EXPECTED_SETTLEMENTS', kinds)  # nominal slot still present

    def test_end_exclusive_and_read_only_2023(self):
        self.assertEqual(list(months())[-1],'2023-12')
        self.assertEqual(len(list(months())),48)
        self.assertEqual(EXPECTED_ROWS,4383)
        with TemporaryDirectory() as t:
            with self.assertRaisesRegex(FundingAuditError,'outside frozen'):
                load_verified_archive(Path(t),'2024-01',offline=True)

    def test_no_2024_data_paths_or_backtest_dependencies(self):
        import inspect
        from quant_research_agent import funding_audit
        src=inspect.getsource(funding_audit)
        self.assertNotIn('backtest.simulate',src)
        self.assertNotIn('2025-',src)
        self.assertIn('2023-12-31',src)


if __name__ == '__main__':
    unittest.main()
