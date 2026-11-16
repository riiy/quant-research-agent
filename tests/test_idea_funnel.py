"""Offline regression tests for the economic-mechanism funnel."""
import json
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quant_research_agent.evidence import SOURCES, MECHANISMS, mechanism_screen, next_feasible_mechanism, legacy_trend_researched
from quant_research_agent.idea_funnel import Idea, IdeaStore, discover, api_idea, seed_idea, main


class EvidenceTests(unittest.TestCase):
    def test_sources_have_curated_dois_and_explicit_scope(self):
        self.assertGreaterEqual(len(SOURCES), 5)
        for item in SOURCES.values():
            self.assertTrue(item['url'].startswith('https://doi.org/'))
            self.assertTrue(item['finding'] and item['universe'])

    def test_materially_different_mechanisms_are_not_trend_variants(self):
        self.assertEqual(mechanism_screen('trend_persistence')['status'], 'BLOCKED')
        self.assertEqual(mechanism_screen('liquidity_reversal')['status'], 'BLOCKED')
        self.assertEqual(mechanism_screen('attention_demand')['status'], 'BLOCKED')
        self.assertEqual(next_feasible_mechanism(set()), 'volatility_exposure')
        self.assertIsNone(next_feasible_mechanism({'volatility_exposure'}))
        self.assertIn('volatility_exposure', MECHANISMS)
        self.assertEqual(mechanism_screen('volatility_exposure', {'volatility_exposure'})['status'], 'BLOCKED')

    def test_archived_trend_blocks_legacy_api_but_not_seed_demo(self):
        class FakeStore:
            def __init__(self, status):
                self.status = status
            def list(self, limit=100000):
                return [{"id": "prior"}]
            def get(self, run_id):
                return {"status": self.status, "candidate_json": json.dumps({"family": "momentum", "params": {"lookback": 120}})}
        self.assertTrue(legacy_trend_researched(FakeStore('ARCHIVED_REJECTED_OR_INCONCLUSIVE')))
        self.assertFalse(legacy_trend_researched(FakeStore('DEMO_SEEDED_HYPOTHESIS')))

    def test_wrong_source_or_mechanism_is_rejected(self):
        example = seed_idea('volatility_exposure').value
        bad = dict(example, source_ids=['zaremba2021'])
        with self.assertRaisesRegex(ValueError, 'verified source'):
            Idea(bad, selected_mechanism='volatility_exposure')
        with self.assertRaisesRegex(ValueError, 'preselected'):
            Idea(dict(example, mechanism_id='trend_persistence'), selected_mechanism='volatility_exposure')
        with self.assertRaisesRegex(ValueError, 'missing='):
            Idea({key: value for key, value in example.items() if key != 'falsifier'}, selected_mechanism='volatility_exposure')


class FunnelTests(unittest.TestCase):
    def test_seed_does_not_create_paid_attempt_or_consume_mechanism(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            demo = discover(root, 'seed')
            self.assertEqual(demo['status'], 'DEMO_NOT_ARCHIVED')
            self.assertEqual(demo['api_calls'], 0)
            self.assertEqual(IdeaStore(root).seen(), set())
            self.assertFalse((root / 'research.sqlite3').exists())

    def test_unavailable_or_already_screened_mechanisms_cost_zero(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            store = IdeaStore(root)
            idea = seed_idea('volatility_exposure')
            store.save(idea, mechanism_screen('volatility_exposure'), {'mode': 'test'})
            with patch('quant_research_agent.idea_funnel.api_idea') as model:
                outcome = discover(root, 'api')
            model.assert_not_called()
            self.assertEqual(outcome['status'], 'NO_NEW_FEASIBLE_MECHANISMS')
            self.assertEqual(outcome['api_calls'], 0)

    def test_unique_mechanism_not_unique_parameter(self):
        with TemporaryDirectory() as temp:
            store = IdeaStore(Path(temp))
            idea = seed_idea('volatility_exposure')
            screen = mechanism_screen('volatility_exposure')
            store.save(idea, screen, {'mode':'test'})
            with self.assertRaises(Exception):
                store.save(idea, screen, {'mode':'test'})
            self.assertEqual(store.seen(), {'volatility_exposure'})

    def test_gateway_responses_format_and_same_source_scope(self):
        idea = seed_idea('volatility_exposure').value
        payload = {'status':'completed', 'output': [{'content': [
            {'type':'output_text', 'text':json.dumps({'idea': idea})}]}],
            'usage': {'input_tokens':23,'output_tokens':45}}
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test-only', 'QUANT_MODEL':'test-model',
                                      'OPENAI_API_URL':'https://api.example.test/v1/responses'}):
            with patch('quant_research_agent.idea_funnel.request.urlopen', return_value=BytesIO(json.dumps(payload).encode())) as mocked:
                result, meta = api_idea('volatility_exposure')
        body = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(body['input'][0]['role'], 'user')
        self.assertEqual(body['input'][0]['content'][0]['type'], 'input_text')
        self.assertEqual(body['text']['format']['type'], 'json_schema')
        self.assertEqual(body['text']['format']['schema']['properties']['mechanism_id']['enum'], ['volatility_exposure'])
        self.assertIn('Only daily_ohlcv', body['instructions'])
        self.assertEqual(result.value, idea)
        self.assertEqual(meta['usage']['input_tokens'], 23)

    def test_preview_offline(self):
        with TemporaryDirectory() as temp:
            with patch('quant_research_agent.idea_funnel.api_idea') as remote:
                self.assertEqual(main(['--home', temp, 'preview']), 0)
            remote.assert_not_called()


if __name__ == '__main__':
    unittest.main()
