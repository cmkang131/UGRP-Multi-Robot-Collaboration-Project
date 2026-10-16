"""Saved counterexample scalars and visible/issued-only regressions; no physics."""
import argparse
from copy import deepcopy
import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sim.grasp_act_search15_modes import add_arguments, options, match, validate
from sim.grasp_act_search26 import MODES, observed_band, connector_cache, alignment, remember_issued
from sim.settle_pulse import PulseSettler
from tests.test_grasp_act_search25 import scene


def test_default_off_dependencies_and_provenance():
    p=argparse.ArgumentParser();add_arguments(p)
    assert all(options(p.parse_args([]))[k]=='off' for k in MODES)
    with pytest.raises(ValueError,match='search26 requires'):
        validate(MODES,recovery='progress_view_recovery_v3')
    with pytest.raises(ValueError,match='search26_alignment mode mismatch'):
        match({},MODES,'recording')


def test_observation_priority_requires_current_own_admitted_band():
    t,w=scene();nav=SimpleNamespace(teacher=t,world=w,rid='r1',end='blue')
    w['beam']={'ends':{'blue':(.208,0.,.024)}}
    vis=w['visibility']['r1'];vis['visible_probes']=5
    vis['observations']['band_blue']={'seen_t':w['t']}
    assert observed_band(nav) is None
    t.search15_modes.update(MODES)
    assert observed_band(nav)==5
    vis['observations']['band_blue']['seen_t']-=.1
    assert observed_band(nav) is None
    vis['observations']['band_blue']['seen_t']=w['t'];vis['visible_probes']=4
    assert observed_band(nav) is None


def test_failed_connector_reused_and_any_input_change_invalidates():
    t,w=scene();t.search15_modes.update(MODES)
    cache=connector_cache(t,w);cache['failure']=(3,None,'blocked')
    assert connector_cache(t,deepcopy(w)) is cache
    w['objects']['box']['xy'][0]+=.0000001
    assert connector_cache(t,w)=={} and connector_cache(t,w) is not cache


def test_failed_connector_sample_is_not_recomputed_across_navigation_instances():
    from sim.grasp_act_search23 import BodyNavigation
    t,w=scene();t.search15_modes.update(MODES)
    nav=BodyNavigation(t,w);before=dict(t.sink.pwm)
    with patch('sim.grasp_act_pregrasp.band_view',return_value=(3,before)) as predict:
        assert nav.connector_sample((0.,0.,0.),before,(0.,0.),0.)[0]==3
        assert BodyNavigation(t,w).connector_sample((0.,0.,0.),before,(0.,0.),0.)[0]==3
        assert predict.call_count==1
        w['objects']['box']['xy'][0]+=.0000001
        assert BodyNavigation(t,w).connector_sample((0.,0.,0.),before,(0.,0.),0.)[0]==3
        assert predict.call_count==2


def setup_alignment(point,heading,distance):
    t,w=scene();t.search15_modes.update(MODES);t.phase='align';t.staging_distance=distance
    t._geometry=lambda *_:((0.,0.,0.),point,heading,
        (point[0]-distance*math.cos(heading),point[1]-distance*math.sin(heading)))
    return t,w


def test_r3_blocked_yaw_can_use_settled_translation_toward_actual_goal():
    # search25 R3 final relative observation and unchanged 60mrad limit.
    t,w=setup_alignment((.2083848766,.004469068,.0238922445),.06199506,.208)
    def safe(t,w,value,before,**kwargs):
        from harness.grasp_act_visible_world import command_delta
        dx,dy,da=command_delta(value,.1)
        return not da and dy<0
    with patch('sim.grasp_act_search19.admitted',side_effect=safe):
        value=alignment(t,w,1.)
    assert any(value['wheels'])
    from harness.grasp_act_visible_world import command_delta
    assert command_delta(value,.1)[1]<0
    assert t.search26_settlers[1].pulses==0
    remember_issued(t,value)
    assert t.search26_settlers[1].pulses==1
    from sim.grasp_act_teacher import YAW_TOL_RAD
    assert YAW_TOL_RAD==.06


def test_unreachable_submillimeter_target_keeps_minimum_pulse():
    t,w=setup_alignment((.2096633294,-.0039812237,.0238922445),0.,.2092)
    with patch('sim.grasp_act_search19.admitted',return_value=True):
        value=alignment(t,w,1.)
    assert value['wheels']==[.35]*4
    assert value['duration_s']==[.04]*4


def test_rejected_pulse_does_not_accumulate_reversal_or_relax_ready():
    t,w=setup_alignment((.2083848766,.004469068,.0238922445),.06199506,.208)
    with patch('sim.grasp_act_search19.admitted',return_value=False):
        value=alignment(t,w,1.)
    remember_issued(t,value)
    assert not any(value['wheels']) and all(s.pulses==0 for s in t.search26_settlers)
    # Exercise the imported common policy; no copy of reversal logic here.
    settler=PulseSettler(.002)
    for e in (.011,-.011,.011,-.011):
        state=settler.observe(e,.01);settler.issued(e)
    assert state['settled'] and state['reason']=='consecutive_reversals'
