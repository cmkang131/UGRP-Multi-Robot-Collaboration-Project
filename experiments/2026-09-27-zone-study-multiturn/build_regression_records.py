"""Serialize the unit-test fixture trace, with the main v64 integration as a control.

No model or physics. v64's integration module is read from the pinned Git commit
and loaded in memory; the shared scheduler/client remain the working versions.
This is a source-level counterfactual, not a rerun of the old physical cohort.
"""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests import test_zone_study_multiturn as fixture

BASE = '97f91cb040bf382973ce84b24b1ca8399e64a6fb'


def refuse(*args, **kwargs):
    raise AssertionError('network forbidden')


def record(condition, first, boundary):
    trial, clock, links, requests = fixture.make_trial(condition, first=first)
    fixture.advance(trial, clock, links, 27., boundary=boundary)
    result = trial.finish(27.)
    return {'condition': condition, 'first_action': first, 'synthetic_boundary_s': boundary,
            'sim_cost_profile': trial.params.to_dict(), 'model_calls': 0, 'physics_steps': 0,
            'fake_wire_requests': len(requests), 'calls': [c.to_dict() for c in trial.scheduler.calls],
            'messages': [m.to_dict() for m in trial.scheduler.messages],
            'inputs': trial.input_log, 'dispatch': trial.dispatch_log,
            'decision_events': getattr(trial.scheduler, 'decision_events', None),
            'trace': list(result.trace)}


def main():
    original = subprocess.run(['git', 'show', f'{BASE}:harness/zone_study_integration.py'],
                              cwd=ROOT, check=True, capture_output=True, text=True).stdout
    legacy = types.ModuleType('_zone_study_integration_v64_control')
    legacy.__file__ = str(ROOT / 'harness/zone_study_integration.py')
    sys.modules[legacy.__name__] = legacy
    exec(compile(original, legacy.__file__, 'exec'), legacy.__dict__)
    current = fixture.TimingTrial

    class LegacyTimingTrial(legacy.IntegratedTrial):
        sim_output_tokens = current.sim_output_tokens

        def __init__(self, *args, decision_limits=None, **kwargs):
            super().__init__(*args, **kwargs)

    rows = {}
    with patch.object(socket.socket, 'connect', refuse), patch.object(socket.socket, 'connect_ex', refuse), \
            patch.dict(sys.modules, {'mujoco': None}):
        for version, cls in [('v64_control', LegacyTimingTrial), ('v66_candidate', current)]:
            fixture.TimingTrial = cls
            rows[version] = [record(c, first, boundary)
                             for c in fixture.zi.MAIN_CONDITIONS
                             for first, boundary in [('claim', 20.), ('wait', None)]]
    fixture.TimingTrial = current
    data = {'scope': 'unit-test fixtures only; not an experiment or language/physical success result',
            'base_sha': BASE, 'v64_integration_source_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'v66_bundle': fixture.zi.EXECUTION_BUNDLE_ID, 'rows': rows}
    # v1 is retained as a diagnostic: its fake clock did not expire legacy hold
    # jobs. v2 advances those own timers and is the valid no_comm timing control.
    for before, after in zip(rows['v64_control'][:2], rows['v66_candidate'][:2]):
        signature = lambda row: [(c['actor'], c['started_sim_s'], c['finished_sim_s']) for c in row['calls']]
        assert signature(before) == signature(after), 'no_comm timing changed'
    path = Path(__file__).with_name('regression-traces-v2.json')
    with path.open('x') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    assert json.loads(path.read_text()) == data
    for version, records in rows.items():
        print(version, [(r['condition'], r['first_action'], r['fake_wire_requests'],
                         sum(bool(d['ack'] and not d['ack']['accepted']) for d in r['dispatch'])) for r in records])


if __name__ == '__main__':
    main()
