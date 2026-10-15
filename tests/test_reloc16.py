import math
from types import SimpleNamespace
import numpy as np
import pytest
from harness.reloc16_compass import certify_points,axis_wrap,CompassHeading


def points_for_wall(yaw=0.):
    # Orthographic-looking horizontal wall line in a downward-facing camera.
    # Camera x maps body-left, camera y maps body-down, camera z maps forward.
    K=np.array([[400.,0.,320.],[0.,400.,240.],[0.,0.,1.]])
    R=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
    c,s=math.cos(yaw),math.sin(yaw);R=np.array([[c,-s,0],[s,c,0],[0,0,1.]])@R
    uv=np.column_stack([np.linspace(15,625,96),np.full(96,80.)])
    return uv,K,R


def test_disjoint_background_support_recovers_small_yaw_and_axis_ambiguity():
    p,K,R=points_for_wall(math.radians(12))
    out=certify_points(p,K,R,residual_px=1.5,min_columns=6)
    assert out['status']=='measured'
    assert abs(axis_wrap(out['axis_yaw_rad']+math.radians(12)))<1e-8
    assert out['spatial_blocks']>=2 and out['spatial_consistent']


def test_only_foreground_or_one_spatial_block_remains_unknown():
    p,K,R=points_for_wall();p=p[(p[:,0]>170)&(p[:,0]<300)]
    out=certify_points(p,K,R,residual_px=1.5,min_columns=6)
    assert out['status']=='unknown_static_support'
    assert out['null_hypothesis_retained']


def test_hypotheses_across_axis_boundary_do_not_create_unobserved_midpoint():
    assert axis_wrap(math.radians(89.9))==pytest.approx(math.radians(-.1))
    assert axis_wrap(math.radians(-89.9))==pytest.approx(math.radians(.1))


def test_null_pending_and_delayed_acceptance_do_not_reset_xy_or_metric_age(monkeypatch):
    import harness.reloc16_compass as m
    # Isolate temporal fusion contract from the real image/calibration detector.
    h=object.__new__(CompassHeading)
    h.sample_s=.2;h.servo={1:1500};h.servo_since=0.;h.last_t=None;h.last_hash=None
    h.pending=None;h.command_total=0.;h.accepted=0;h.last_measurement_t=None;h.wall_tracking_v1=False
    h.mp=SimpleNamespace(undistort=lambda x:x,column_positions=lambda *a:np.arange(96),K_INV=np.eye(3))
    h.p={'min_run_columns':6};h.calibration={'line_residual_px_p95':1.5}
    monkeypatch.setattr(m,'contacts',lambda *a:np.zeros((96,2)))
    monkeypatch.setattr(m,'commanded_rotation',lambda *a:np.eye(3))
    def obs(*a,**k):return dict(status='measured',axis_yaw_rad=.02,uncertainty_bound_rad=.01,sigma_yaw=.01/3)
    monkeypatch.setattr(m,'certify_points',obs)
    own=SimpleNamespace(x=np.array([2.,3.,.01]),P=np.eye(3)*.01)
    h.observe(np.zeros((480,640,3),np.uint8),3.,own)
    assert h.last['status']=='pending_next_rgb' and own.x[2]==.01
    h.observe(np.ones((480,640,3),np.uint8),3.2,own)
    assert h.last['status']=='accepted' and own.x[2]==pytest.approx(.02)
    assert list(own.x[:2])==[2.,3.] and not h.last['metric_fix_refreshed']
    # No static wall => command state is retained, including covariance.
    monkeypatch.setattr(m,'certify_points',lambda *a,**k:dict(status='unknown_static_support'))
    old=own.x.copy();P=own.P.copy()
    h.observe(np.full((480,640,3),2,np.uint8),3.4,own)
    np.testing.assert_equal(own.x,old);np.testing.assert_equal(own.P,P)
    assert h.last_measurement_t==3.2


def test_finite_vectorized_line_hypotheses_and_first_ties_equal_reference():
    from harness.reloc16_lines import best_line
    rng=np.random.default_rng(40)
    for _ in range(12):
        uv=np.column_stack([np.arange(96),rng.integers(20,80,96)]).astype(float)
        uv[:40,1]=30+uv[:40,0]/4
        remaining=rng.random(96)>.1;eligible=rng.random(96)>.2
        ids=np.flatnonzero(remaining & eligible);best=None;checks=0
        for ia,i in enumerate(ids[:-1]):
            for j in ids[ia+1:]:
                slope=(uv[j,1]-uv[i,1])/(uv[j,0]-uv[i,0])
                keep=remaining & (abs(uv[:,1]-(uv[i,1]+slope*(uv[:,0]-uv[i,0])))<=1.5)
                checks+=1
                if best is None or keep.sum()>best.sum():best=keep
        got,work=best_line(uv,remaining,eligible,1.5)
        np.testing.assert_equal(got,best);assert work==checks


def test_vectorized_compass_preserves_cross_product_residual_ties():
    from harness.reloc16_lines import best_line
    uv=np.column_stack([np.arange(40),np.r_[np.full(20,10.),np.arange(20)%3+9.]])
    best=np.zeros(len(uv),bool);checks=0
    for i in range(len(uv)-1):
        for j in range(i+1,len(uv)):
            line=np.cross([*uv[i],1.],[*uv[j],1.]);norm=np.linalg.norm(line[:2])
            keep=abs(np.column_stack([uv,np.ones(len(uv))])@line/norm)<=1.5
            checks+=1
            if keep.sum()>best.sum():best=keep
    got,work=best_line(uv,np.ones(len(uv),bool),np.ones(len(uv),bool),1.5,perpendicular=True)
    np.testing.assert_equal(got,best);assert work==checks


def test_scene_floor_mask_removes_wall_signature_preserves_floor_and_default(monkeypatch):
    import json
    from pathlib import Path
    from harness.reloc16_floor_mask import floor_clear,OPTION
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    cal=json.loads((Path(__file__).parents[1]/'experiments/2026-10-16-reloc16/colour-calibration.json').read_text())
    state=ColourBoundaryState(cal['scene_profile'],cal,option=RELOC16_OPTION)
    # Fixed v5 wall; neutral floor; original magenta/orange/blue floor colours.
    image=np.array([[[110,75,90],[145,145,145],[179,77,209],[60,140,210],[190,135,70]]],np.uint8)
    clear=np.ones((1,5),bool)
    off,_=floor_clear(image,clear,option='off');assert off is clear
    actual,audit=floor_clear(image,clear,state=state,option=OPTION)
    np.testing.assert_equal(actual,[[False,True,True,True,True]])
    assert clear.all() and not audit['floor_lk_changed'] and not audit['doors_clear_changed']
    with pytest.raises(ValueError):floor_clear(image,clear,state=SimpleNamespace(profile='other',option=RELOC16_OPTION),option=OPTION)


def test_legacy_edge_proposals_require_explicit_v2_and_boolean():
    from harness.scene_colour_boundary import ColourBoundaryState
    with pytest.raises(ValueError,match='LEGACY_PROPOSALS_REQUIRE_BOUNDARY_V2'):
        ColourBoundaryState('unselected',{},legacy_proposals_v1=True)
    with pytest.raises(ValueError,match='LEGACY_PROPOSALS_REQUIRE_BOUNDARY_V2'):
        ColourBoundaryState('unselected',{},legacy_proposals_v1='yes')
