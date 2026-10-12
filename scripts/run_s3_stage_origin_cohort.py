"""Frozen twenty-case comparison, live checks, persistent Oracle raw only."""
import argparse
import concurrent.futures
import json
import os
import platform
import re
import sys
from pathlib import Path

from scripts.run_s3_integer_carry_cohort import ROOT, execute
from scripts.run_s3_stage_origin import PLAN


def commands(plan, sha):
    return [(r, [sys.executable, '-m', 'scripts.run_s3_stage_origin',
        '--expected-source-sha', sha, '--output', f'outputs/{r["name"]}/raw',
        '--case', r['case'], '--condition', str(r['condition']),
        '--stage-origin', r['option'], '--execute']) for r in plan['runs']]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    items = commands(json.loads((ROOT/PLAN).read_text()), a.expected_source_sha)
    if not a.execute:
        print(json.dumps(items))
        return 0
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or ROOT.name != a.expected_source_sha or not re.fullmatch('[a-f0-9]{40}', a.expected_source_sha) or os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('committed x86 archive and priority zero required')
    if len(items) != 20 or os.environ.get('LP_NUM_THREADS') != '4':
        raise ValueError('frozen twenty workers / LP4 required')
    if a.output.is_absolute() or len(a.output.parts) != 3 or a.output.parts[0] != 'outputs' or a.output.parts[-1] != 'cohort':
        raise ValueError('new outputs/<batch>/cohort required')
    resolved = a.output.resolve()
    if not resolved.is_relative_to(Path.home()/'ugrp-sim/runs'):
        raise ValueError('raw must be on persistent runs disk')
    if (resolved.parent/'SOURCE_SHA').read_text().strip() != a.expected_source_sha:
        raise ValueError('source receipt mismatch')
    a.output.mkdir(parents=True, exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(execute, item, a.output, a.expected_source_sha) for item in items]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    (a.output/'cohort.json').write_text(json.dumps(sorted(results, key=lambda r: r['name']), indent=2)+'\n')
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
