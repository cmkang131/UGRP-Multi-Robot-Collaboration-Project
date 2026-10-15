"""Crate15 saved-input/numerical regressions. No dynamics or rendering."""
import importlib.util
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from harness.grasp_act_visible_world import command_delta
from sim.crate_motion_v15 import Navigation, MODE, alignment_pulse
from sim.crate_navigation_v12 import WallFootprint
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_goal_set import geometry
from scripts.run_crate_teacher import make_grasp_teacher, run
from scripts.zone_teacher import FOLDED

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'experiments/2026-10-15-crate15'

@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    import mujoco
    def forbidden(*a,**k):raise AssertionError('physics/render forbidden')
    for name in ('mj_step','mj_forward','Renderer'):monkeypatch.setattr(mujoco,name,forbidden)


def teacher(motion=MODE):
    return make_grasp_teacher('r1','teal',FOLDED,teacher_stability='align_relook_v1',
        teacher_search='search_reacquire_v1',approach_goal_set='approach_goal_set_v1',
        crate_lift_pose='crate_antipodal_grasp_v1',crate_approach_recovery='crate_approach_recovery_v1',
        crate_wall_footprint='crate_footprint_v1',crate_stances='crate_stances_v1',
        crate_pulse_safety='crate_no_closer_v1',crate_candidate_recovery='crate_candidates_v1',
        crate_alignment='crate_alignment_v14',crate_motion=motion)


def empty():
    return {'t':1.,'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{},'walls':[],
        'beam':{'pose':[.2974,0.,0.],'ends':{'teal':[.1974,0.,.02396]}},
        'visibility':{'r1':{'visible_probes':15,'objects':[],'peers':[]}}}


def hold():return {'t':1.,'pwm':{str(k):v for k,v in FOLDED.items()},'wheels':[0.]*4,'duration_s':[0.]*4}


@pytest.mark.parametrize('case',json.loads((HERE/'route-fixtures.json').read_text()),ids=lambda c:c['run'])
def test_saved_safe_start_does_not_require_unsafe_snapped_node(case):
    w=case['world'];rid=case['robot'];start=w['robots'][rid]['pose'][:2]
    _,_,heading,goal=geometry(w,rid,case['end'],case['choice'])
    old=WallFootprint(w,rid,True,CRATE,(-20,20,-20,20))
    assert old.free(start,old.pose[2]) and old.free(goal,heading)
    assert old.path(start,goal,heading) is None
    nav=Navigation(w,rid,True,CRATE,(-20,20,-20,20),end=case['end']);path=nav.path(start,goal,heading)
    assert path and path[0]==tuple(start) and path[-1]==tuple(goal)
    assert all(nav.segment(a,b,nav.pose[2] if i==0 else nav.heading_at(a,heading),nav.heading_at(b,heading))
               for i,(a,b) in enumerate(zip(path,path[1:])))


def test_peer_rectangle_preserves_real_occupation_and_clears_false_circle():
    w=empty();w['robots']['r2']={'pose':[.31,0.,0.]}
    nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    assert not WallFootprint(w,'r1',True,CRATE,(-20,20,-20,20)).free((0.,0.),0.)
    assert nav.free((0.,0.),0.)
    w['robots']['r2']['pose']=[.02,0.,0.]
    assert not Navigation(w,'r1',True,CRATE,(-20,20,-20,20)).free((0.,0.),0.)


def test_actual_crate_wall_and_rotating_peer_collisions_are_rejected():
    w=empty();nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    assert not nav.free((.2974,0.),0.)
    w['walls']=[(0.,.115,1.,.02,0.)]
    nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    assert nav.free((0.,0.),0.)
    assert not nav.segment((0.,0.),(0.,0.),0.,math.pi/2)
    value={**hold(),'wheels':[-.35,.35,-.35,.35],'duration_s':[.1]*4}
    assert not nav.pulse_safe(value)


@pytest.mark.parametrize('axis,error',[(0,.0008),(0,-.0008),(1,.003),(2,.006),(2,-.006)])
def test_fine_duty_resolves_inner_band_without_40ms_floor(axis,error):
    errs=[0.,0.,0.];errs[axis]=error;drive=[0.,0.,0.];drive[axis]=(.9,.9,.8)[axis]*error
    cmd=alignment_pulse(hold(),drive,errs);delta=command_delta(cmd,.1)
    assert any(cmd['wheels']) and .001<=max(cmd['duration_s'])<.04
    assert 0.<delta[axis]/error<=.5
    assert all(abs(d)<1e-12 for i,d in enumerate(delta) if i!=axis)


def test_retained_path_is_rechecked_and_invalidated_by_new_wall(monkeypatch):
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    t=teacher();t.folded_ready=True;w=empty();goal=(-.02,0.)
    # Real nominal station is 0; use its current exact geometry.
    pose,g,heading,goal=t._geometry(w);t.path=[(-.1,0.),goal];t.path_goal=goal
    w['robots']['r1']['pose']=[-.1,0.,0.]
    def failed(self,*a):self.path=[];self.approach_plan_valid=False;return False
    monkeypatch.setattr(VisibleOnlyGraspTeacher,'_plan_approach',failed)
    assert t._plan_approach(w,1.)
    assert t.crate_recovery_log[-1]['recovery']=='revalidated_previous_path'
    w['walls']=[(0.,0.,.2,.2,0.)]
    assert not t._plan_approach(w,2.) and not t.path


def test_side_view_uses_only_current_body_without_assigned_lug(monkeypatch):
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    monkeypatch.setattr(VisibleOnlyGraspTeacher,'_observe_stable',lambda self,w,n:self._hold(n))
    w=empty();w['beam']=None;w['visibility']['r1'].update(visible_probes=0,objects=['crate_1'])
    w['objects']={'crate_1':{'xy':[.5,0.],'radius':.133,'top_z_bound_m':.12}}
    t=teacher();t.folded_ready=True;t.phase='search'
    cmd=t._observe_stable(w,1.)
    assert any(cmd['wheels']) and t.crate_recovery_log[-1]['hidden_lug_read'] is False
    for now in (2.,3.,4.):t._observe_stable(w,now)
    assert 60 in t.search_view_visited and t.search_view_key != 60
    w['visibility']['r1']['objects']=[]
    assert not any(t._observe_stable(w,5.)['wheels'])


def test_crate15_boundary_preflight_and_opt_in(tmp_path):
    with pytest.raises(ValueError,match='held_object'):run({},tmp_path/'no',crate_profile='crate15_v1')
    assert not (tmp_path/'no').exists()
    assert teacher('off').crate_motion=='off'


def test_queue_is_review_only_five_plus_ten():
    spec=importlib.util.spec_from_file_location('queue15',HERE/'queue.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    q=m.build('f'*40,{})
    assert len(q['runs'])==15 and q['stage_counts']=={'reproduction':5,'diagnostic':10,'gate':0}
    assert {r['seed'] for r in q['runs'] if r['stage']=='reproduction'}=={77990,79314,79317,79450,79451}
    assert not any(r['near_wall'] for r in q['runs'])
    def check(v):
        if isinstance(v,dict):
            for k,item in v.items():
                if any(s in k for s in ('approved','enabled','authorized','ready','submitted')):
                    assert item is False or isinstance(item,dict) and not any(item.values())
                check(item)
        elif isinstance(v,list):
            for item in v:check(item)
    check(q)
