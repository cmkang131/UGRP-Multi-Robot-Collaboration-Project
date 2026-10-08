import copy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness import self_map_closed_loop as m
from harness.active_camera import SEARCH


def fixture():
    f=json.loads((Path(__file__).parent/'fixtures/own_map_tempering/golden.json').read_text())
    explorer=SimpleNamespace(robot_id='r3',started=0.)
    controller=m.attach(explorer,map_utility=m.OPTION,seed=43001)
    controller.last_snapshot=dict(t=1.,frame_id=1,grid=f['grid'],ledger=[dict(t=1.)])
    controller.measurements=[dict(robot_id='r3',t=1.,frame_id=1,frame_sha256='a'*64,
        features=[dict(kind='floor_line',endpoints=[[1,0],[1,1]],normal=[-1,0],hue=112)])]
    controller.poses=[dict(t=1.,frame_id=1,pose=[.2,.3,.4],covariance=np.eye(3).tolist())]
    return controller


def test_default_off_exact_identity_no_reads():
    class Poison:
        def __getattribute__(self,name):raise AssertionError('off touched explorer')
    legacy=Poison()
    assert m.attach(legacy) is legacy and m.attach(legacy,map_utility='off') is legacy
    with pytest.raises(ValueError):m.attach(legacy,map_utility='bad')


def test_loss_is_uniform_prefix_copy_and_suffix_command_only(monkeypatch):
    c=fixture();old=copy.deepcopy(c.last_snapshot)
    c.lose(2.,2)
    assert c.snapshot['grid']==old['grid'] and c.snapshot['landmarks']['future_observations']==0
    assert c.pf.n==100000 and np.ptp(c.pf.px[:,2])>6.
    assert c.pf.likelihood_tempering=='pr_likelihood_half_v1'
    c.last_snapshot['grid']['cells'][0][2]=1234
    assert c.snapshot['grid']==old['grid']
    c.command(dict(t=2.,kind='hold'))
    assert np.array_equal(c.odom.advance(2.2),[0,0,0])
    assert max(e['source']['t'] for e in c.snapshot['landmarks']['edges'])<2.


def test_loss_frame_never_enters_sensor_or_map(monkeypatch):
    c=fixture();c.goal=dict(center_m=[0,0])
    monkeypatch.setattr(m,'own_measurement',lambda *a:pytest.fail('loss frame used'))
    cmd,r=c.receive(robot_id='r3',t=90.,frame_id=2,rgb=None,servo=SEARCH,observation={},frame_sha256='b'*64)
    assert cmd['kind']=='hold' and c.stage=='relocalize' and len(c.measurements)==1 and c.inputs==[]


def test_only_own_confirmed_B_and_internal_five_frames_declare(monkeypatch):
    c=fixture()
    c.goal=dict(center_m=[.5,.5],obs_id='r3-obs-000001',t_sim=1.)
    c.lose(2.,2)
    monkeypatch.setattr(m,'own_measurement',lambda *a:dict(points=[],columns=[],uv=[]))
    monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
    monkeypatch.setattr(c.pf,'step',lambda **kw:dict(pose=[.5,.5,0.],resolved=True,global_std_xy_m=.03))
    monkeypatch.setattr(m,'pulse_command',lambda *a,**kw:(dict(t=a[1],kind='hold'),{}))
    args=dict(robot_id='r3',rgb=np.zeros((2,2,3),np.uint8),servo=SEARCH,
        observation=dict(floor_xy=[],camera=[.1,0]),frame_sha256='b'*64)
    frozen=json.dumps(c.snapshot,sort_keys=True)
    for i in range(5):
        cmd,r=c.receive(t=2.2+i*.2,frame_id=3+i,**args)
        assert r['declared_goal']==(i==4)
    assert c.stage=='declared' and cmd['kind']=='hold'
    assert json.dumps(c.snapshot,sort_keys=True)==frozen
    assert c.inputs[0]['delta']==[0,0,0]


def test_unobserved_goal_and_dev_light_timeout_not_success(monkeypatch):
    c=fixture();c.lose(2.,2)
    monkeypatch.setattr(m,'own_measurement',lambda *a:dict(points=[],columns=[],uv=[]))
    monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
    monkeypatch.setattr(c.pf,'step',lambda **kw:dict(pose=[.5,.5,0.],resolved=False,global_std_xy_m=.3))
    monkeypatch.setattr(m,'pulse_command',lambda *a,**kw:(dict(t=a[1],kind='hold'),{}))
    _,r=c.receive(t=62.,frame_id=3,robot_id='r3',rgb=np.zeros((2,2,3),np.uint8),servo=SEARCH,
        observation=dict(floor_xy=[],camera=[.1,0]),frame_sha256='b'*64)
    assert not r['declared_goal'] and c.stage=='goal_unobserved'
    assert c.events[-1]['reason']=='would_stop_unresolved' and c.goal is None


def test_live_sensor_same_frozen_egomap42_measurement():
    # Real cached RGB check: no simulation/GT/native model constructed.
    import cv2
    ep=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
    if not ep.exists():pytest.skip('local raw RGB unavailable')
    frames=[json.loads(l) for l in (ep/'robots/r3/frames.jsonl').read_text().splitlines()]
    row=json.loads((Path(__file__).parent/'fixtures/own_map_tempering/golden.json').read_text())['sequence'][0]
    f=next(x for x in frames if x['frame_id']==row['frame_id'])
    bgr=cv2.imread(str(ep/f['path']));servo={int(k):v for k,v in row['servo'].items()}
    points=m.own_measurement(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),servo)
    features=m.Sensor(m.HUES).measure(bgr,servo,points)
    assert np.allclose(points['points'],row['points'],atol=1e-12)
    assert json.dumps(features,sort_keys=True)==json.dumps(row['features'],sort_keys=True)


def test_managed_workflow_and_frozen_bundle():
    from scripts.run_own_map_goal_dev import bundle
    from sim.workflow_manager import plan
    root=Path(__file__).parents[1];out='/tmp/egomap43-test-plan-no-execution'
    record=plan(root,'own-map-goal-dev',['--output',out,'--expected-source-sha','a'*40])
    assert 'scripts.run_own_map_goal_dev' in record['command']
    b=bundle('a'*40)
    assert b['task']['seed']==43001 and b['case_cap_s']==360.
    assert b['options']['wall_texture']=='tape_v1' and b['options']['camera_pose']=='SEARCH'


def test_egomap34_exact_detector_bytes_and_explicit_source_admission():
    import hashlib
    from test_wall_contact_types import test_active_detector_off_nonempty_real_rgb_frozen_bytes
    test_active_detector_off_nonempty_real_rgb_frozen_bytes()
    root=Path(__file__).parents[1]
    manifest=json.loads((root/'experiments/2026-10-08-own-map-closed-loop/detector-off-admission.json').read_text())
    for name,r in manifest['files'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==r['current_sha256']
        assert hashlib.sha256((root/r['original_fixture']).read_bytes()).hexdigest()==r['original_sha256']
