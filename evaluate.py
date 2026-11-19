"""Replay a pair of recorded routing strategies without a model login or dependencies."""
import argparse
from collections import Counter
import json
from pathlib import Path

from collect import ROOT, MODELS, load, second_read

FIELDS = {'id', 'route', 'claim', 'sources', 'human_review'}
PILOT = ROOT / 'results' / 'pilot-2026-11-20'


def index_answers(record, expected_ids):
    if record['ids'] != expected_ids:
        raise ValueError('Recorded request membership differs from the protocol')
    if record['status'] != 'completed':
        return {}
    answers = {}
    for row in record['results']:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('Unexpected result structure')
        key = row['id']
        if key not in expected_ids or key in answers:
            raise ValueError(f'Unexpected or duplicate ID: {key}')
        if (type(row['human_review']) is not bool or not isinstance(row['sources'], list)
                or not all(isinstance(x, str) for x in row['sources'])):
            raise ValueError(f'Invalid review flag or source list: {key}')
        answers[key] = row
    return answers


def summarize(gold, answers, records):
    checks = []
    for expected in gold:
        key = expected['id']
        answer = answers.get(key)
        mismatches = []
        if answer is None:
            mismatches = ['unresolved']
        else:
            for field in ['route', 'claim', 'human_review', 'sources']:
                left, right = expected[field], answer[field]
                if field == 'sources':
                    left, right = sorted(left), sorted(right)
                if left != right:
                    mismatches.append(field)
        checks.append({'id': key, 'errors': mismatches,
                       'missed_review': expected['human_review'] and
                       (answer is None or not answer['human_review'])})
    accepted = sum(not row['errors'] for row in checks)
    costs = [r['cost_usd'] for r in records]
    usage = [r.get('usage') for r in records]
    tokens = None
    if all(isinstance(u, dict) for u in usage):
        tokens = dict(sum((Counter(u) for u in usage), Counter()))
    return {'accepted': accepted, 'total': len(gold),
            'missed_reviews': sum(row['missed_review'] for row in checks),
            'incorrect_claims': sum('claim' in row['errors'] for row in checks),
            'unresolved': sum('unresolved' in row['errors'] for row in checks),
            'failed_attempts': sum(r['status'] != 'completed' for r in records),
            'seconds': round(sum(r['seconds'] for r in records), 3),
            'usage': tokens, 'cost_per_accepted_usd':
                sum(costs) / accepted if accepted and all(v is not None for v in costs) else None,
            'cases': checks}


def replay(directory=PILOT, split='heldout'):
    cases = load(f'data/{split}.json')
    gold = load(f'expected/{split}.json')
    ids = [c['id'] for c in cases]
    if len(ids) != len(set(ids)) or [r['id'] for r in gold] != ids:
        raise ValueError('Answer key does not cover the unique fixture IDs in order')
    escalated = [c['id'] for c in cases if second_read(c)]
    repeats = {}
    for path in sorted(directory.glob(f'{split}-*.json')):
        r = json.loads(path.read_text(encoding='utf-8'))
        stage = r['stage']
        if r['split'] != split or stage not in MODELS or r['requested_model'] != MODELS[stage]:
            raise ValueError(f'Unexpected run metadata: {path.name}')
        batch = repeats.setdefault(r['repeat'], {})
        if stage in batch:
            raise ValueError(f'Duplicate stage: {path.name}')
        batch[stage] = r
    if not repeats:
        raise ValueError('No matching run files')
    report = []
    for repeat, stages in sorted(repeats.items()):
        if set(stages) != set(MODELS):
            raise ValueError(f'Missing recorded stage in repeat {repeat}')
        base, second = stages['baseline'], stages['second-read']
        fixed = index_answers(base, ids)
        routed = {key: value for key, value in fixed.items() if key not in escalated}
        routed.update(index_answers(second, escalated))
        report.append({'repeat': repeat, 'fixed': summarize(gold, fixed, [base]),
                       'escalation': summarize(gold, routed, [base, second])})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=PILOT)
    parser.add_argument('--split', choices=['dev', 'heldout'], default='heldout')
    parser.add_argument('--json', action='store_true', help='include per-case grading and usage')
    args = parser.parse_args()
    try:
        report = replay(args.runs, args.split)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f'Cannot replay: {error}\n')
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report:
            for strategy in ('fixed', 'escalation'):
                s = row[strategy]
                print(f"Repeat {row['repeat']} {strategy:10}  accepted {s['accepted']}/{s['total']}, "
                      f"missed reviews {s['missed_reviews']}, incorrect claims {s['incorrect_claims']}, "
                      f"unresolved {s['unresolved']}, {s['seconds']:.1f}s")
