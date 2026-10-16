import math
import importlib.util
import json
from pathlib import Path
from scripts import run_arena_wall_map as run
from harness.self_pulse_odom import command_odometry,model,profile_key


def test_plans_supported_sealed_and_reach_authored_own_goals():
    spec=importlib.util.spec_from_file_location('arena_plan',run.EXP/'code/plan.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for reverse in (False,True):
        plan=module.compile_route(reverse)
        assert _close(json.loads(json.dumps(plan)),json.loads((run.EXP/(plan['case']+'-plan.json')).read_text()))
        assert plan['end_command_s']<=180 and len(plan['milestones'])==8
        for cmd in plan['commands']:
            assert profile_key(cmd,False) in model()['profiles']
        assert all(sum((a-b)**2 for a,b in zip(m['predicted_pose'][:2],m['target_own_m']))<=.10**2
                   for m in plan['milestones'])


def test_gt_return_cannot_affect_recorded_commands(tmp_path):
    class Backend:
        now=1.3
        frame=0
        def __init__(self,*a,**k):self.commands=[]
        def reset(self,cap):pass
        def set_deadline(self,t):pass
        def issue(self,rid,action):issued.append(action)
        def capture(self):self.frame+=1
        def eval_sample(self):return {'pose':[999]*3,'contact':True}
        def advance_to(self,t):self.now=t
        def close(self):pass
    issued=[]
    result=run.acquire_case('forward',tmp_path/'episode','test',Backend)
    expected=json.loads((run.EXP/'forward-plan.json').read_text())['commands']
    moves=[a for a in issued if a['kind']=='mecanum']
    assert moves==[{k:v for k,v in c.items() if k not in ('t','leg')} for c in expected]
    assert result['status']=='RECORDED' and result['frames']==1801 and result['model_calls']==0


def test_calibration_has_empty_bins_and_rejects_nonfinite_scores():
    import sys
    import numpy as np
    import pytest
    # Load by path with sibling modules (common/replay) isolated from other experiment folders.
    from tests.isolated_code_dir import load
    m=load(run.EXP/'code','arena_score','score.py')
    r=m.calibration([.55,.55,.95],[1.,0.,1.])
    assert r['bins'][0]['n']==0 and r['bins'][0]['precision'] is None
    assert r['bins'][5]['n']==2 and r['bins'][5]['precision']==.5
    assert r['brier']==pytest.approx((.45**2+.55**2+.05**2)/3)
    assert 'ece' not in m.calibration([.2],[0.],probability=False)
    with pytest.raises(AssertionError):m.calibration([np.nan],[1.])


def _close(a,b):
    """Exact structure/ints/strings; floats to 1e-12 relative (Linux/macOS libm differ in the last ulp)."""
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(_close(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):return isinstance(b,(list,tuple)) and len(a)==len(b) and all(_close(x,y) for x,y in zip(a,b))
    if isinstance(a,float) or isinstance(b,float):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-15)
    return a==b
