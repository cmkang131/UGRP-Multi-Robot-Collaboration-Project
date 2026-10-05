"""Reproduce D2 in fresh guarded processes without editing any runtime source.

Run with the existing project Python. The parent holds the shared test lock;
the child forbids physics/model imports and network calls. Normal GitHub CI
is unaffected and must run in full for this PR.
"""
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
REVIEWED = '823ca2ced2fb65e771ce2be9c08a2864e08db804'
TEST = 'tests/test_beam_initial_pose_plan.py'


def child(mode, args):
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in {'mujoco', 'glfw', 'torch', 'google', 'openai', 'anthropic'}:
                raise AssertionError('No physics/model import: ' + fullname)

    def refuse(*args, **kwargs):
        raise AssertionError('No network calls')

    sys.meta_path.insert(0, Block())
    socket.socket.connect = socket.create_connection = refuse
    sys.path.insert(0, str(ROOT))
    if mode != 'normal':
        from harness import beam_initial_pose_plan as bp
        original = bp.TeamFootprintV3
        part, target = mode.split(':')

        class MissingGeometry(original):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                for role, parts in self.carrier_parts.items():
                    if target == 'both' or target == role:
                        self.carrier_parts[role] = {
                            'carriers': [], 'arms': parts[:1], 'chassis': parts[1:],
                        }[part]

        bp.TeamFootprintV3 = MissingGeometry
    import pytest
    return pytest.main(args)


def run():
    sys.path.insert(0, str(ROOT))
    from scripts import agent_lock
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    merge = subprocess.run(['git', 'rev-parse', '--verify', 'MERGE_HEAD'], cwd=ROOT,
                           text=True, capture_output=True)
    merge_parent = merge.stdout.strip() if merge.returncode == 0 else None
    waiting = time.monotonic()
    while True:
        try:
            receipt = agent_lock.acquire(
                agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/beam-initial-pose-contract',
                purpose='PR315 D2 static regression and mutation checks; no physics',
                pid=os.getpid(), expected_minutes=3)
            break
        except RuntimeError:
            if time.monotonic() - waiting > 1200:
                raise
            print('Waiting for shared test lock', flush=True)
            time.sleep(5)
    (out/'lock.json').write_text(json.dumps(receipt, indent=2) + '\n')
    results = []

    def check(label, mode, files, expected):
        junit = out/(label + '.xml')
        cmd = [sys.executable, str(Path(__file__).resolve()), '--child', mode,
               *files, '-q', '--tb=short', '--disable-warnings', '--junitxml=' + str(junit)]
        with (out/(label + '.txt')).open('w') as log:
            result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'PYTHONPATH': str(ROOT),
                                         'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                                         'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'},
                                    timeout=180)
        cases = ET.parse(junit).findall('.//testcase')
        failed = [c.attrib['name'] for c in cases if c.find('failure') is not None]
        row = {'label': label, 'mutation': mode, 'returncode': result.returncode,
               'tests': len(cases), 'failures': failed, 'command': cmd,
               'errors': sum(c.find('error') is not None for c in cases)}
        results.append(row)
        (out/'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(label, 'exit', result.returncode, 'tests', len(cases), 'failures', len(failed), flush=True)
        assert result.returncode == expected and row['errors'] == 0, row

    try:
        # Original test bytes in a temporary sibling of tests/ keep ROOT intact.
        with tempfile.TemporaryDirectory(prefix='.t08a-d2-', dir=ROOT) as tmp:
            old = Path(tmp)/'test_before_d2.py'
            old.write_bytes(subprocess.check_output(['git', 'show', REVIEWED + ':' + TEST], cwd=ROOT))
            for mode in ('normal', 'carriers:both', 'arms:both'):
                check('before-' + mode.replace(':', '-'), mode, [str(old)], 0)
        check('after-related', 'normal', [TEST, 'tests/test_pair_passage_plan.py',
              'tests/test_zone_pair_registered_source.py', 'tests/test_zone_study_source_pinning.py',
              'tests/test_zone_pair_executor.py::test_destination_route_reaches_zone_b_and_uses_bounded_segments'], 0)
        for part in ('carriers', 'arms', 'chassis'):
            for role in ('both', 'end_neg', 'end_pos'):
                mode = part + ':' + role
                check('after-' + mode.replace(':', '-'), mode, [TEST], 1)
        fixed_names = ('test_formal_north_south_geometry_is_static_only',
                       'test_continuous_uncertainty_box_contains_original_and_all_carrier_sweeps',
                       'test_carrier_outer_corner_blocked_even_when_beam_and_centres_clear',
                       'test_carrier_approach_and_arm_blockers_outside_search')
        fixed = {c.attrib['name'] for c in ET.parse(out/'after-related.xml').findall('.//testcase')
                 if c.attrib['name'].startswith(fixed_names)}
        detected = {name for row in results if row['label'].startswith('after-')
                    for name in row['failures']}
        assert len(fixed) == 18 and fixed <= detected, sorted(fixed - detected)
        protected = json.loads((Path(__file__).parent/'BASELINE.json').read_text())['preserved_files']
        assert all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest() == r['sha256'] for r in protected)
        summary = {'reviewed_sha': REVIEWED, 'merged_main_parent': merge_parent,
            'fixed_cases_detecting_geometry_removal': sorted(fixed),
            'origin_main_observed': subprocess.check_output(
            ['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip(),
            'python': sys.version, 'protected_files_unchanged': len(protected),
            'sim_seconds': 0, 'physics_model_imports_blocked': True,
            'network_blocked': True, 'loadavg_after': os.getloadavg(),
            'tested_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                             (TEST, 'harness/beam_initial_pose_plan.py', str(Path(__file__).relative_to(ROOT)))}}
        (out/'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    finally:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        if held and held.get('pid') == os.getpid():
            released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
            (out/'released.json').write_text(json.dumps(released, indent=2) + '\n')


if __name__ == '__main__':
    if sys.argv[1] == '--child':
        sys.exit(child(sys.argv[2], sys.argv[3:]))
    run()
