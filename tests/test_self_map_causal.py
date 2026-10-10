import copy
import importlib.util
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest
from harness.self_map_causal import snapshot_before, own_landmarks_before, landmark_object, before, after
from harness.self_map_relocalize import Relocalizer
from harness.own_map_amcl_vendor import landmarks as lm
from harness.self_map_landmark_sensor import Sensor


def test_snapshot_prefix_and_future_append_invariance():
    row=dict(t=9.,frame_id=3,view='online_frontend',grid=dict(robot_id='r3',cells=[[0,0,1]]),ledger=[dict(t=9.)])
    future=copy.deepcopy(row);future['t']=11.;future['grid']['cells']=[[99,99,100]]
    assert snapshot_before([row,future],10.,robot_id='r3')==row
    assert snapshot_before([row],10.,robot_id='r3')==row
    out=snapshot_before([row],10.,robot_id='r3');out['grid']['cells'].clear()
    assert row['grid']['cells']
    bad=copy.deepcopy(row);bad['ledger'][0]['t']=12.
    with pytest.raises(ValueError,match='FUTURE'):snapshot_before([bad],10.,robot_id='r3')
    with pytest.raises(ValueError,match='OWN_ONLINE'):snapshot_before([row],10.,robot_id='r2')
    assert not before(10.,10.) and not after(10.,10.)
    assert before(9.8,10.) and after(10.2,10.)


def test_causal_landmarks_no_hindsight_no_static_reconstruction():
    edge=dict(kind='floor_line',endpoints=[[1,0],[1,.2]],normal=[1,0],hue=110.)
    door=dict(kind='door',center=[2,0],width=.5)
    measurement=dict(robot_id='r3',t=9.,frame_id=3,frame_sha256='a'*64,features=[edge,door])
    pose=dict(t=9.,frame_id=3,pose=[2.,3.,np.pi/2],covariance=np.eye(3).tolist())
    future=dict(robot_id='r3',t=11.,frame_id=4,features=[dict(kind='bad')])
    out=own_landmarks_before([measurement,future],[pose],10.,robot_id='r3')
    assert out==own_landmarks_before([measurement],[pose],10.,robot_id='r3')
    assert len(out['edges'])==1 and out['edges'][0]['partial_extent']
    np.testing.assert_allclose(out['edges'][0]['a'],[2,4])
    np.testing.assert_allclose(out['edges'][0]['b'],[1.8,4])
    np.testing.assert_allclose(out['edges'][0]['normal'],[0,1],atol=1e-15)
    np.testing.assert_allclose(out['doors'][0]['center'],[2,5])
    assert out['world_alignment'] is None
    assert out['edges'][0]['source']['obs_id']=='r3-obs-000003'
    with pytest.raises(ValueError,match='PEER'):own_landmarks_before([{**measurement,'robot_id':'r2'}],[pose],10.,robot_id='r3')


def test_exact_s2_partial_line_and_door_measurement():
    mapped=lm.MapFeatures(dict(regions=dict(B=dict(center_m=[4.,0.],half_extents_m=[1.,1.],rgba=[.2,.4,.95,.3])),passages=[dict(kind='door',center_m=[2.,0.],width_m=.5)]))
    z=[dict(kind='door',center=[2.,0.],width=.5)]
    score=lm.landmark_likelihood(mapped,np.array([[0.,0.,0.],[0.,1.,0.]]),z)
    p=lm.PARAMS
    expected=(1-p['random_fraction'])*lm.gaussian(0,p['sigma_range_m'])*lm.gaussian(0,p['sigma_bearing_rad'])*lm.gaussian(0,p['sigma_width_m'])+p['random_fraction']/(p['max_range_m']*2*np.pi*p['door_width_m'][1])
    assert score[0]==pytest.approx(expected) and score[0]>100*score[1]
    cm=NS(origin=np.array([0.,0.,1.]),_rot=np.diag([1.,-1.,-1.]))
    K=np.array([[200.,0.,160.],[0.,200.,120.],[0.,0.,1.]])
    image=np.full((240,320,3),130,np.uint8);image[:,:160]=[150,130,110]
    got=lm.floor_features(image,cm,np.linalg.inv(K),mapped,np.ones((240,320),bool))
    assert len(got)==1 and got[0]['normal'][0]<-.99
    assert lm.floor_features(image,cm,np.linalg.inv(K),mapped,np.zeros((240,320),bool))==[]


def grid():
    return dict(resolution_m=.1,cells=[[x,y,1 if x in (0,19) or y in (0,19) else -1] for x in range(20) for y in range(20)])


def test_default_and_explicit_off_full_prediction_rng_bytes():
    path=Path(__file__).parents[1]/'tests/fixtures/self_map_relocalize_before_landmarks.py.txt'
    loader=SourceFileLoader('prior_egomap41_relocalize',str(path));spec=importlib.util.spec_from_loader(loader.name,loader)
    old=importlib.util.module_from_spec(spec);loader.exec_module(old)
    ps=[old.Relocalizer(grid(),seed=42),Relocalizer(grid(),seed=42),Relocalizer(grid(),seed=42,sensor_landmarks='off',landmark_map='must_not_read')]
    servo={3:740,4:2320,5:1320,6:1500}
    for i,delta in enumerate([[0,0,0],[0,0,0],[.3,0,.3]]):
        results=[p.step(t=i,points=[[1,0],[1,.2]],delta=delta,servo=servo,**({'features':object()} if j else {})) for j,p in enumerate(ps)]
        assert len({json.dumps(r,sort_keys=True).encode() for r in results})==1
        assert len({p.px.tobytes() for p in ps})==1
        assert len({p.logw.tobytes() for p in ps})==1
        assert len({json.dumps(p.rng.bit_generator.state,sort_keys=True) for p in ps})==1


def test_floor_only_packet_and_unchanged_motion_gate():
    mapped=landmark_object(dict(edges=[],doors=[dict(center=[1,1],width=.5)]))
    p=Relocalizer(grid(),seed=42,sensor_landmarks=lm.OPTION,landmark_map=mapped)
    z=[dict(kind='door',center=[.3,0],width=.5)];servo={3:740,4:2320,5:1320,6:1500}
    r=p.step(t=0,points=[],delta=[0,0,0],servo=servo,features=z)
    assert r['updated'] and r['updates']==1
    r=p.step(t=.2,points=[],delta=[0,0,0],servo=servo,features=z)
    assert not r['updated']
    with pytest.raises(ValueError):Relocalizer(grid(),seed=42,sensor_landmarks='bad')
    with pytest.raises(ValueError):Relocalizer(grid(),seed=42,sensor_landmarks=lm.OPTION)


def test_command_camera_clear_mask_no_native_calls_or_fake_doors(monkeypatch):
    import mujoco
    def forbidden(*a, **k):
        raise AssertionError('OFFLINE_NATIVE_CALL_FORBIDDEN')
    for name in ('MjModel','MjData','Renderer','mj_step','mj_forward','mj_kinematics'):
        monkeypatch.setattr(mujoco, name, forbidden)
    sensor=Sensor([110.]);servo={1:2000,3:740,4:2320,5:1320,6:1500}
    blank=np.full((480,640,3),130,np.uint8)
    assert sensor.measure(blank,servo,dict(columns=[],uv=[]))==[]


def test_egomap41_judgment_block_is_unchanged():
    root=Path(__file__).parents[1]/'experiments'
    old=(root/'2026-10-08-own-map-utility/code/score.py').read_text()
    new=(root/'2026-10-08-own-map-causal-landmarks/code/score.py').read_text()
    start='    own = [r for r in out'
    end='    maps = {}'
    assert old[old.index(start):old.index(end)]==new[new.index(start):new.index(end)]
    for fragment in ['correct = (xy<=.25)&(yaw<=math.radians(10))',
                     "if i>=4 and r['stable_resolved'] and correct[i-4:i+1].all()"]:
        assert fragment in new and fragment in old


def test_future_goal_is_not_available_at_loss():
    root=Path(__file__).parents[1]
    path=root/'experiments/2026-10-08-own-map-utility/code/replay.py'
    spec=importlib.util.spec_from_file_location('egomap41_goal',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    c=dict(state='locally_confirmed_region',confirmed_t=72.1,id=6,center_m=[-1.4,2.8],
           observations=11,first_t=70.1,bounds_m=[[-1.9,2.1],[-1.1,3.4]],confidence=.54)
    row=dict(t=72.1,frame_id=355,goal=dict(robot_id='r3',coordinate_frame='r3/own_odom',candidates=[c]))
    frames={355:dict(sha256='a'*64)}
    assert m.remembered_goal([r for r in [row] if before(r['t'],61.3)],frames) is None
    assert m.remembered_goal([r for r in [row] if before(r['t'],91.3)],frames)['obs_id']=='r3-obs-000355'
