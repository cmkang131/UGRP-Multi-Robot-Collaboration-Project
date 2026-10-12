import copy
import math
import numpy as np
import pytest
from harness.e2e_b_partial_accept import Consensus, valid_fit, usable
from harness.e2e_b_partial import rect_corners
from harness.e2e18_bundle import SPEED4
from harness.e2e_rgb_gate import ArrivalGate, boundary
from harness.active_camera import SEARCH
from scripts.run_e2e_ownmap_live import bundle, ROOT


def fit(center=(1.,0.)):
    return dict(complete=False,estimated_from_partial=True,polygon=rect_corners(center,0.,(.4,.7)).tolist(),
        center=list(center),size_m=[.8,1.4],stats=dict(rms_m=.02,inlier_fraction=.9,pos_std_m=.02,yaw_std_deg=2.,
            iou=.9,patch_outside_fraction=.01,grid_cost=.001,second_cost=.002))


def ref(i):return dict(robot_id='r1',frame_id=i,t_sim=.4*i,sha256=str(i)*64)


def test_partial_needs_fresh_diverse_consistent_views():
    c=Consensus();f=fit()
    assert c.observe([f],ref(1),(0.,0.,0.)) is None
    assert c.observe([f],ref(1),(.1,0.,0.)) is None
    assert c.observe([f],ref(2),(0.,0.,0.)) is None
    got=c.observe([f],ref(3),(.04,0.,0.))
    assert got['complete'] is False and usable(got,'on_v1') and not usable(got)
    assert len(got['evidence_refs'])==2
    assert c.observe([fit((1.3,0.))],ref(4),(.08,0.,0.)) is None


@pytest.mark.parametrize('key,value',[('rms_m',.031),('iou',.8),('inlier_fraction',.5),('pos_std_m',float('nan')),('second_cost',.001)])
def test_residual_and_quality_rejected(key,value):
    f=fit();f['stats'][key]=value
    assert not valid_fit(f)


def test_size_and_ambiguity_rejected():
    f=fit();f['size_m']=[1.,1.4];assert not valid_fit(f)
    c=Consensus();assert c.observe([fit(),fit()],ref(1),(0,0,0)) is None


def test_boundary_and_arrival_accept_only_consensus(monkeypatch):
    from harness import e2e_b_partial as partial
    from harness import e2e_rgb_gate as gate
    monkeypatch.setattr(partial,'detect_partial',lambda *a,**k:[fit()])
    monkeypatch.setattr(gate,'geometric_match',lambda *a:dict(accepted=True,reason='verified'))
    rgb=np.zeros((480,640,3),np.uint8)
    assert boundary(rgb,SEARCH,(0,0,0),marker_detect=partial.OPTION) is None
    g=ArrivalGate('r1',option='rgb_geometry_v1',marker_detect=partial.OPTION,partial_accept='on_v1')
    for i in range(1,6):
        g.observe(ref=ref(i),rgb=rgb,servo=SEARCH,pose=(.04*(i-1),0,0),covariance=np.eye(3)*1e-6)
        if i==1:assert g.current['boundary'] is None
        if i==2:g.remember_B();assert g.references['B']['boundary']['complete'] is False
        verdict=g.verify('B',now=.4*i,target=(.04*(i-1),0))
    assert verdict['accepted']


def options():
    return dict(enabled=True,relook='on_v1',exploration_progress='frontier_progress_v1',pose_fix='innovation',
        path_follow='rpp_v1',dev_light=True,mapping_budget='case_cap_v1',wall_cap_s=25200.,
        stall_odometry='rgb_vo_us_v1',ultrasonic_front='on_v1',vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1',
        explore_deadlock='replan_v1',boundary_association='extent_v1',boundary_retry='navigation_v1',boundary_coverage='native_v1',
        boundary_views='standoff_fullquad_v1',b_marker_detect='partial_known_size_v1',speed3='adaptive_v1',speed4=SPEED4,
        b_partial_accept='on_v1')


def test_registered_bundle_seeds_and_runtime():
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    for seed in (61001,61006,61007,61012):
        b=bundle('a'*40,seed,'study_gemma4_31b_v1',**options())
        assert b['execution_bundle_id']=='e2e18-v216'
        require_current(b,ROOT)
        assert accepted_call_id(f'speed-gate-e2e18-v216-s{seed}-r1:call-0001-r1:1')
    with pytest.raises(ValueError):bundle('a'*40,61013,'study_gemma4_31b_v1',**options())
    b['speed4']['rbpf_particles']=99
    with pytest.raises(ValueError):require_current(b,ROOT)


def test_cached_static_views_and_fast_distance():
    from harness.e2e_speed5 import plan_views,using
    from harness.e2e_b_partial import rect_sd
    views=plan_views();assert len(views)==85
    altered=plan_views();altered[0]['pose'][0]=999
    assert plan_views()[0]['pose'][0]!=999
    points=np.random.default_rng(5).uniform(-2,2,(40,2))
    old=rect_sd(points,(.3,.2),.37,(.4,.7))
    with using('cache_v1'):new=rect_sd(points,(.3,.2),.37,(.4,.7))
    np.testing.assert_array_equal(old,new)


@pytest.mark.parametrize('mode,version',[('lean_v1',217),('lean_v2',218),('lean_v3',219)])
def test_speed5_registered_and_preserves_fit_quality(mode,version):
    from harness.e2e_runtime_registration import require_current
    from harness.e2e_speed5 import using
    from tests.test_e2e_b_partial import render
    from harness.e2e_b_partial import detect_partial
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',**options(),speed5=mode)
    assert b['execution_bundle_id']==f'e2e18-v{version}';require_current(b,ROOT)
    if version>=218:
        bad=copy.deepcopy(b);bad['opencv_threads']=16
        with pytest.raises(ValueError):require_current(bad,ROOT)
    with using(mode):
        for center,yaw in [((.9,.45),0.),((1.,.5),.07),((.95,-.5),-.09)]:
            got=detect_partial(render(np.array(center),yaw),SEARCH,(0,0,0))
            assert len(got)==1 and valid_fit(got[0])
            assert math.dist(got[0]['center_robot_m'],center)<.06
        assert detect_partial(render(np.array([.9,0.]),0.),SEARCH,(0,0,0))==[]


def test_squared_grid_cost_matches_distance_formula():
    from harness.e2e_speed5 import rectangle_grid_cost
    from harness.e2e_b_partial import rect_sd
    rng=np.random.default_rng(77)
    points=rng.uniform(-2,2,(81,2));centers=rng.uniform(-1,1,(51,2))
    for yaw in (.3,1.7):
        sd=rect_sd(points[None,:],centers[:,None],yaw,(.4,.7))
        for interior in (True,False):
            old=(np.minimum(np.maximum(sd,0) if interior else np.abs(sd),.06)**2).mean(axis=1)
            new=rectangle_grid_cost(points,centers,yaw,(.4,.7),.06,interior=interior)
            np.testing.assert_allclose(new,old,rtol=1e-12,atol=1e-15)


def test_float32_search_cost_remains_bounded():
    from harness.e2e_speed5 import rectangle_grid_cost,using
    rng=np.random.default_rng(4)
    for offset in (-3.,0.,3.):
        points=rng.uniform(-4,4,(80,2))+offset
        centers=rng.uniform(-1.2,1.2,(1681,2))+offset
        for interior in (False,True):
            ref=rectangle_grid_cost(points,centers,.97,(.4,.7),.06,interior=interior)
            with using('lean_v3'):got=rectangle_grid_cost(points,centers,.97,(.4,.7),.06,interior=interior)
            assert got.dtype==np.float32
            np.testing.assert_allclose(got,ref,rtol=1e-5,atol=1e-8)
