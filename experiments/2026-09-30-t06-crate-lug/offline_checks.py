"""T06 related offline regressions. No host lock, native model or network."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TESTS = [
    'tests/test_zone_own_executor_crate.py',
    'tests/test_zone_pair_executor.py', 'tests/test_zone_pair_status.py',
    'tests/test_zone_pair_admission.py', 'tests/test_zone_pair_review.py',
    'tests/test_zone_pair_review2.py',
    'tests/test_zone_study_integration.py', 'tests/test_zone_study_integration_pair.py',
    'tests/test_zone_study_integration_seams.py',
    'tests/test_zone_pair_registered_source.py', 'tests/test_zone_study_source_pinning.py',
    'tests/test_zone_own_executor_crate_review_j.py',
]
GROUPS = {'logic': TESTS[:6], 'integration': TESTS[6:9], 'pinning': TESTS[9:11],
          'review_j': TESTS[11:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--child', choices=GROUPS)
    args = parser.parse_args()
    if args.child:
        sys.path.insert(0, str(ROOT))
        for module in ('mujoco', 'torch', 'torchvision', 'openai', 'anthropic', 'google.genai'):
            sys.modules[module] = None
        def blocked(*args, **kwargs):
            raise AssertionError('T06 offline: network forbidden')
        socket.socket.connect = socket.socket.connect_ex = blocked
        import pytest
        return pytest.main(['-q', *GROUPS[args.child], '--junitxml=' + str(args.output / (args.child + '.xml'))])
    args.output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
    def run(group):
        command = [sys.executable, str(Path(__file__).resolve()), '--child', group, '--output', str(args.output)]
        with (args.output / (group + '.log')).open('w') as stream:
            proc = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        print(json.dumps({'group': group, 'exit_code': proc.returncode}), flush=True)
        return {'group': group, 'command': command, 'exit_code': proc.returncode}
    with ThreadPoolExecutor(max_workers=3) as pool:
        runs = list(pool.map(run, GROUPS))
    suites = [s for group in GROUPS for s in ET.parse(args.output / (group + '.xml')).getroot().findall('testsuite')]
    sources = ['harness/zone_crate_skill.py', 'harness/zone_crate_dispatch.py', 'harness/zone_pair_executor.py',
               'harness/zone_study_integration.py', *TESTS]
    result = {'scope': 'offline regression; physics/render/model calls 0; no host lock',
              'base_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'python': sys.version, 'runs': runs, 'exit_code': max(r['exit_code'] for r in runs),
              'tests': sum(int(s.get('tests', '0')) for s in suites),
              'failures': sum(int(s.get('failures', '0')) for s in suites),
              'errors': sum(int(s.get('errors', '0')) for s in suites),
              'skipped': sum(int(s.get('skipped', '0')) for s in suites),
              'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
              'raw': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(args.output.iterdir()) if p.suffix in ('.log', '.xml')}}
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
