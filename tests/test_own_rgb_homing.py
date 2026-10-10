import copy
import hashlib
import json
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from harness import own_rgb_homing as m
from harness import own_route_homing as route
from harness import own_route_reference as ref
from harness.active_camera import SEARCH
from test_own_route_traversed import prepared,frame


def synthetic(pose,points,descriptors):
    K=np.array([[500.,0,320],[0,500.,240],[0,0,1]])
    T=m.camera_pose(pose,SEARCH)
    uv,_=m.reprojection(points,T,K)
    f=m.Frame(int(pose[0]*1000),1.,np.array(pose),T,uv,descriptors,np.ones(len(points)),'synthetic')
    return f,K


def scene():
    rng=np.random.default_rng(5)
    T=m.camera_pose([0,0,0],SEARCH)
    xyz=rng.uniform([-.8,-.5,1.5],[.8,.5,3.],(90,3))@T[:3,:3].T+T[:3,3]
    return xyz,rng.integers(0,256,(90,32),dtype=np.uint8)


def test_metric_triangulation_and_pnp_not_unit_translation_or_inverse_yaw():
    xyz,d=scene();a,K=synthetic([0,0,0],xyz,d);b,_=synthetic([0,.3,.04],xyz,d)
    assert m.triangulate(a,b,K)>=80
    q,_=synthetic([.13,-.09,-.07],xyz,d)
    result=m.estimate(a,q,K,SEARCH)
    assert result['status']=='accepted'
    assert np.allclose(result['pose'],q.pose,atol=1e-4)
    assert result['inliers']>=80


def test_pure_rotation_cannot_invent_metric_depth_and_bad_geometry_rejects():
    xyz,d=scene();a,K=synthetic([0,0,0],xyz,d)
    # Same camera centre, only optical rotation: zero triangulation baseline.
    b=copy.deepcopy(a);b.camera[:3,:3]=a.camera[:3,:3]@cv2.Rodrigues(np.array([0.,.1,0]))[0]
    b.uv=m.reprojection(xyz,b.camera,K)[0]
    assert m.triangulate(a,b,K)==0
    assert m.estimate(a,b,K,SEARCH)['reason']=='insufficient_3d_matches'
    a.points={i:x for i,x in enumerate(xyz)}
    b.uv=np.random.default_rng(9).uniform([0,0],[640,480],(90,2))
    assert m.estimate(a,b,K,SEARCH)['status']=='rejected'


def test_default_off_does_not_touch_receiver_or_read_poison():
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    p=Poison();assert route.install(p) is p


class Bank:
    frames=[];home=[]
    def extract(self,*args):return None
    def add(self,f):return False
    def recognize(self,*args,**kw):return dict(status='rejected',reason='fixture')
    def snapshot(self):return {}


@pytest.mark.parametrize('loop',['off',m.OPTION])
def test_first_accelerated_frame_marker_and_off_full_bytes(monkeypatch,loop):
    a,_=prepared(monkeypatch);b,_=prepared(monkeypatch)
    route.install(b)
    assert json.dumps(frame(a),sort_keys=True)==json.dumps(frame(b),sort_keys=True)
    c,active=prepared(monkeypatch)
    ref.install(c,ref.Options(return_own_free_astar=True),traversed_free='footprint_history_v1')
    route.install(c,visual_homing=m.OPTION,visual_loop=loop,memory=Bank())
    _,trace=frame(c)
    assert active==[True]
    assert trace['visual_homing']['calls']==1
    assert trace['visual_homing']['executed']['receive']
    assert trace['visual_homing']['executed']['localize']
    assert trace['reference_navigation']['execution']['calls']==1


def test_return_gate_cannot_reuse_stale_or_unverified_match(monkeypatch):
    c,_=prepared(monkeypatch)
    ref.install(c,ref.Options(return_own_free_astar=True),traversed_free='footprint_history_v1')
    c.route={'samples':[{'pose':[0,0,0]}]}
    def base(p):c.cursor=1;return np.zeros(2)
    c._return_target=base
    route.install(c,visual_homing=m.OPTION,memory=Bank())
    c._homing_executed={};c._homing_verified=False
    c._return_target(np.zeros(3));assert c.cursor==0
    c._homing_verified=True;c._return_target(np.zeros(3));assert c.cursor==1
    c._homing_verified=False;c._return_target(np.zeros(3));assert c.cursor==0


def test_pose_correction_preserves_particle_spread_and_own_start(monkeypatch):
    c,_=prepared(monkeypatch)
    ref.install(c,ref.Options(return_own_free_astar=True),traversed_free='footprint_history_v1')
    g=c.explorer.memory.self_map
    g.poses=np.array([[.1,0,0],[.2,0,0]])
    g.pending_cov=np.array([np.eye(3),np.eye(3)*2])
    g.odom=SimpleNamespace(pose=[1,2,.2],covariance=np.eye(3))
    home=copy.deepcopy(c.graph.nodes[0]['pose']);before=np.linalg.norm(g.poses[1,:2]-g.poses[0,:2])
    s={'pose':[0,0,0],'frame_id':2}
    route.apply_pose(c,s,[1,2,.2],3,1)
    assert np.isclose(np.linalg.norm(g.poses[1,:2]-g.poses[0,:2]),before)
    assert np.allclose(np.linalg.eigvalsh(g.pending_cov),[[1,1,1],[2,2,2]])
    assert c.graph.nodes[0]['pose']==home


def test_registered_batch_inputs_and_options():
    from scripts import run_own_route_homing as runner
    assert len(runner.jobs('/not-running'))==24
    assert set(runner.CONDITIONS)=={'baseline','traversed','homing','loopclosure'}
    for condition in runner.CONDITIONS:
        b=runner.bundle(63001,'a'*40,condition,'stage')
        assert b['phase_budgets_s']=={'B_approach':270.,'return':270.}
        assert b['options']['visual_loop']==(m.OPTION if condition=='loopclosure' else 'off')
        assert b['options']['progress_lookahead']=='off'
