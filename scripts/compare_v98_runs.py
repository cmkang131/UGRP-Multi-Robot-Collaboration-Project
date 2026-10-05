"""Byte comparison of two v98 case directories for wall-time-only changes (monitor, exact speedups).

Every file under both case directories is compared by SHA-256. A differing JSON/JSONL file is diffed
key by key; a difference is accepted only at an EXACT key path of the allowlist below (list indices
normalised to ``[]``), each with the source line that makes it differ between any two runs:

* ``result.json``  ``/loadavg_start[]``, ``/loadavg_end[]``: host load (scripts/run_pair_highpose.py)
* ``student_record.json``  ``/pair[]/status_messages[]/task_id``: ``'pair-' + uuid.uuid4().hex``
  (harness/zone_pair_executor.py, PairStatusChannel creation)
* ``student_record.json``  ``/robots/<r>/provider/provider/lifecycle[]/{before,after}/pf_id``: ``id(pf)``
  (harness/vision_pose_source_pair_v3.py, relocalization lifecycle)
* ``student_record.json``  ``/robots/<r>/provider/provider/inference_wall_ms/{p50,p90,max}``: wall clock
* ``eval_only/dr_receipt_nees.json``  ``/source/student_record`` (absolute path of the run),
  ``/source/student_record_sha256`` (hash of a record that contains the fields above) and
  ``/truth_files/{r1,r2}/path`` (absolute path of the run; their ``sha256``/``rows`` must still match)
  (scripts/eval_highpose_receipt_nees.py)
* ``artifacts.sha256.json``: only the entries of files whose own differences are all allowed

Anything else (a command, a frame byte, an event, a count, a missing file) is a BEHAVIOUR difference.
Exit code 0 identical up to the allowlist, 1 behaviour difference, 2 bad input.

usage: python scripts/compare_v98_runs.py <caseA> <caseB> [--json report.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ALLOWED = {
    'result.json': {'/loadavg_start[]', '/loadavg_end[]'},
    'student_record.json': {
        '/pair[]/status_messages[]/task_id',
        *(f'/robots/{r}/provider/provider/lifecycle[]/{s}/pf_id' for r in ('r1', 'r2') for s in ('before', 'after')),
        *(f'/robots/{r}/provider/provider/inference_wall_ms/{k}' for r in ('r1', 'r2') for k in ('p50', 'p90', 'max')),
    },
    'eval_only/dr_receipt_nees.json': {'/source/student_record', '/source/student_record_sha256',
                                       '/truth_files/r1/path', '/truth_files/r2/path'},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diff_paths(a, b, path='', out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f'{path}/{k} <missing on one side>')
            else:
                diff_paths(a[k], b[k], f'{path}/{k}', out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f'{path} <length {len(a)} vs {len(b)}>')
        for i, (x, y) in enumerate(zip(a, b)):
            diff_paths(x, y, f'{path}[{i}]', out)
    elif a != b or type(a) is not type(b):
        out.append(path)
    return out


def _load(path):
    if path.suffix == '.json':
        return json.loads(path.read_text())
    if path.suffix == '.jsonl':
        return [json.loads(line) for line in path.read_text().splitlines()]
    return None


def compare(a: Path, b: Path) -> dict:
    fa = {str(p.relative_to(a)): p for p in a.rglob('*') if p.is_file()}
    fb = {str(p.relative_to(b)): p for p in b.rglob('*') if p.is_file()}
    only = sorted(set(fa) ^ set(fb))
    files, allowed_files = {}, set()
    identical = 0
    for rel in sorted(set(fa) & set(fb)):
        if sha(fa[rel]) == sha(fb[rel]):
            identical += 1
            continue
        if rel == 'artifacts.sha256.json':
            continue
        try:
            da, db = _load(fa[rel]), _load(fb[rel])
        except ValueError as exc:
            files[rel] = {'allowed': False, 'n': 1, 'unexpected': [f'<unparsable: {exc}>']}
            continue
        if da is None:
            files[rel] = {'allowed': False, 'n': 1, 'unexpected': ['<binary bytes differ>']}
            continue
        paths = diff_paths(da, db)
        norm = [re.sub(r'\[\d+\]', '[]', p) for p in paths]
        unexpected = sorted({p for p in norm if p not in ALLOWED.get(rel, set())})
        files[rel] = {'allowed': not unexpected, 'n': len(paths), 'kinds': sorted(set(norm))[:50],
                      'unexpected': unexpected[:50]}
        if not unexpected:
            allowed_files.add(rel)
    if 'artifacts.sha256.json' in fa and 'artifacts.sha256.json' in fb and sha(fa['artifacts.sha256.json']) != sha(fb['artifacts.sha256.json']):
        ma, mb = _load(fa['artifacts.sha256.json']), _load(fb['artifacts.sha256.json'])
        keys = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
        unexpected = [k for k in keys if k not in allowed_files]
        files['artifacts.sha256.json'] = {'allowed': not unexpected, 'n': len(keys), 'kinds': keys, 'unexpected': unexpected}
    behaviour = sorted(r for r, v in files.items() if not v['allowed'])
    return {'a': str(a), 'b': str(b), 'files_a': len(fa), 'files_b': len(fb), 'identical_files': identical,
            'only_one_side': only, 'differing_files': files, 'behaviour_differences': behaviour,
            'allowlist': {k: sorted(v) for k, v in ALLOWED.items()},
            'verdict': 'IDENTICAL_UP_TO_ALLOWLIST' if not behaviour and not only else 'BEHAVIOUR_DIFFERENT'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('a', type=Path)
    p.add_argument('b', type=Path)
    p.add_argument('--json', type=Path)
    x = p.parse_args(argv)
    if not x.a.is_dir() or not x.b.is_dir():
        print('both arguments must be case directories')
        return 2
    report = compare(x.a, x.b)
    if x.json:
        x.json.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: report[k] for k in ('files_a', 'files_b', 'identical_files', 'only_one_side',
                                             'behaviour_differences', 'verdict')}, indent=1))
    for rel, v in report['differing_files'].items():
        print(rel, 'allowed' if v['allowed'] else 'BEHAVIOUR', v['n'], v['unexpected'][:8] or v.get('kinds', [])[:6])
    return 0 if report['verdict'] == 'IDENTICAL_UP_TO_ALLOWLIST' else 1


if __name__ == '__main__':
    raise SystemExit(main())
