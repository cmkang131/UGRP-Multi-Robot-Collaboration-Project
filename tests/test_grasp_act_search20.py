"""Finite saved-input regressions. No MuJoCo world, renderer or model."""
import argparse
from copy import deepcopy
import inspect
import json
import math
from pathlib import Path

import pytest
from harness.grasp_act_admission import recording_admission
from scripts.replay_grasp_act_search19 import BASE, KW, clearance_rows
from sim.grasp_act_search15_modes import add_arguments, options, match
from sim.grasp_act_search19 import MODES as S19, admitted
from sim.grasp_act_search20 import (MODES, ADMIT_MARGIN_M, RETAIN_MARGIN_M, CACHE_SIZE,
    BodyNavigation, PlanningBudget, PlanningBudgetExceeded, retain, alignment_alternative)
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

FIX=json.loads((Path(__file__).parent/'fixtures/grasp_act_search20.json').read_text())
OLD=json.loads((Path(__file__).parent/'fixtures/grasp_act_search19.json').read_text())


def teacher(x):
    t=VisibleOnlyGraspTeacher('r1','blue',{int(k):v for k,v in x['pwm'].items()},**KW,**BASE,**S19,**MODES)
    t.folded_ready=True;t.started=True;t.phase='approach'
    return t


def test_toggle_default_dependencies_and_recording_provenance():
    parser=argparse.ArgumentParser();add_arguments(parser)
    assert options(parser.parse_args([]))['search20']=='off'
    assert 'search20' in inspect.signature(recording_admission).parameters
    with pytest.raises(ValueError,match='search20'):
        match({},MODES,'gate')
    with pytest.raises(ValueError,match='both search19'):
        VisibleOnlyGraspTeacher('r1','blue',FIX['alignment']['pwm'],**KW,**BASE,**MODES)


def test_same_family_survives_actual_21mm_goal_jitter_and_late_low_clearance():
    # Start from the actual last valid plan, then retain OWN updated plan. Using
    # baseline state independently at 17.4 would already have lost that plan.
    states=[x for x in FIX['late'] if x['t']>=15.4-1e-6]
    t=teacher(states[0]);t.search19_body_active=True
    t.path=states[0]['path'];t.path_goal=states[0]['path_goal'];t.approach_choice=tuple(states[0]['choice'])
    for x in states:
        selected,checked=retain(t,x['world'],x['t'])
        assert selected is not None, (x['t'],checked)
        assert selected['choice']==t.approach_choice
        t.path=selected['path'];t.path_goal=selected['goal']
    assert any(x['goal_shift_m']>.020 for x in t.search20_log)


@pytest.mark.parametrize('seed,overlaps',[(8311709,54),(8311723,77)])
def test_every_genuinely_overlapping_original_candidate_stays_rejected(seed,overlaps):
    x=OLD['blocked'][str(seed)];t=teacher(x)
    rows=clearance_rows(x['world'],t,FIX['first_candidates'][str(seed)])
    bad=[r for r in rows if r['body_gap_mm']<=0]
    assert len(rows)==118 and len(bad)==overlaps
    nav=BodyNavigation(t,x['world'])
    for row in bad:
        from sim.grasp_act_goal_set import geometry
        h=geometry(x['world'],'r1','blue',(math.radians(row['offset_deg']),row['distance_m']))[2]
        assert not nav.free(row['goal'],[],[],.13,heading=h)


def test_pose_and_segment_use_same_near_overlap_threshold_and_new_pose_is_conservative():
    from sim.grasp_act_search18 import HALF_X
    x=FIX['alignment'];t=teacher(x)
    w={'beam':None,'walls':[],'robots':{'r1':{'pose':[0.,0.,0.]}},
       'objects':{'box':{'xy':[HALF_X+.006+.025,0.],'radius':.020}}}
    nav=BodyNavigation(t,w);new=BodyNavigation(t,w,admission=True)
    assert nav.free((0.,0.),[],[],.13) and nav.pose_segment((0.,0.,0.),(0.,0.,0.))
    assert not new.free((0.,0.),[],[],.13)
    assert ADMIT_MARGIN_M==.140 and RETAIN_MARGIN_M==.002


def test_alignment_tries_clear_backward_axis_when_lateral_points_into_beam():
    x=FIX['alignment'];t=teacher(x);t.phase='align';t.approach_plan_valid=True
    t.approach_choice=tuple(x['choice']);t.staging_distance=t.approach_choice[1]
    t.align_active=list(x['active']);t.align_integral=[0.,0.,0.]
    before=dict(t.sink.pwm);original=t._continuous(x['t'],0.,-.05,0.)
    assert not admitted(t,x['world'],original,before)
    replacement=alignment_alternative(t,x['world'],original,before,x['t'])
    assert admitted(t,x['world'],replacement,before) and replacement!=original
    assert t.search20_log[-1]['axis']==0
    assert replacement['pwm']==original['pwm']


def test_cache_is_exact_and_bounded_and_deadline_never_issues_partial_motion(monkeypatch):
    x=FIX['alignment'];t=teacher(x)
    w={'beam':None,'walls':[],'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{}}
    nav=BodyNavigation(t,w);t.search20_budget=PlanningBudget()
    assert nav.free((0.,0.),[],[],.13);assert nav.free((0.,0.),[],[],.13)
    assert t.search20_budget.hits==1
    for i in range(CACHE_SIZE+1):nav.free((i*1e-7,0.),[],[],.13)
    assert len(t.search20_cache)==CACHE_SIZE
    t.search20_budget=None
    before=dict(t.sink.pwm)
    def exhausted(world,now,*,permit_pick):
        t.sink.pwm[3]=1234
        raise PlanningBudgetExceeded()
    monkeypatch.setattr(t,'_step',exhausted)
    value,done=t.step(x['world'],x['t'])
    assert not any(value['wheels']) and value['pwm']=={str(k):v for k,v in before.items()}
    assert not done and not t.approach_plan_valid


def test_v6_requires_explicit_toggle_and_matching_scenario_hash():
    import hashlib
    from sim.grasp_act_scene import validate_cargo_scene
    assert validate_cargo_scene({'scenario_id':'s1_normal_mixed_v4'})=='off'
    p=Path(__file__).resolve().parents[1]/'configs/zone_study_scenarios_v6/s1_normal_mixed_v6.json'
    plan={'scenario_id':'s1_normal_mixed_v6','cargo_scene':'cargo_v6',
          'scenario_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    assert validate_cargo_scene(plan)=='cargo_v6'
    with pytest.raises(ValueError,match='hash mismatch'):
        validate_cargo_scene({**plan,'scenario_source_sha256':'wrong'})
    with pytest.raises(ValueError,match='separately hashed'):
        validate_cargo_scene({**plan,'scenario_id':'s1_normal_mixed_v4'})


def test_route_progress_replan_keeps_family_proposal_and_revalidates_it(monkeypatch):
    x=FIX['late'][-1];t=teacher(x);t.search19_body_active=True
    initial=next(v for v in FIX['late'] if abs(v['t']-16.4)<.01)
    t.approach_choice=tuple(initial['choice']);t.path=initial['path'];t.path_goal=initial['path_goal']
    t.staging_distance=t.approach_choice[1];t.approach_plan_valid=True;t.next_plan=x['t']+1.
    monkeypatch.setattr(t,'_peer_route',lambda *a:None)
    monkeypatch.setattr(t.progress,'observe_goal',lambda *a:'replan')
    pose,point,heading,goal=t._geometry(x['world'])
    t._route(x['world'],goal,heading,x['t'])
    assert t.approach_plan_valid and t.path
    assert t.search20_log[-1]['event']=='stance_family_retained'
