"""Compare reviewed integration bytes, frozen v64, and the working candidate."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.modules['mujoco'] = None


def forbidden(*args, **kwargs):
    raise AssertionError('review7 forbids network/model calls')


socket.socket.connect = socket.socket.connect_ex = forbidden
from tests.test_zone_study_multiturn import TimingTrial
from tests.test_zone_study_multiturn_properties import v64
from tests.test_zone_study_multiturn_review7 import run_review7

BASE = 'b454ad3ce63ac9182248ea751e8224ef13762e89'
source = subprocess.check_output(['git', 'show', BASE + ':harness/zone_study_integration.py'])
module = types.ModuleType('_review7_before')
module.__file__ = str(ROOT / 'harness/zone_study_integration.py')
sys.modules[module.__name__] = module
exec(compile(source, module.__file__, 'exec'), module.__dict__)


class Before(module.IntegratedTrial):
    sim_output_tokens = TimingTrial.sim_output_tokens


loader = v64.__wrapped__()
frozen = next(loader)
rows = []
try:
    for condition in ('no_comm', 'peer_ko', 'leader_ko', 'structured'):
        for first, horizon in [('claim', h) for h in (8., 12., 20.)] + [('continue', 8.), ('claim', 90.)]:
            row = {'condition': condition, 'first': first, 'horizon_s': horizon}
            for label, cls in [('before', Before), ('v64', frozen), ('after', None)]:
                trial, requests, result = run_review7(condition, horizon, trial_cls=cls, first=first)
                row[label] = {'end_reason': result.end_reason,
                              'pending_work_count': sum(link.job() is not None for link in trial.links.values()),
                              'refusals': sum(m['budget_refused'] for m in trial.scheduler.metrics.values()),
                              'send_count': trial.send_ledger.sends(),
                              'end_state': getattr(result, 'end_state', None)}
            if condition == 'no_comm':
                assert row['after']['end_reason'] == row['v64']['end_reason']
            rows.append(row)
finally:
    next(loader, None)
claim_rows = [r for r in rows if r['first'] == 'claim' and r['horizon_s'] < 90.]
assert len(claim_rows) == 12
assert all(r['before']['end_reason'] == 'budget_exhausted' and
           r['after']['end_reason'] == 'sim_horizon' for r in claim_rows)
record = {'source_commit': BASE, 'before_integration_sha256': hashlib.sha256(source).hexdigest(),
          'model_calls': 0, 'physics_steps': 0, 'review7_counterexamples': len(claim_rows),
          'rows': rows}
(Path(__file__).parent / 'review7-counterexamples-before.json').write_text(
    json.dumps(record, indent=2, ensure_ascii=False) + '\n')
print('review7 busy-horizon counterexamples: 12/12 reproduced before; 12/12 fixed')
