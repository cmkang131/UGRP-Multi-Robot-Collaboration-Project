import ast
import hashlib
import json
from pathlib import Path
import pytest
from scripts import run_wall_parallax_strafe as run


def test_frozen_detector_and_copied_sources():
    f=json.loads((run.ROOT/'experiments/2026-10-07-wall-parallax/freeze.json').read_text())
    assert all(run.sha(run.ROOT/p)==h for p,h in f['hashes'].items())
    c=json.loads((run.EXP/'copied-sources.json').read_text())
    assert all(run.sha(run.ROOT/p)==v['sha256'] for p,v in c['files'].items())

@pytest.mark.parametrize('case',run.CASES)
def test_fixed_schedule_ignores_evaluation(tmp_path,case):
    class Fake:
        now=1.3
        commands=[]
        closed=False
        def __init__(self,*a,**k):self.n=0
        def reset(self,cap):return self.now
        def set_deadline(self,t):self.end=t
        def issue(self,rid,a):self.commands.append((self.now,a))
        def capture(self):self.n+=1
        def eval_sample(self):return {'robot_xyz_m':[999,999,999],'success':True}
        def advance_to(self,t):self.now=t
        def close(self):type(self).closed=True
    r=run.acquire_case(case,tmp_path/case,'test-sha',Fake)
    assert r['status']=='RECORDED' and r['frames']==181 and Fake.closed
    moves=[a for _,a in Fake.commands if a['kind']=='mecanum']
    assert len(moves)==8
    assert [a['left'] for a in moves]==[.65*run.CASES[case]['sign']]*4+[-.65*run.CASES[case]['sign']]*4
    assert all(a['duration_s']==.65 for a in moves)


def test_offline_scheduler_does_not_import_physics():
    src=Path(run.__file__).read_text()
    tree=ast.parse(src)
    assert not any(isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('sim.') for n in tree.body)
    assert 'idle_robot_contacts=\'off\'' in (run.ROOT/'sim/wall_parallax_strafe.py').read_text()


def test_builder_signature_before_physics():
    import inspect
    from sim.masterpi_drive_friction_v7 import build_world
    from sim import wall_parallax_strafe as backend
    node=next(n for n in ast.walk(ast.parse(Path(backend.__file__).read_text()))
              if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='build_world')
    # Exercise Python call admission without constructing a MuJoCo world.
    inspect.signature(build_world).bind(None,**{k.arg:None for k in node.keywords})
