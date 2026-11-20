"""Evidence retrieval and scope tests. No live network and no backtest calls."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# In the standalone authoring environment, source_fit_audit is represented by
# a one-function stub; GitHub CI exercises the real module & original P1 tests.
try:
    from quant_research_agent import abstract_evidence as e
except ImportError:
    raise

DOI = '10.1016/j.frl.2018.12.004'
TITLE = 'Bitcoin and the day-of-the-week effect'
BAD = 'A crypto-stock weekend effect: Predicting Monday stock returns using weekend cryptocurrency returns'


def crossref(doi=DOI, title=TITLE, abstract=None):
    m={'DOI':doi,'title':[title]}
    if abstract is not None: m['abstract']=abstract
    return json.dumps({'status':'ok','message':m}).encode()


def index(s):
    result = {}
    for i,w in enumerate(s.split()):
        result.setdefault(w,[]).append(i)
    return result


def openalex(doi=DOI, title=TITLE, abstract='Bitcoin day-of-the-week patterns in daily returns.'):
    return json.dumps({'results':[{'doi':'https://doi.org/'+doi,'title':title,
                       'abstract_inverted_index':index(abstract)}]}).encode()


class EvidenceSemanticsTest(unittest.TestCase):
    def test_stock_target_mismatch_vetoes_calendar(self):
        a=e.analyze(BAD,'Weekend cryptocurrency returns predict Monday stock returns.',source='Crossref')
        self.assertEqual(a['decision'],'REJECT_TARGET_MISMATCH')
        self.assertEqual(a['target'],'EQUITY_OR_STOCK_RETURNS')
        self.assertEqual(a['predictor'],'PRIOR_CRYPTO_RETURN')
        self.assertFalse(a['experiment_authorized'])
        self.assertIn('equity', a['evidence'])
    def test_btc_weekday_relevant_but_not_permission_to_repeat_archived_model(self):
        a=e.analyze('Day-of-the-week effect on Bitcoin returns',
                    'We study daily Bitcoin returns and Monday effects.',source='OpenAlex')
        self.assertEqual(a['decision'],'TOPIC_RELATED_PROTOCOL_REVIEW')
        self.assertEqual(a['frequency'],'DAILY_OR_WEEKDAY')
        self.assertIn('weekday',a['evidence'])
        self.assertFalse(a['archived_BTC_Monday_retest_allowed'])
    def test_btc_derivatives_or_hourly_rejected(self):
        a=e.analyze('Day-of-the-week effects on Bitcoin futures returns',
                    'Daily Bitcoin futures returns exhibit Monday effects.',source='Crossref')
        self.assertEqual(a['decision'],'REJECT_MARKET_MISMATCH')
        b=e.analyze('Bitcoin hour-of-day, day-of-week effects on returns',
                    'Intraday Bitcoin returns vary by weekday.',source='OpenAlex')
        self.assertEqual(b['decision'],'REJECT_FREQUENCY_MISMATCH')
    def test_no_abstract_never_topic_approved(self):
        a=e.analyze('Bitcoin and the day-of-the-week effect',None,source='NONE')
        self.assertEqual(a['decision'],'NEEDS_HUMAN_SOURCE_REVIEW')
        self.assertEqual(a['abstract_source'],None)
    def test_generic_calendar_not_frozen_monday(self):
        a=e.analyze('Calendar effects in Bitcoin returns and volatility',
                    'We study calendar anomalies in daily Bitcoin returns.',source='Crossref')
        self.assertEqual(a['decision'],'NEEDS_HUMAN_SOURCE_REVIEW')
    def test_noncalendar_predictor(self):
        a=e.analyze('Bitcoin returns connectedness with macroeconomic factors',
                    'Macroeconomic shocks predict Bitcoin returns.',source='OpenAlex')
        self.assertEqual(a['decision'],'REJECT_PREDICTOR_MISMATCH')
    def test_crossref_valid_doi_and_jats_strip(self):
        a,t=e.crossref_abstract(crossref(abstract='<jats:p>Daily Bitcoin returns.</jats:p>'),DOI)
        self.assertEqual(a,'Daily Bitcoin returns.')
        self.assertEqual(t,TITLE)
    def test_crossref_wrong_doi_blocked(self):
        with self.assertRaisesRegex(ValueError,'DOI mismatch'):
            e.crossref_abstract(crossref(doi='10.1234/not.same'),DOI)
    def test_openalex_rebuild_and_validation(self):
        a,t=e.openalex_abstract(openalex(),DOI)
        self.assertEqual(a,'Bitcoin day-of-the-week patterns in daily returns.')
        self.assertEqual(t,TITLE)
        self.assertEqual(e.decode_openalex({'a':[0],'b':[0]}),'')
        self.assertEqual(e.decode_openalex({'a':[0],'b':[2]}),'')
        self.assertEqual(e.decode_openalex({'a':['0']}),'')
    def test_openalex_mismatched_and_ambiguous(self):
        with self.assertRaisesRegex(ValueError,'DOI mismatch'):
            e.openalex_abstract(openalex(doi='10.1234/wrong'),DOI)
        with self.assertRaises(ValueError):
            e.openalex_abstract(json.dumps({'results':[{'x':1},{'y':2}]}).encode(),DOI)
    def test_endpoint_fixed_and_url_encoded(self):
        urls=e.source_urls(DOI)
        self.assertIn('api.crossref.org',urls[0]);self.assertIn('api.openalex.org',urls[1])
        with self.assertRaises(ValueError):
            e.source_urls('https://169.254.169.254')
    def test_network_url_origin_rejected(self):
        for u in ('http://api.openalex.org/works','https://169.254.169.254/works',
                  'https://user:pwd@api.crossref.org/works'):
            with self.assertRaises(ValueError):e.get_json(u)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'runtime'
        p=self.root/'agent';p.mkdir(parents=True)
        db=sqlite3.connect(p/'autonomous_loop.sqlite3')
        db.execute('CREATE TABLE papers(doi TEXT,title TEXT,publication_year INTEGER,decision TEXT,response_sha TEXT)')
        rows=[(DOI,TITLE,2019,'NEEDS_HUMAN_SOURCE_REVIEW','abc'),
              ('10.1016/j.frl.2025.108661',BAD,2025,'REJECT_TARGET_MISMATCH','abc')]
        db.executemany('INSERT INTO papers VALUES(?,?,?,?,?)',rows)
        db.commit();db.close()
        self.actual=rows
    def verifier(self,root,db,doi):
        row=db.execute('SELECT * FROM papers WHERE doi=?',(doi,)).fetchone()
        return {'doi':doi,'title':row['title']}
    def test_plan_stays_offline_and_bounded(self):
        with patch.object(e,'verified_stored_paper',side_effect=self.verifier):
            p=e.plan(self.root,5)
        self.assertEqual(p['network_requests'],0)
        self.assertLessEqual(len(p['selected']),5)
        self.assertGreaterEqual(len(p['selected']),1)
    def test_local_batch_enrich_fallback_and_no_replay(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            if 'crossref.org' in url:return crossref()
            return openalex()
        with patch.object(e,'verified_stored_paper',side_effect=self.verifier):
            out=e.enrich(self.root,1,now=datetime(2026,11,20,tzinfo=timezone.utc),fetcher=fetch)
            repeat=e.enrich(self.root,1,now=datetime(2026,11,20,tzinfo=timezone.utc),fetcher=lambda _:self.fail('No second HTTP'))
        self.assertEqual(out['status'],'EVIDENCE_REVIEW_ARCHIVED')
        self.assertEqual(out['papers_reviewed'],1)
        self.assertEqual(out['studies_executed'],0)
        self.assertEqual(repeat['status'],'IDLE_NO_NEW_REVIEW_PAPERS')
        self.assertEqual(len(calls),2)
        report=json.loads(Path(out['report_path']).read_text())
        self.assertEqual(report['entries'][0]['abstract_status'],'AVAILABLE')
        self.assertEqual(report['entries'][0]['scope']['decision'],'NEEDS_HUMAN_SOURCE_REVIEW')
        self.assertTrue((self.root/report['entries'][0]['provenance'][0]['raw_path']).exists())
    def test_crossref_abstract_avoids_openalex(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            return crossref(abstract='Daily Bitcoin returns have a Monday effect.')
        with patch.object(e,'verified_stored_paper',side_effect=self.verifier):
            out=e.enrich(self.root,1,now=datetime(2026,11,20,tzinfo=timezone.utc),fetcher=fetch)
        self.assertEqual(out['network_requests'],1)
        self.assertEqual(len(calls),1)
    def test_invalid_doi_never_reached_from_verifier(self):
        with patch.object(e,'verified_stored_paper',side_effect=ValueError('archived sha mismatch')):
            with self.assertRaisesRegex(ValueError,'archived sha mismatch'):
                e.plan(self.root)
    def test_pause_prevents_network(self):
        (self.root/'PAUSED').write_text('paused')
        out=e.enrich(self.root,5,fetcher=lambda _: self.fail('no HTTP'))
        self.assertEqual(out['status'],'PAUSED')
        self.assertEqual(out['network_requests'],0)

if __name__=='__main__': unittest.main()
