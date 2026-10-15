"""Actual geometry and opt-in invariants, no dynamics or renderer."""
import argparse
from copy import deepcopy
import math
import numpy as np
import pytest
from unittest.mock import patch
from sim.grasp_act_search15_modes import add_arguments,options,validate,match
from sim.grasp_act_search25 import MODES,segment_envelope,in_frame
from sim.grasp_act_search23 import BodyNavigation
from sim.grasp_act_search18 import HALF_X
from tests.test_grasp_act_search23 import teacher


def scene():
    t=teacher();t.search15_modes.update(search24_irm='search24_irm_v1',search24_budget='search24_checks_v1')
    w={'t':2.,'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{'box':{'xy':[.2,0.], 'radius':.025}},
       'beam':None,'walls':[], 'visibility':{'r1':{'observations':{'box':{'kind':'cargo','id':'box',
       'xyz':[.2,0.,.02],'seen_t':0.,'yaw':0.,'radius':.025}},'objects':[],'peers':[]}}}
    return t,w


def test_independent_default_off_and_provenance():
    p=argparse.ArgumentParser();add_arguments(p);values=options(p.parse_args([]))
    assert all(values[k]=='off' for k in MODES)
    with pytest.raises(ValueError,match='search25 requires'):
        validate({'search25_memory':MODES['search25_memory']},recovery='progress_view_recovery_v3')
    with pytest.raises(ValueError,match='search25_memory mode mismatch'):
        match({}, {'search25_memory':MODES['search25_memory']},'gate')


def test_inflation_can_be_crossed_but_actual_body_collision_cannot():
    t,w=scene();old=BodyNavigation(t,w)
    assert not old.free((0.,0.),(),(),0.)
    t.search15_modes['search25_inflation']=MODES['search25_inflation'];nav=BodyNavigation(t,w)
    assert nav.free((0.,0.),(),(),0.)
    assert not nav.free((.2,0.),(),(),0.)
    assert not nav.pose_segment((0.,0.,0.),(.2,0.,0.))
    assert nav.pose_segment((0.,0.,0.),(-.1,0.,0.))
    assert nav.audit_details[0]['margin_m']>0  # retained as soft cost


def test_sample_envelope_rejects_an_edge_grazing_between_samples():
    t,w=scene();t.search15_modes['search25_inflation']=MODES['search25_inflation']
    nav=BodyNavigation(t,w)
    x=.2-.025-HALF_X-.0001
    assert nav.free((x,0.),(),(),0.)
    assert not nav.pose_segment((x,0.,0.),(x,.002,0.))
    assert nav.last_blockers[0]['id']=='box'
    # Grid edges retain these rows in nav.blocked, then another batched node
    # measurement compares slacks. Exercise the R1 failure path explicitly.
    nav.blocked['box']=nav.last_blockers[0]
    nav.measure([(.2,0.)])
    assert nav.blocked['box']['slack_m']<0
    assert segment_envelope((0.,0.,0.),(.1,0.,.1),50)>0


def test_memory50_changes_only_remembered_envelope():
    t,w=scene();t.search15_modes['search25_memory']=MODES['search25_memory'];nav=BodyNavigation(t,w)
    assert nav.audit_details[0]['margin_m']==.05
    w['visibility']['r1']['observations']['box']['seen_t']=w['t']
    fresh=BodyNavigation(t,w)
    assert fresh.audit_details[0]['margin_m']==.005
    assert not nav.inflation_soft


def test_rectangular_fov_preserves_forward_and_vertical_limits():
    assert in_frame(np.array([math.tan(math.radians(23)),0.,1.]))
    assert not in_frame(np.array([0.,math.tan(math.radians(19)),1.]))
    assert not in_frame(np.array([0.,0.,-1.]))


def test_wall_safety_cap_is_separate_from_compute_exhaustion():
    from sim.grasp_act_search20 import PlanningBudget,PlanningSafetyCap
    b=PlanningBudget(max_checks=98304,max_s=None,safety_s=30.)
    with patch('sim.grasp_act_search20.time.perf_counter',side_effect=[0.,0.,31.]):
        b.check()
        with pytest.raises(PlanningSafetyCap):b.check()
    assert b.checks==1 and not b.exhausted


def test_raw_r2_submillimeter_unreachable_target_is_not_a_zero_command():
    from sim.grasp_act_teacher import grasp_poses
    point=(.20966332944715402,-.003981223655784681,.023892244543134985)
    with pytest.raises(ValueError):grasp_poses(point)
    values=[]
    for mode in ('off',MODES['search25_inflation']):
        t,w=scene();t.phase='align';t.staging_distance=.2092
        t.search15_modes['search25_inflation']=mode
        t._nominal_handoff=lambda *a:False;t._uses_goal_set=lambda *a:False
        t._geometry=lambda *a:((0.,0.,0.),point,0.,(point[0]-.2092,point[1]))
        t.ready_geometry=lambda *a:False
        w.update(beam={'ends':{'blue':point}},visibility={'r1':{'visible_probes':15}})
        value,_=t._approach(w,2.);values.append(value)
    assert not any(values[0]['wheels'])
    assert all(v==.35 for v in values[1]['wheels'])
    assert values[1]['duration_s']==[.04]*4
