"""Frozen visible-input geometry and executable recovery checks; no physics."""
import argparse,json,math
from copy import deepcopy
from pathlib import Path
import pytest
from scripts.replay_grasp_act_search18 import KW
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher as Teacher
from sim.grasp_act_search15_modes import ALL_MODES,add_arguments,options
from sim.grasp_act_search19 import body_fallback,admitted
from sim.grasp_act_search20 import PlanningBudget
from sim.grasp_act_search21 import BodyNavigation,schedule,recovery_step
from sim.grasp_act_goal_set import geometry

FIX=json.loads((Path(__file__).parent/'fixtures/grasp_act_search21.json').read_text())
def teacher():
    t=Teacher('r1','blue',{int(k):v for k,v in FIX['pwm'].items()},**KW,**{**ALL_MODES,'search24_irm':'off','search24_budget':'off','search23':'off','search22':'off','search18_footprint':'off'})
    t.folded_ready=True;t.phase='approach';return t

def test_default_and_dependency():
    p=argparse.ArgumentParser();add_arguments(p)
    assert options(p.parse_args([]))['search21']=='off'
    with pytest.raises(ValueError,match='requires search20'):
        Teacher('r1','blue',FIX['pwm'],**KW,**{**ALL_MODES,'search24_irm':'off','search24_budget':'off','search23':'off','search22':'off','search18_footprint':'off','search20':'off'})

def test_fresh_geometry_admits_checked_alternative_and_stale_does_not():
    t=teacher();w=deepcopy(FIX['world']);nav=BodyNavigation(t,w,admission=True)
    g=geometry(w,'r1','blue',(0.,.203))[3]
    assert not nav.free(g,[],[],.13)
    selected,rows=body_fallback(t,w,FIX['t'])
    assert selected is not None and selected['choice']==(math.radians(10),.208)
    assert rows[-1]['arm_sweep'] and rows[-1]['body_sweep']
    stale=deepcopy(w);stale['visibility']['r1']['observations']['tile_1']['seen_t']-=.1
    assert not BodyNavigation(t,stale,admission=True).free(selected['goal'],[],[],.13)
    stale=deepcopy(w);stale['visibility']['r1']['observations']['band_blue']['seen_t']-=.1
    assert not BodyNavigation(t,stale,admission=True).free(selected['goal'],[],[],.13)

def test_empty_set_has_checked_motion_then_real_camera_scan_and_finite_replan():
    t=teacher();w=deepcopy(FIX['world']);now=FIX['t'];schedule(t,w,now,force=True)
    before=dict(t.sink.pwm);value,done=recovery_step(t,w,now+.1,before)
    assert any(value['wheels']) and not done and admitted(t,w,value,before)
    previous=t.sink.pwm[6]
    recovery_step(t,w,now+.9,dict(t.sink.pwm))
    assert t.sink.pwm[6]!=previous
    recovery_step(t,w,now+1.5,dict(t.sink.pwm))
    assert t.search21_recovery is None and not t.approach_plan_valid
    schedule(t,w,now+2,force=True);t.search21_recovery=None;schedule(t,w,now+4,force=True)
    assert t.search21_encounters==2 and t.search21_recovery is None


def test_transient_empty_set_does_not_disrupt_existing_motion():
    t=teacher();t.approach_blocked_since=FIX['t']
    schedule(t,FIX['world'],FIX['t']+.1)
    assert t.search21_recovery is None
    schedule(t,FIX['world'],FIX['t']+2.)
    assert t.search21_recovery is not None


def test_follow_segment_instead_of_returning_to_a_passed_vertex(monkeypatch):
    from sim.grasp_act_search21 import route_projection,route_progress
    t=teacher();w=deepcopy(FIX['world']);nav=BodyNavigation(t,w)
    path=[(0.,0.),(1.,0.),(1.,1.)];start=(.2,0.)
    monkeypatch.setattr(nav,'segment_free',lambda *a:True)
    assert nav.waypoint(start,path,[],[],0.)==(1.,0.)
    t.path=path
    assert nav.path_for_goal(start,(1.,1.),[],[],0.)==[start,(1.,0.),(1.,1.)]
    # Moving away from the Euclidean goal along a required detour is progress.
    t.path=[(0.,0.),(-1.,0.),(-1.,1.),(1.,1.)]
    for now,x in enumerate((0.,-.2,-.4,-.6,-.8)):
        w['robots']['r1']['pose']=[x,0.,0.]
        assert route_progress(t,w,(1.,1.),0.,float(now)) is None
    # Repeated forward/backward oscillation never exceeds the best arc.
    for now,x in ((5.,-.7),(6.,-.8),(7.,-.7)):
        w['robots']['r1']['pose']=[x,0.,0.];event=route_progress(t,w,(1.,1.),0.,now)
    assert event=='replan'
