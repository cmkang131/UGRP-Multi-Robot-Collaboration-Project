"""Summarize finished Oracle receipts; never run physics or rewrite raw evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def differences(a, b, path='$'):
    if type(a) is not type(b):
        yield path
    elif isinstance(a, dict):
        for key in sorted(a.keys() | b.keys()):
            if key not in a or key not in b:
                yield f'{path}.{key}'
            else:
                yield from differences(a[key], b[key], f'{path}.{key}')
    elif isinstance(a, list):
        if len(a) != len(b):
            yield f'{path}.length'
        for i, (left, right) in enumerate(zip(a, b)):
            yield from differences(left, right, f'{path}[{i}]')
    elif a != b:
        yield path


def decode(path):
    text = path.read_text()
    return ([json.loads(line) for line in text.splitlines() if line.strip()]
            if path.suffix == '.jsonl' else json.loads(text))


def summarize(root):
    original = root / 'data/comparison.json'
    data = json.loads(original.read_text())
    result = {
        'schema': 'ugrp.lazy_camera_report.v1',
        'raw': str(root), 'raw_receipt_sha256': digest(original),
        'measurement_source': data['source'], 'order': data['order'],
        'default': data['default'], 'adopted': data['adopted'],
        'scope': 'Oracle finite DEV phases; startup-inclusive wall/SIM; no mission success claim',
        'physics_timer_limit': 'Legacy adapters bypass the selected physics hook; zero calls means unmeasured, not zero physics cost.',
        'cases': [],
    }
    for case in data['results']:
        compact = {k: v for k, v in case.items() if k not in ('rows', 'camera')}
        compact['arms'] = []
        for i, (row, camera) in enumerate(zip(case['rows'], case['camera']), 1):
            assert row['failure'] is None and row['sim_s'] == 60
            arm = {k: v for k, v in row.items() if k != 'samples'}
            arm['sample_count'] = len(row['samples'])
            arm['camera'] = camera
            arm['physics_timer_measured'] = row['timers']['physics_calls'] > 0
            compact['arms'].append(arm)
        compact['mismatch_diagnosis'] = []
        first = root / 'data' / f"{case['kind']}-1-eager"
        for name in case['mismatches']:
            entry = {'file': name, 'comparisons_to_first_A': []}
            for i, mode in enumerate(data['order'][1:], 2):
                other = root / 'data' / f"{case['kind']}-{i}-{mode}"
                a, b = first / name, other / name
                comparison = {'arm': i, 'mode': mode}
                if not a.is_file() or not b.is_file():
                    comparison['diagnosis'] = 'not fetched or missing; raw comparison remains authoritative'
                else:
                    comparison.update(a_sha256=digest(a), b_sha256=digest(b), byte_equal=a.read_bytes() == b.read_bytes())
                    if a.suffix in ('.json', '.jsonl'):
                        paths = list(differences(decode(a), decode(b)))
                        comparison.update(parsed_difference_count=len(paths),
                            field_counts=dict(Counter(p.rsplit('.', 1)[-1] for p in paths)),
                            first_paths=paths[:100],
                            diagnosis='parsed differences' if paths else 'serialization only (parsed values equal)')
                    else:
                        comparison['diagnosis'] = 'binary mismatch; no semantic normalization'
                entry['comparisons_to_first_A'].append(comparison)
            compact['mismatch_diagnosis'].append(entry)
        compact['all_robot_files_identical'] = not any(p.startswith('robots/') for p in case['mismatches'])
        result['cases'].append(compact)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = summarize(args.raw.resolve())
    with args.output.open('x') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(args.output)
