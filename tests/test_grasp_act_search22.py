"""Pure issued/visible regressions; no MuJoCo world or renderer."""
import argparse,math
from copy import deepcopy
import numpy as np
import pytest
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_contract import command
from sim.grasp_act_search15_modes import add_arguments,options,ALL_MODES
from sim.grasp_act_search22 import uncertainty,measurement_uncertainty,BodyNavigation,K,record_candidates,update_world,recovery_step
from sim.grasp_act_search21 import BodyNavigation as Previous,schedule
from tests.test_grasp_act_search21 import FIX,teacher as previous_teacher


def teacher():
    t=previous_teacher();t.search15_modes['search22']='search22_v1';return t


def measurement():
    return dict(id='red_2',kind='cargo',xyz=[.3,.1,.02],yaw=0.,radius=.03,top_z_bound_m=.04,visible_n=10,probe_N=12)


def test_default_off_and_explicit_dependency():
    p=argparse.ArgumentParser();add_arguments(p)
    assert options(p.parse_args([]))['search22']=='off'
    from sim.grasp_act_search15_modes import validate
    with pytest.raises(ValueError,match='search22 requires search21'):
        validate({**ALL_MODES,'search18_footprint':'off','search21':'off'},recovery='progress_view_recovery_v3')


def test_covariance_grows_with_issued_motion_resets_with_visible_update_and_rejects_truth():
    v=VisibleWorld('r1','blue',odometry='search17_fixed_v1',search22='search22_v1')
    v.observe([measurement()],0.)
    sigma0=uncertainty(v.memory['red_2'],v.pose)['sigma_m']
    issued=previous_teacher()._hold(0.);issued['wheels']=[.3]*4;issued['duration_s']=[.1]*4
    for i in range(1,11):v.issue(issued);v.observe([],i*.1)
    sigma=uncertainty(v.memory['red_2'],v.pose)['sigma_m']
    assert sigma>sigma0 and K==pytest.approx(3.0348542588)
    v.observe([measurement()],1.1)
    assert uncertainty(v.memory['red_2'],v.pose)['sigma_m']==pytest.approx(sigma0)
    with pytest.raises(ValueError,match='GT self pose forbidden'):v.observe([],1.2,comparison_pose=[0,0,0])


def test_off_preserves_visible_world_exactly_and_navigation_search21_padding():
    a=VisibleWorld('r1','blue');b=VisibleWorld('r1','blue',search22='off')
    for now,ms in [(0.,[measurement()]),(1.,[]),(20.,[])]:assert a.observe(ms,now)==b.observe(ms,now)
    t=previous_teacher();w=deepcopy(FIX['world'])
    nav=Previous(t,w,admission=True)
    stale=deepcopy(w);stale['visibility']['r1']['observations']['tile_1']['seen_t']-=.1
    assert .14 in Previous(t,stale,admission=True).disc_margins
    assert .005 in nav.disc_margins and nav.disc_margins==Previous(t,w,admission=True).disc_margins


def test_memory_margins_are_per_obstacle_and_geometry_still_rejects():
    t=teacher();w=deepcopy(FIX['world']);m=w['visibility']['r1']['observations']['tile_1']
    m['seen_t']-=1;m['uncertainty']=measurement_uncertainty(m)
    nav=BodyNavigation(t,w,admission=True)
    detail=next(d for d in nav.details if d['id']=='tile_1')
    assert .005<detail['margin_m']<.03
    rows=nav.candidate_audit(m['xyz'],0.)
    assert any(r['blocked'] and r['category']=='current_geometry' for r in rows)
    m['uncertainty']['command_covariance']=(np.eye(3)*.01).tolist()
    inflated=BodyNavigation(t,w,admission=True)
    assert next(d for d in inflated.details if d['id']=='tile_1')['margin_m']>detail['margin_m']


def test_memory_only_rejection_keeps_two_targeted_low_gaze_encounters():
    t=teacher();w=deepcopy(FIX['world']);now=w['t'];m=w['visibility']['r1']['observations']['tile_1']
    m['seen_t']-=1;m['uncertainty']=measurement_uncertainty(m)
    rows=[{'reason':'blocked_goal','collision_audit':[{'id':'tile_1','blocked':True,'category':'memory_margin'}]}, {'reason':'ik_unreachable'}]
    record_candidates(t,w,rows,now)
    assert rows[0]['rejection_category']=='memory_margin' and rows[1]['rejection_category']=='IK'
    schedule(t,w,now,force=True)
    assert t.search21_recovery['target'][0]=='tile_1'
    before=dict(t.sink.pwm);recovery_step(t,w,now+.1,before)
    assert t.search22_log[-1]['event']=='targeted_gaze'
    assert t.search22_log[-1]['height_m']<.04
    assert t.sink.pwm!=before
    recovery_step(t,w,now+1.5,dict(t.sink.pwm));schedule(t,w,now+2,force=True)
    recovery_step(t,w,now+3.5,dict(t.sink.pwm));schedule(t,w,now+4,force=True)
    assert t.search21_encounters==2 and t.search21_recovery is None


def test_clear_needs_fresh_frame_coverage_dwell_and_new_sighting_restores(monkeypatch):
    t=teacher();w=deepcopy(FIX['world']);now=w['t'];m=w['visibility']['r1']['observations']['tile_1']
    m['seen_t']-=1;m['uncertainty']=measurement_uncertainty(m)
    import sim.grasp_act_free_space as fs
    monkeypatch.setattr(fs,'ghost_visible_region',lambda *a,**kw:(False,'occluded'))
    assert 'tile_1' in update_world(t,w,now)['objects']
    monkeypatch.setattr(fs,'ghost_visible_region',lambda *a,**kw:(True,'covered_empty'))
    assert 'tile_1' in update_world(t,w,now)['objects']
    assert 'tile_1' not in update_world(t,w,now+.3)['objects']
    m['seen_t']=now+.4
    assert 'tile_1' in update_world(t,w,now+.4)['objects']
