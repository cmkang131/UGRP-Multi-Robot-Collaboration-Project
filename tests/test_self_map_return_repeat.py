import copy,hashlib,importlib.util,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness import self_map_return_repeat as repeat
from harness import self_map_closed_loop as legacy
from harness.active_camera import SEARCH

ROOT=Path(__file__).parents[1]


def fixture(module):
    f=json.loads((ROOT/'tests/fixtures/own_map_tempering/golden.json').read_text())
    c=module.RememberedGoal(SimpleNamespace(robot_id='r3',started=0.),seed=49001)
    c.last_snapshot=dict(t=1.,frame_id=1,grid=f['grid'],ledger=[dict(t=1.)])
    return c


def test_default_off_identity_and_registered_bundle_workflow():
    class Poison:
        def __getattribute__(self,name):raise AssertionError('off reads object')
    obj=Poison();assert repeat.attach(obj) is obj
    with pytest.raises(ValueError):repeat.attach(obj,map_utility='bad')
    from scripts.run_own_map_return_repeat import SEEDS,bundle
    from sim.workflow_manager import plan
    for seed in SEEDS:
        b=bundle(seed,'a'*40)
        assert b['case_cap_s']==630. and b['schedule']==dict(explore_s=360.,suffix_cap_s=270.,relocalize_dev_timeout_s=60.)
        assert b['options']['navigation_start']=='navfn_recovery_v1'
        assert b['options']['wall_texture']=='tape_v1' and b['options']['camera_pose']=='SEARCH'
        assert b['options']['graph_acceleration']=='match_cache_v1'
    with pytest.raises(ValueError):bundle(43001,'a'*40)
    p=plan(ROOT,'own-map-return-repeat',['--seed','49001','--output','/tmp/not-executed-egomap49','--expected-source-sha','a'*40])
    assert 'scripts.run_own_map_return_repeat' in p['command']


def test_360_loss_excludes_frame_and_retains_prefix(monkeypatch):
    c=fixture(legacy);c.__class__=repeat.Return360
    c.goal=dict(center_m=[.5,.5],candidate_id='self-B',first_t=12.,t_sim=15.)
    assert not c.loss_due(359.8) and c.loss_due(360.)
    c.last_snapshot['t']=359.8
    monkeypatch.setattr(legacy,'own_measurement',lambda *a:pytest.fail('loss frame used'))
    _,trace=c.receive(robot_id='r3',t=360.,frame_id=1801,rgb=None,servo=SEARCH,observation={},frame_sha256='b'*64)
    assert trace['status']=='unknown_start_reset' and c.inputs==[]
    assert c.snapshot['grid']==c.last_snapshot['grid'] and c.snapshot['t']<c.loss_t
    assert c.pf.n==100000 and np.ptp(c.pf.px[:,2])>6.
    assert type(c.navigator).__name__=='StartCycleNavigator'
    assert c.events[-1]['first_confirmation_t']==15. and c.events[-1]['t']==360.
    c.goal['t_sim']=361.
    with pytest.raises(AssertionError):c.lose(360.,1801)


def test_original_egomap43_outputs_particles_rng_byte_identical(monkeypatch):
    f=ROOT/'tests/fixtures/own_map_return_repeat/egomap43_closed_loop.py'
    provenance=json.loads((f.parent/'provenance.json').read_text())
    assert hashlib.sha256(f.read_bytes()).hexdigest()==provenance['sha256']
    spec=importlib.util.spec_from_file_location('original43',f);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    outputs=[]
    for module in (old,legacy):
        c=fixture(module);c.goal=dict(center_m=[.5,.5],obs_id='own',t_sim=1.)
        c.lose(2.,2)
        monkeypatch.setattr(module,'own_measurement',lambda *a:dict(points=[],columns=[],uv=[]))
        monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
        monkeypatch.setattr(module,'pulse_command',lambda *a,**kw:(dict(t=a[1],kind='hold'),{}))
        seq=[]
        for i in range(3):
            cmd,trace=c.receive(robot_id='r3',t=2.2+i*.2,frame_id=3+i,rgb=np.zeros((2,2,3),np.uint8),servo=SEARCH,
                observation=dict(floor_xy=[],camera=[.1,0]),frame_sha256='b'*64)
            c.command(cmd);seq.append(trace)
        outputs.append((json.dumps(dict(trace=seq,inputs=c.inputs,events=c.events,rng=c.pf.rng.bit_generator.state),sort_keys=True),c.pf.px.tobytes(),c.pf.logw.tobytes()))
    assert outputs[0]==outputs[1]


def test_unchanged_five_frame_arrival_and_point_two_boundary(monkeypatch):
    c=fixture(legacy);c.__class__=repeat.Return360
    c.goal=dict(center_m=[.5,.5],candidate_id='own',first_t=1.,t_sim=1.)
    c.lose(360.,1801)
    monkeypatch.setattr(legacy,'own_measurement',lambda *a:dict(points=[],columns=[],uv=[]))
    monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
    monkeypatch.setattr(c.pf,'step',lambda **kw:dict(pose=[.7,.5,0.],resolved=True,global_std_xy_m=.03))
    monkeypatch.setattr(legacy,'pulse_command',lambda *a,**kw:(dict(t=a[1],kind='hold'),{}))
    for i in range(5):
        cmd,r=c.receive(robot_id='r3',t=360.2+i*.2,frame_id=1802+i,rgb=np.zeros((2,2,3),np.uint8),servo=SEARCH,
            observation=dict(floor_xy=[],camera=[.1,0]),frame_sha256='b'*64)
        assert r['declared_goal']==(i==4)
    assert cmd['kind']=='hold'


def test_evaluation_nees_and_failure_denominators():
    path=ROOT/'experiments/2026-10-08-own-map-return-repeat/code/report.py'
    spec=importlib.util.spec_from_file_location('report49',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.nees([.2,.3],np.diag([.04,.09,1]))==pytest.approx(2.)
    assert m.nees([1,0],np.zeros((3,3))) is None
    base=dict(status='RECORDED',observed=True,arrived=False,false_declarations=0,end_error=.1,correct_convergence=True)
    assert m.classify(**base)=='path_or_budget'
    assert m.classify(**dict(base,observed=False))=='exploration_not_covered'
    assert m.classify(**dict(base,status='HOST_ERROR'))=='other'
    assert m.classify(**dict(base,end_error=.26))=='localization'
    assert m.classify(**dict(base,arrived=True,end_error=.8))=='success'
