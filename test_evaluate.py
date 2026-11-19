import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from evaluate import PILOT, index_answers, replay, summarize

GOLD = {'id': 'T1', 'route': 'explain', 'claim': 'one_capture', 'sources': ['T1','L1'],
        'human_review': False}
RUN = {'ids': ['T1'], 'status': 'completed', 'results': [GOLD], 'seconds': 1.5,
       'cost_usd': .02, 'usage': {'output_tokens': 15}}


class ReplayTests(unittest.TestCase):
    def test_wrong_claim_rejected_even_with_correct_route(self):
        bad = dict(GOLD, claim='reversed_only')
        score = summarize([GOLD], {'T1': bad}, [RUN])
        self.assertEqual((score['accepted'], score['incorrect_claims']), (0, 1))

    def test_source_order_and_multiplicity(self):
        for sources, accepted in [(['L1','T1'], 1), (['L1','T1','T1'], 0), (['T1'], 0)]:
            self.assertEqual(summarize([GOLD], {'T1': dict(GOLD, sources=sources)},
                                       [RUN])['accepted'], accepted)

    def test_duplicate_answer_and_extra_ids_rejected(self):
        for row in (GOLD, dict(GOLD, id='X')):
            with self.assertRaises(ValueError):
                index_answers(dict(RUN, results=[GOLD, row]), ['T1'])

    def test_lost_review_and_unknown_cost(self):
        missed = summarize([dict(GOLD,human_review=True)], {}, [dict(RUN, cost_usd=None)])
        self.assertEqual((missed['missed_reviews'],missed['unresolved']), (1,1))
        self.assertIsNone(missed['cost_per_accepted_usd'])

    def test_all_attempt_spend(self):
        failed = dict(RUN, status='timeout', results=[])
        score = summarize([GOLD], {'T1': GOLD}, [failed, RUN])
        self.assertEqual((score['cost_per_accepted_usd'],score['failed_attempts']), (.04,1))
        self.assertEqual(index_answers(failed, ['T1']), {})

    def test_actual_public_pilot(self):
        report = replay()
        self.assertEqual(len(report), 2)
        for row in report:
            for strategy in ('fixed', 'escalation'):
                self.assertEqual(row[strategy]['total'], 20)
                self.assertEqual(len(row[strategy]['cases']), 20)
                self.assertIsNone(row[strategy]['cost_per_accepted_usd'])

    def test_replay_rejects_changed_prompt_or_effort(self):
        with TemporaryDirectory() as tmp:
            runs = shutil.copytree(PILOT, Path(tmp) / 'runs')
            for stage in ('baseline', 'second-read'):
                path = runs / f'heldout-1-{stage}.json'
                original = path.read_text(encoding='utf-8')
                for field, value, message in [('prompt_sha256', '0' * 64, 'Prompt fingerprint'),
                                              ('effort', 'low', 'Reasoning effort')]:
                    with self.subTest(stage=stage, field=field):
                        record = json.loads(original)
                        record[field] = value
                        path.write_text(json.dumps(record), encoding='utf-8')
                        with self.assertRaisesRegex(ValueError, message):
                            replay(runs)
                path.write_text(original, encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
