import csv
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
from random import Random
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from quant_research_agent import attention_kill_test as k


def fake_prices():
    out={}
    d=k.FIRST
    idx=0
    price=10000.
    while d<=k.LAST:
        price *= math.exp(0.0004+0.009*math.sin(idx*0.09)+0.002*math.cos(idx*0.13))
        out[d]=(price,100.+3*math.sin(idx*.02))
        d+=timedelta(days=1)
        idx+=1
    return out


def fake_trends():
    weeks=list(k._weeks())
    t={d:int(30+18*math.sin(i*.13)+9*math.cos(i*.07)) for i,d in enumerate(weeks)}
    s={d:max(1,min(100,t[d]+int(3*math.sin(i*.37)))) for i,d in enumerate(weeks)}
    return t,s


def write_spot(p, data, *, suffix=False):
    with p.open('w',newline='') as f:
        w=csv.writer(f)
        w.writerow(['day','open','high','low','close','volume'])
        for d,(close,vol) in data.items():
            w.writerow([d,close,close*1.01,close*.99,close,vol])
        if suffix:
            w.writerow(['2024-01-01','BAD_POST_HOLDOUT','x','x','x','x'])


def write_trends(p, topic, data):
    value='Bitcoin: (Worldwide)' if topic else 'bitcoin: (Worldwide)'
    with p.open('w') as f:
        f.write('Category: All categories\n\nWeek,'+value+'\n')
        f.write('2019-12-29,12\n')
        for d,v in data.items():
            f.write(f'{d},{v}\n')
        f.write('2023-12-31,19\n')


class AttentionKillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.path=Path(cls.temp.name)
        cls.topic_data, cls.term_data=fake_trends()
        cls.prices=fake_prices()
        cls.topicfile=cls.path/'topic.csv'
        cls.termfile=cls.path/'term.csv'
        cls.spotfile=cls.path/'spot.csv'
        write_trends(cls.topicfile,True,cls.topic_data)
        write_trends(cls.termfile,False,cls.term_data)
        write_spot(cls.spotfile,cls.prices,suffix=True)
        cls.topicsha=hashlib.sha256(cls.topicfile.read_bytes()).hexdigest()
        cls.termsha=hashlib.sha256(cls.termfile.read_bytes()).hexdigest()
        h=hashlib.sha256()
        for day,(close,volume) in cls.prices.items():
            o,high,low=close,close*1.01,close*.99
            h.update((str(day)+","+",".join(format(x,'.17g') for x in (o,high,low,close,volume))+"\n").encode())
        cls.spotsha=h.hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.patches=[mock.patch.object(k,'TOPIC_SHA',self.topicsha),
                      mock.patch.object(k,'TERM_SHA',self.termsha),
                      mock.patch.object(k,'SPOT_PREFIX_SHA',self.spotsha)]
        for p in self.patches:p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def test_real_export_hashes_are_hardcoded(self):
        self.assertNotEqual(k.TOPIC_SHA,k.TERM_SHA)
        self.assertEqual(k.WEEKLY_OBSERVATIONS,208)
        self.assertEqual(k.FEATURE_WEEK_LAG,2)

    def test_complete_topic_term_parsing(self):
        a,meta=k.load_trends(self.topicfile,topic=True)
        b,meta2=k.load_trends(self.termfile,topic=False)
        self.assertEqual(len(a),208)
        self.assertEqual(a[k.FIRST_WEEK],self.topic_data[k.FIRST_WEEK])
        self.assertEqual(meta['sha256'],self.topicsha)
        self.assertEqual(meta2['sha256'],self.termsha)

    def test_wrong_trends_query_or_digest_fails(self):
        with self.assertRaises(k.AttentionError):
            k.load_trends(self.termfile,topic=True)
        with mock.patch.object(k,'TOPIC_SHA','bad'):
            with self.assertRaises(k.AttentionError):
                k.load_trends(self.topicfile,topic=True)

    def test_spot_scope_and_prefix_and_no_2024_access(self):
        spot,meta=k.load_spot(self.spotfile)
        self.assertEqual(meta['development_rows'],1461)
        self.assertEqual(meta['last'],'2023-12-31')
        self.assertEqual(len(spot),1461)

    def test_wrong_spot_checksum_fails(self):
        with mock.patch.object(k,'SPOT_PREFIX_SHA','invalid'):
            with self.assertRaises(k.AttentionError):
                k.load_spot(self.spotfile)

    def test_missing_week_or_missing_spot_day_fails(self):
        one=self.path/'badtrend.csv'
        lines=self.topicfile.read_text().splitlines()
        one.write_text('\n'.join([x for x in lines if not x.startswith('2021-03-07,')])+'\n')
        with mock.patch.object(k,'TOPIC_SHA',k.digest(one.read_bytes())):
            with self.assertRaises(k.AttentionError):
                k.load_trends(one,topic=True)
        prices=self.prices.copy()
        del prices[date(2022,5,1)]
        spot=self.path/'missing.csv'
        write_spot(spot,prices)
        with mock.patch.object(k,'SPOT_PREFIX_SHA',k.digest(b'x')):
            with self.assertRaises(k.AttentionError):
                k.load_spot(spot)

    def test_weekly_causality_two_weeks_lag(self):
        topic=self.topic_data.copy()
        term=self.term_data.copy()
        train,test=k.construct_rows(self.prices,topic,term)
        self.assertGreater(len(train),70)
        self.assertEqual({r['week'].year for r in test},{2022,2023})
        day=date(2022,3,6)
        original=next(r for r in test if r['week']==day)
        topic[day]=100
        topic[day-timedelta(days=7)]=100
        _,updated=k.construct_rows(self.prices,topic,term)
        changed=next(r for r in updated if r['week']==day)
        self.assertEqual(original['topic_change'],changed['topic_change'])
        self.assertEqual(original['features_base'],changed['features_base'])
        # Current week's market data is the target, never a signal.
        topic[day-timedelta(days=14)]=100
        _,updated2=k.construct_rows(self.prices,topic,term)
        changed2=next(r for r in updated2 if r['week']==day)
        self.assertNotEqual(original['topic_change'],changed2['topic_change'])

    def test_calibration_no_2022_data_or_target_leak(self):
        a,b=k.construct_rows(self.prices,self.topic_data,self.term_data)
        self.assertTrue(all(r['week']+timedelta(days=6)<=k.CAL_LAST for r in a))
        self.assertTrue(all(r['week']>=k.EVAL_START for r in b))
        pred,fit=k.fit_predict(a,b,signal='topic_change')
        b2=[dict(row,target=1000000.) for row in b]
        pred2,fit2=k.fit_predict(a,b2,signal='topic_change')
        self.assertEqual(pred,pred2)
        self.assertEqual(fit,fit2)

    def test_ridge_fit_is_deterministic(self):
        tr,te=k.construct_rows(self.prices,self.topic_data,self.term_data)
        p1,m1=k.fit_predict(tr,te,signal=None)
        p2,m2=k.fit_predict(tr,te,signal=None)
        self.assertEqual(p1,p2)
        self.assertEqual(m1,m2)
        self.assertEqual(len(p1),len(te))

    def test_bootstrap_is_deterministic_and_correct_sign(self):
        d=[1.,2.,3.,4.]*30
        self.assertGreater(k.block_lower(d),0)
        self.assertLess(k.block_lower([-x for x in d]),0)
        self.assertEqual(k.block_lower(d),k.block_lower(d))

    def test_report_is_immutable_and_no_trades(self):
        with tempfile.TemporaryDirectory() as root:
            r=k.run(Path(root),self.topicfile,self.termfile,self.spotfile)
            p=Path(r['report'])
            self.assertTrue(p.exists())
            self.assertIn(r['status'],('STOP_INSUFFICIENT_INCREMENTAL_INFORMATION',
                                      'PASS_RETROSPECTIVE_INCREMENTAL_INFORMATION_ONLY'))
            d=json.loads(p.read_text())
            self.assertEqual(d['evaluation']['weeks'],104)
            self.assertFalse(d['trading_allowed'])
            self.assertFalse(d['strategy_backtest_allowed'])
            self.assertEqual(k.run(Path(root),self.topicfile,self.termfile,self.spotfile)['report'],r['report'])
            p.write_text('CHANGED')
            with self.assertRaises(k.AttentionError):
                k.run(Path(root),self.topicfile,self.termfile,self.spotfile)

    def test_cli_requires_actual_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            code=k.main(['--home',root,'--topic',str(self.topicfile),
                         '--term',str(self.termfile),'--spot',str(self.spotfile)])
            self.assertIn(code,(0,2))
            self.assertTrue((Path(root)/'attention'/k.OUTPUT_NAME).exists())


if __name__=='__main__':unittest.main()
