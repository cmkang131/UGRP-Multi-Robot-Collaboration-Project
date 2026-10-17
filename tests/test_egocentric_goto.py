import math
import numpy as np
import pytest

from harness.egocentric_goto import (
    OPTION, SCHEMA, EgocentricGoto, command_delta, duty, point_covariance)


def observation(xy):
    return dict(id='detected-floor-target', kind='zone_marking', signature='floor_orange_zone_marking',
                relative_xy_m=list(xy), covariance_m2=point_covariance(xy).tolist())


def forward_command():
    wheels, duration = duty([1., 0., 0.])
    return dict(wheels=wheels, duration_s=duration)


def test_off_is_explicit_and_does_not_construct_memory():
    c = EgocentricGoto(option='off', footprint_radius_m=.12)
    assert c.memory is None and c.memory_module is None
    action = c.step(0., None, [observation([2., 0.])])
    assert action['kind'] == 'stop' and action['reason'] == 'option_off'
    assert c.done and c.memories == []
    context = c.context()
    assert context['schema'] == SCHEMA and context['items'] == []
    assert context['held_world_reads'] == 0 and context['static_map_control'] == 0
    with pytest.raises(ValueError, match='UNKNOWN_EGOCENTRIC_GOTO_OPTION'):
        EgocentricGoto(option='egocentric_goto_v2', footprint_radius_m=.12)


def test_own_command_transport_then_visual_reobservation_corrects_memory():
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    c.step(0., None, [observation([2., 0.])])
    assert len(c.memories) == 1 and c.memories[0]['kind'] == 'zone_marking'
    before = np.asarray(c.memories[0]['relative_xy_m'])
    command = forward_command()
    increment = np.asarray(command_delta(command))
    result = c.update_memory(.1, command, [])
    after = np.asarray(c.memories[0]['relative_xy_m'])
    assert after[0] < before[0]
    assert abs((after[0]-before[0]) + increment[0]) < .02
    prior_error = np.linalg.norm(after-[1.5, .1])
    corrected = c.update_memory(.2, None, [observation([1.5, .1])])
    assert any(e['reason'] == 'reobserved' for e in corrected['events'])
    first_error = np.linalg.norm(np.asarray(c.memories[0]['relative_xy_m'])-[1.5, .1])
    assert first_error < prior_error
    for t in (.3, .4, .5, .6):
        c.update_memory(t, None, [observation([1.5, .1])])
    assert np.linalg.norm(np.asarray(c.memories[0]['relative_xy_m'])-[1.5, .1]) < .1
    assert c.memories[0]['radius95_m'] < .6
    context = c.context()
    item = context['items'][0]
    assert context['schema'] == SCHEMA and item['frame'] == 'self/current'
    assert item['source'] == 'own_rgb+own_commands' and item['arrival_verified'] is False
    assert 'relative_xy_m' in item and context['held_world_reads'] == 0
    c.memories = [dict(kind='zone_marking', held_object_pose=[0, 0])]
    with pytest.raises(ValueError, match='WORLD_OR_HELD_INPUT_FORBIDDEN'):
        c.context()


def test_policy_turns_to_heading_and_refuses_blocked_forward_with_reason():
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    behind = c.step(0., None, [observation([-2., 0.])])
    assert behind['kind'] == 'turn' and behind['drive'][2] != 0
    ahead = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    action = ahead.step(0., None, [observation([2., 0.])])
    assert action['kind'] == 'forward'
    blocked = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    action = blocked.step(0., None, [observation([2., 0.])],
                          scan=dict(segments=[[[.05, .03], [.05, .08]]]))
    assert action['kind'] == 'avoid_turn' and action['stage'] == 'blocked'
    event = [e for e in blocked.events if e['reason'] == 'forward_blocked'][-1]
    assert event['blocked_object'] == 'observed_obstacle'
    assert event['minimum_gap_m'] == pytest.approx(.05, abs=.03)
    assert event['gap_status'] == 'measured'

