"""T09b offline-only verification/mutations without a host lock (PR #328).

No source files are mutated. Each invocation writes a NEW output directory.
The ordinary baseline includes pinning and T09a dependencies; mutants run T09b.
"""
import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
TARGET = 'tests/test_zone_own_executor_observed_reroute.py'
RELATED = [TARGET, 'tests/test_zone_own_executor_door_routes.py',
           'tests/test_review_e2e_batch_i.py',
           'tests/test_pair_passage_plan.py', 'tests/test_zone_model_conventions.py',
           'tests/test_zone_pair_status.py', 'tests/test_zone_pair_registered_source.py',
           'tests/test_zone_study_source_pinning.py', 'tests/test_zone_study_protocol.py',
           'tests/test_ci_fast_path.py']


class NoPhysics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'glfw', 'torch', 'openai', 'anthropic', 'google'}:
            raise RuntimeError('T09b offline-only boundary: ' + fullname)


def no_network(event, args):
    if event == 'socket.connect':
        raise RuntimeError('T09b tests cannot connect to network')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mutations = ['ignore_observation', 'ignore_replan', 'skip_stop', 'ignore_messages', 'ignore_pair_failure',
                 'ignore_capture_age', 'ignore_future_capture', 'ignore_capture_order', 'ignore_cancel_capture']
    parser.add_argument('--mutation', default='none', choices=['none', 'suite', *mutations])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    record = {'mutation': args.mutation, 'python': sys.version,
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'load_start': os.getloadavg(), 'physics_steps': 0, 'render_calls': 0, 'model_calls': 0}
    record['pending_merge_head'] = subprocess.run(
        ['git', 'rev-parse', '-q', '--verify', 'MERGE_HEAD'], text=True,
        capture_output=True).stdout.strip() or None
    paths = ['harness/zone_observed_door_reroute.py', 'harness/zone_static_door_routes.py',
             'harness/zone_pair_status.py', 'harness/zone_study_protocol.py',
             'harness/zone_study_contract.py', 'scripts/run_ci_tests.py',
             *RELATED, str(Path(__file__).relative_to(ROOT))]
    for p in paths:
        if not (ROOT / p).is_file():
            raise ValueError('missing test/source: ' + p)
    sys.meta_path.insert(0, NoPhysics())
    sys.addaudithook(no_network)
    from scripts import agent_lock
    record['host_lock_acquired'] = False
    try:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        record['timing_sensitive_lock_seen'] = bool(held and held.get('timing_sensitive'))
        if record['timing_sensitive_lock_seen']:
            print('Warning: timing-sensitive host work; offline tests continue per PR #328', flush=True)
    except Exception as error:
        record['lock_status_warning'] = str(error)
    try:
        record['source_sha256'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
        from harness import zone_observed_door_reroute as rr
        source = (ROOT / 'harness/zone_observed_door_reroute.py').read_text()
        replacements = {
            'ignore_observation': ('for door in observation.blocked_doors:', 'for door in ():'),
            'ignore_replan': ('needs_replan = self.route is not None and self.route.passage_id in self._blocked',
                              'needs_replan = False'),
            'ignore_pair_failure': ("return self._fail('PAIR_NOT_SAFE', now_s)", 'pass'),
            'ignore_capture_age': ("return self._fail('STALE_OWN_CAPTURE', now_s)", 'pass'),
            'ignore_future_capture': ("return self._fail('FUTURE_OWN_CAPTURE', now_s)", 'pass'),
            'ignore_capture_order': ("return self._fail('NONINCREASING_OWN_CAPTURE', now_s)", 'pass'),
            'ignore_cancel_capture': ("return self._fail('PRE_CANCEL_OWN_CAPTURE', now_s)", 'pass'),
        }
        import pytest
        record['runs'] = []
        cases = ['none', *mutations] if args.mutation == 'suite' else [args.mutation]
        for case in cases:
            altered = source
            if case in replacements:
                before, after = replacements[case]
                assert source.count(before) == 1
                altered = source.replace(before, after)
            exec(compile(altered, rr.__file__, 'exec'), rr.__dict__)
            if case == 'skip_stop':
                rr.ObservedDoorReroute._stop = lambda self: 'stopped'
            elif case == 'ignore_messages':
                rr.delivered_blockages = lambda *args: ()
            targets = RELATED if case == 'none' else [TARGET]
            print('T09b case: ' + case, flush=True)
            code = int(pytest.main([
                *targets, '-q', '--tb=short', '-o', 'junit_family=xunit1',
                '--junitxml=' + str(args.output / (case + '.xml'))]))
            record['runs'].append({'mutation': case, 'exit_code': code})
            if case == 'none' and code:
                break  # A broken baseline cannot validate any mutation.
        if args.mutation == 'suite':
            record['exit_code'] = int(len(record['runs']) != len(cases) or any(
                r['exit_code'] != (0 if r['mutation'] == 'none' else 1) for r in record['runs']))
        else:
            record['exit_code'] = record['runs'][-1]['exit_code']
        return record['exit_code']
    finally:
        record['source_unchanged'] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
                                       for p, sha in record.get('source_sha256', {}).items())
        record['load_end'] = os.getloadavg()
        (args.output / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
