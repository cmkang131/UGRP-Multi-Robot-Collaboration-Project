"""Freeze P1 source; only upstream PR422 changes are allowed in old closure."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[3]
EXP=ROOT/'experiments/2026-10-09-goal-route-motion-audit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((ROOT/'experiments/2026-10-09-goal-route-preflight/freeze.json').read_text())
upstream='6ffa74dfcf004458e450fde5a897dc343bd13e1b'
changed={p for p,h in old['files'].items() if sha(ROOT/p)!=h}
assert changed=={'harness/zone_solo_cyan_path_heading.py'},changed
for p in changed:
    assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',f'{upstream}:{p}'],cwd=ROOT)
paths={ROOT/p for p in old['files']}
paths.update(EXP.glob('code/*.py'))
paths.update(ROOT/p for p in ('scripts/run_goal_route_motion_audit.py','tests/test_goal_route_motion_audit.py',
    'configs/simulation_workflows.d/goal-route-motion-audit.json','tests/test_s2_path_heading.py',
    'tests/test_path_heading_default.py','tests/fixtures/path_heading/command-contract.json'))
(EXP/'freeze.json').write_text(json.dumps(dict(preregistration='egomap59 README; same P1 gates',
    upstream=upstream,changed_previous_files=sorted(changed),motion_calibration_changed=False,
    files={str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}),indent=2)+'\n')
print('frozen',len(paths))
