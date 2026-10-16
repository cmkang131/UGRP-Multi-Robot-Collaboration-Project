"""Freeze previous source closure plus new adapter, assets and map definitions."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[3]
EXP=ROOT/'experiments/2026-10-09-goal-route-preflight'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((ROOT/'experiments/2026-10-09-goal-route-continuous/freeze.json').read_text())
assert all(sha(ROOT/p)==h for p,h in old['files'].items()),'previous frozen implementation changed'
paths={ROOT/p for p in old['files']}
for p in ('harness/cohort_host_error_guard.py','sim/goal_route_assets.py','scripts/run_goal_route_preflight.py',
          'tests/test_goal_route_preflight.py','tests/test_goal_route_continuous.py',
          'configs/simulation_workflows.d/goal-route-preflight.json'):
    paths.add(ROOT/p)
paths.update(EXP.glob('code/*.py'));paths.update(p for p in (EXP/'assets').rglob('*') if p.is_file())
paths.update((ROOT/'experiments/2026-10-09-goal-route-continuous/code').glob('*.py'))
# Registered geometry, robot, camera and initialization inputs are source too.
paths.update((ROOT/'maps/zones').glob('*.json'))
paths.update((ROOT/'configs').glob('*.json'))
record=dict(preregistration='acf9cc7e',user_retry='egomap58; same seeds and gates; previous 9 HOST faults not outcomes',
    unchanged_previous_closure_files=len(old['files']),files={str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)})
(EXP/'freeze.json').write_text(json.dumps(record,indent=2)+'\n')
print('frozen',len(paths))
