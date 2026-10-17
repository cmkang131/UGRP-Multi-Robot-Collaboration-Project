import math
import numpy as np
import pytest

from harness.egocentric_goto import (
    OPTION, SCHEMA, WALL_KIND, WALL_OPTION, EgocentricGoto, command_delta, duty,
    point_covariance)


def observation(xy, area=.6):
    item = dict(id='detected-floor-target', kind='zone_marking', signature='floor_orange_zone_marking',
                relative_xy_m=list(xy), covariance_m2=point_covariance(xy).tolist())
    if area is not None:
        item['observed_area_m2'] = area
    return item


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
    searching = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    action = searching.step(0., None, [])
    assert action['kind'] == 'search' and action['target_range_m'] is None
    for i in range(30):
        action = searching.step(.1*(i+1), None, [])
    assert action['kind'] == 'search' and not searching.done
    # A one-off orange patch rejected by the EKF gate (e.g. a peer arm) must
    # not replace the repeatedly observed target memory.
    rejected = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    rejected.step(0., None, [observation([2., 0.])])
    action = rejected.step(.1, None, [observation([3.5, 0.])])
    assert action['target_source'] == 'memory'
    assert action['target_range_m'] == pytest.approx(2., abs=.2)
    assert any(e['reason'] == 'target_observation_rejected' for e in rejected.events)


def test_small_orange_object_cannot_birth_or_steer_the_target_memory():
    # gate-08 world02: a small orange patch (peer wheels, 0.005-0.024 m^2)
    # became the first landmark and pulled the robot away from the 0.44-0.86
    # m^2 floor marking.  Birth gate is fail-closed.
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    action = c.step(0., None, [observation([.15, -.99], area=.008)])
    assert action['kind'] == 'search' and not c.memories
    event = [e for e in c.events if e['reason'] == 'small_marking_rejected'][-1]
    assert event['blocked_object'] == 'orange_object_below_zone_marking_area'
    assert event['minimum_gap_m'] is None and event['gap_status'] == 'not_measured'
    assert event['observed_area_m2_min'] == pytest.approx(.008)
    no_area = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    action = no_area.step(0., None, [observation([2., 0.], area=None)])
    assert action['kind'] == 'search' and not no_area.memories
    action = c.step(.1, None, [observation([2., 0.], area=.6)])
    assert action['kind'] == 'forward' and len(c.memories) == 1



def wall_scan(*segments):
    return dict(segments=[list(segment) for segment in segments])


def test_wall_memory_default_off_does_not_change_control_or_construct_a_store():
    scan = wall_scan(([1.0, .8], [1.2, 1.1]))
    off = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    on = EgocentricGoto(option=OPTION, footprint_radius_m=.12,
                        wall_memory=WALL_OPTION)
    assert off.wall_enabled is False and off.wall_store is None
    assert on.wall_enabled is True and on.wall_store is not None
    # Separate store: wall slots can never evict the goal memory.
    assert on.memory is not on.wall_store
    commands = [None, forward_command(), forward_command(), None]
    for index, command in enumerate(commands):
        t = .1*index
        baseline = off.step(t, command, [observation([2., 0.])], scan=scan)
        candidate = on.step(t, command, [observation([2., 0.])], scan=scan)
        assert baseline == candidate
    assert [m['kind'] for m in off.memories] == ['zone_marking']
    assert off.wall_memories == []
    assert [m['kind'] for m in on.memories] == ['zone_marking']
    walls = [m for m in on.wall_memories if m['kind'] == WALL_KIND]
    assert len(walls) == 1
    goal = on.goal_memory()
    assert goal is not None and goal['kind'] == 'zone_marking'
    # The control-facing context stays target-only this round.
    assert [item['kind'] for item in on.context()['items']] == ['zone_marking']
    with pytest.raises(ValueError, match='UNKNOWN_EGONAV_WALL_MEMORY_OPTION'):
        EgocentricGoto(option=OPTION, wall_memory='on', footprint_radius_m=.12)


def test_wall_memory_uses_the_goal_memory_transport_and_records_reobservation_error():
    scan = wall_scan(([1.0, .5], [1.0, .9]))
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12,
                       wall_memory=WALL_OPTION)
    c.step(0., None, [observation([2., 0.])], scan=scan)
    wall = c.wall_memories[0]
    assert wall['kind'] == WALL_KIND and wall['observations'] == 1
    assert np.allclose(wall['relative_xy_m'], [1.0, .7], atol=1e-9)
    goal_before = np.asarray(c.memories[0]['relative_xy_m'], float)
    wall_before = np.asarray(wall['relative_xy_m'], float)
    command = forward_command()
    increment = np.asarray(command_delta(command), float)
    # No observations this tick: pure own-command transport, the same path
    # for the goal memory and the wall memory.
    c.update_memory(.1, command, [])
    goal_after = np.asarray(c.memories[0]['relative_xy_m'], float)
    wall_after = np.asarray(c.wall_memories[0]['relative_xy_m'], float)
    assert abs((goal_after[0]-goal_before[0]) + increment[0]) < 1e-9
    assert abs((wall_after[0]-wall_before[0]) - (goal_after[0]-goal_before[0])) < 1e-9
    # Re-observation is compared against the transported prior and the
    # corrected memory, using only this frame's own scan.
    c.step(.2, None, [observation([2., 0.])], scan=scan)
    assert c.wall_memory_errors
    error = c.wall_memory_errors[-1]
    assert error['t'] == pytest.approx(.2)
    assert error['prior_error_m'] < .05 and error['residual_m'] < .05
    assert c.wall_memories[0]['observations'] == 2
    summary = c.wall_memory_summary()
    assert summary['toggle'] == WALL_OPTION and summary['control_use'] is False
    assert summary['count'] == 1 and summary['events'].get('created') == 1
    assert summary['events'].get('reobserved') == 1
