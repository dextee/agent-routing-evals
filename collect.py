"""Opt-in live evaluation; requires Codex CLI and an existing model-enabled login."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
MODELS = {'baseline': 'gpt-6-luna', 'second-read': 'gpt-6.2-sol'}
EFFORT = 'medium'


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def second_read(case):
    return not case['ticket']['reference'] or len(case['ledger']) != 1


def build_prompt(cases):
    policy = (ROOT / 'policy.txt').read_text(encoding='utf-8').strip()
    inputs = json.dumps(cases, ensure_ascii=False, separators=(',', ':'))
    return f'{policy}\nUse only these inputs and no tools. Return the schema object.\n{inputs}'


def prompt_digest(prompt):
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()


def invoke(stage, cases, timeout):
    executable = shutil.which('codex')
    if not executable:
        raise SystemExit('Install Codex CLI and sign in before collecting.')
    # npm installs a POSIX shell shim and a .cmd launcher on Windows.
    if shutil.which('codex.cmd'):
        executable = shutil.which('codex.cmd')
    prompt = build_prompt(cases)
    with tempfile.TemporaryDirectory(prefix='billing-pilot-') as tmp:
        tmp = Path(tmp)
        schema = tmp / 'output.schema.json'
        schema.write_bytes((ROOT / 'response.schema.json').read_bytes())
        result = tmp / 'answer.json'
        cmd = [executable, 'exec', '--ephemeral', '--ignore-user-config',
               '--skip-git-repo-check', '-s', 'read-only', '-m', MODELS[stage],
               '-c', 'project_doc_max_bytes=0', '-c', f'model_reasoning_effort="{EFFORT}"',
               '--json', '--output-schema', str(schema), '-o', str(result), '-']
        record = {'stage': stage, 'requested_model': MODELS[stage], 'effort': EFFORT,
                  'started_utc': datetime.now(timezone.utc).isoformat(),
                  'ids': [c['id'] for c in cases],
                  'prompt_sha256': prompt_digest(prompt),
                  'cost_usd': None, 'usage': None, 'results': []}
        start = time.monotonic()
        try:
            run = subprocess.run(cmd, cwd=tmp, input=prompt, encoding='utf-8', errors='replace',
                                 capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            record.update(status='timeout', seconds=round(time.monotonic()-start, 3))
            return record
        record['seconds'] = round(time.monotonic() - start, 3)
        events = []
        for line in run.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        item_types = {e.get('item', {}).get('type') for e in events if e.get('item')}
        record['item_types'] = sorted(t for t in item_types if t)
        usage = [e.get('usage') for e in events if e.get('type') == 'turn.completed' and e.get('usage')]
        if usage:
            record['usage'] = usage[-1]
        if run.returncode or not result.exists():
            record['status'] = 'cli_error'
            print('CLI failed. See local terminal diagnostics.', flush=True)
            print(run.stderr[-1500:], flush=True)
        elif item_types - {'agent_message', 'reasoning'}:
            record['status'] = 'unexpected_activity'
        else:
            try:
                answer = json.loads(result.read_text(encoding='utf-8-sig'))
                if not isinstance(answer['results'], list):
                    raise ValueError('Invalid results')
                record.update(status='completed', results=answer['results'])
            except (ValueError, KeyError, TypeError):
                record['status'] = 'malformed_answer'
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='new output directory, one file per repeat and stage')
    parser.add_argument('--timeout', type=int, default=420)
    parser.add_argument('--split', choices=['dev', 'heldout'], default='heldout')
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('repeats must be positive')
    args.directory.mkdir(parents=True, exist_ok=False)
    cases = load('data/' + args.split + '.json')
    for repeat in range(1, args.repeats + 1):
        for stage in MODELS:
            selected = cases if stage == 'baseline' else [c for c in cases if second_read(c)]
            record = invoke(stage, selected, args.timeout)
            record.update(split=args.split, repeat=repeat)
            file = args.directory / f'{args.split}-{repeat}-{stage}.json'
            file.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
            print(file.name, record['status'], record['seconds'], flush=True)


if __name__ == '__main__':
    main()
