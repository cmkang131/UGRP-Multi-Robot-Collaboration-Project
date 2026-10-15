"""Invalid-start, issued-pulse and exact certificate regressions; no physics."""
import argparse
from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from sim.grasp_act_search15_modes import add_arguments, options, validate
from sim.grasp_act_search20 import PlanningBudget
from sim.grasp_act_search23 import BodyNavigation
from sim.grasp_act_search27 import MODES, command_check, start_state, in_frame, optical_pixel
from tests.test_grasp_act_search25 import scene


def candidate():
    t,w=scene();t.search15_modes.update(MODES,search25_inflation='search25_soft_v1',
        search25_budget='search25_checks_v1',search25_memory='search25_memory50_v1')
    return t,w


def test_defaults_and_dependencies():
    p=argparse.ArgumentParser();add_arguments(p)
    assert all(options(p.parse_args([]))[k]=='off' for k in MODES)
    with pytest.raises(ValueError,match='search27 requires'):
        validate(MODES,recovery='progress_view_recovery_v3')


def test_warm_body_certificate_same_logical_cost_and_new_observation_reopens():
    t,w=candidate();t.search20_budget=PlanningBudget(max_checks=98304,max_s=None,safety_s=30.)
    a=BodyNavigation(t,w);first=a.measure([(0.,0.)],0.)
    cold=t.search20_budget.checks
    b=BodyNavigation(t,deepcopy(w));second=b.measure([(0.,0.)],0.)
    assert t.search20_budget.checks==2*cold
    assert all(np.array_equal(x,y) for x,y in zip(first,second))
    assert t.search27_stats['body_grid']['cache_hits']==1
    w['visibility']['r1']['observations']['box']['seen_t']=w['t']
    BodyNavigation(t,w).measure([(0.,0.)],0.)
    assert t.search27_stats['body_grid']['computed']==2
    w['objects']['new']={'xy':[0.,0.], 'radius':.04}
    assert not BodyNavigation(t,w).free((0.,0.),(),(),0.)
    assert t.search27_stats['body_grid']['computed']==3


def test_invalid_start_never_searches_or_teleports_and_logs_transition():
    t,w=candidate();w['objects']['box']['xy']=[.1,0.]
    original=deepcopy(w['robots'])
    with patch('sim.grasp_act_pregrasp.issued_sweep_reason',return_value=None), \
         patch('sim.grasp_act_search27.escape',return_value=None), \
         patch.object(t,'_plan_approach',side_effect=AssertionError('must not search')):
        value=start_state(t,w,dict(t.sink.pwm))
        assert not any(value['wheels'])
        assert w['robots']==original
    row=next(e for e in t.search20_log if e['event']=='start_geometry_invalid')
    assert row['blocked_object']=='box' and row['min_gap_m']<0
    assert row['current']['body_invalid'] and 'last_safe_command' in row


def test_only_monotonic_escape_under_both_models_and_no_stationary_bypass():
    t,w=candidate();w['objects']['box']['xy']=[.115,0.]
    before=dict(t.sink.pwm)
    with patch('sim.grasp_act_pregrasp.issued_sweep_reason',return_value=None):
        back=t._continuous(w['t'],-.025,0.,0.)
        forward=t._continuous(w['t'],.025,0.,0.)
        assert command_check(t,w,back,before,allow_escape=True)[0]
        assert not command_check(t,w,forward,before,allow_escape=True)[0]
        assert not command_check(t,w,t._hold(w['t']),before,allow_escape=True)[0]
        assert not command_check(t,w,back,before)[0]


def test_first_and_final_command_share_body_arm_checks():
    t,w=candidate();before=dict(t.sink.pwm);v=t._continuous(w['t'],.025,0.,0.)
    with patch('sim.grasp_act_pregrasp.issued_sweep_reason',return_value='arm_wall_sweep'):
        assert not command_check(t,w,v,before)[0]
        from sim.grasp_act_search19 import body_pulse_free
        assert not body_pulse_free(t,w,v)


def test_actual_frame_asymmetric_intrinsics():
    from sim.masterpi_camera_profile import CAMERA_CX_PX,CAMERA_FX_PX
    assert optical_pixel((0.,0.,1.))[0]==CAMERA_CX_PX
    assert in_frame((-(CAMERA_CX_PX-1)/CAMERA_FX_PX,0.,1.))
    assert not in_frame((-(CAMERA_CX_PX+1)/CAMERA_FX_PX,0.,1.))
    assert not in_frame((0.,0.,-1.))


def test_short_plan_all_six_scenario_hashes_validate_before_submission():
    import json
    from pathlib import Path
    from sim.grasp_act_scene import validate_cargo_scene
    plan=json.loads((Path(__file__).parents[1]/'experiments/2026-10-14-e2e18-grasp-rootcause/teacher-search27-short6-plan.json').read_text())
    assert [(r['seed'],r.get('cargo_scene','off')) for r in plan['episodes']]==[
        (315709,'off'),(315709,'cargo_v6'),(8311709,'off'),(8311709,'cargo_v6'),(8312300,'off'),(8312300,'cargo_v6')]
    for row in plan['episodes']:validate_cargo_scene(row)


def test_recovery_heading_connector_uses_safe_real_pulse_without_coordinate_change():
    from sim.grasp_act_search27 import heading_connector
    from harness.grasp_act_visible_world import command_delta
    import math
    t,w=candidate();w['objects']['box']['xy']=[0.,.11]
    w['visibility']['r1']['observations']['band_blue']={'id':'band_blue','kind':'band','seen_t':w['t'],'xyz':[0.,.5,.03]}
    nav=BodyNavigation(t,w);nav.target=(0.,.5,.03)
    assert not nav.pose_segment(nav.pose,(*nav.pose[:2],math.pi/2))
    original=deepcopy(w['robots'])
    with patch('sim.grasp_act_pregrasp.issued_sweep_reason',return_value=None):
        value=heading_connector(t,w,dict(t.sink.pwm),nav)
        assert value is not None and command_delta(value,.1)[1]<0
    assert w['robots']==original


def test_cached_issued_arm_kinematics_preserve_rejection_and_gap():
    from sim.grasp_act_pregrasp import issued_sweep_reason
    from sim.grasp_act_search27 import arm_sweep
    t,w=candidate();w['objects']['box']['top_z_bound_m']=.04;before=dict(t.sink.pwm);a=[];b=[]
    x=issued_sweep_reason(w,t.rid,(0.,0.,0.),before,before,(.001,0.,0.),audit=a)
    y=arm_sweep(t,w,t.rid,(0.,0.,0.),before,before,(.001,0.,0.),audit=b)
    assert x==y and a==b
