"""Create (never overwrite) the 90 s v64 control used by the PR #245 regression.

Run from the repo with its existing Python environment. Only the integration
module comes from the pinned commit; shared dependencies and the fake clock /
wire come from the current checkout. This is not a historical full-run replay.
No model, network, simulator, physical step or Git write is permitted here.
"""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tests import test_zone_study_multiturn as fixture

BASE = '97f91cb040bf382973ce84b24b1ca8399e64a6fb'


def refuse(*args, **kwargs):
    raise AssertionError('network forbidden in v64 control')


def main():
    original = subprocess.run(['git', 'show', f'{BASE}:harness/zone_study_integration.py'],
                              cwd=ROOT, check=True, capture_output=True).stdout
    legacy = types.ModuleType('_zone_study_v64_wait_control')
    legacy.__file__ = str(ROOT / 'harness/zone_study_integration.py')
    sys.modules[legacy.__name__] = legacy
    exec(compile(original, legacy.__file__, 'exec'), legacy.__dict__)

    class LegacyTimingTrial(legacy.IntegratedTrial):
        sim_output_tokens = fixture.TimingTrial.sim_output_tokens

        def __init__(self, *args, decision_limits=None, **kwargs):
            super().__init__(*args, **kwargs)

    rows = {}
    with patch.object(socket.socket, 'connect', refuse), patch.object(socket.socket, 'connect_ex', refuse), \
            patch.dict(sys.modules, {'mujoco': None}), patch.object(fixture, 'TimingTrial', LegacyTimingTrial):
        for condition in fixture.zi.MAIN_CONDITIONS:
            trial, clock, links, requests = fixture.make_trial(
                condition, first='wait', send=False, follow_claim=False)
            fixture.advance(trial, clock, links, 90.)
            rows[condition] = fixture.wait_control_record(trial, requests)
    data = {'scope': 'v64 integration source-level control; shared current dependencies; fake clock/wire',
            'base_sha': BASE, 'integration_source_sha256': hashlib.sha256(original).hexdigest(),
            'horizon_s': 90., 'model_calls': 0, 'physics_steps': 0, 'conditions': rows}
    path = Path(__file__).with_name('v64_wait_90s.json')
    with path.open('x') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    assert json.loads(path.read_text()) == data
    for condition, row in rows.items():
        print(condition, [r['sim_s'] for r in row['requests'] if r['actor'] == 'r1'])


if __name__ == '__main__':
    main()
