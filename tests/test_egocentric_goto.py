import math
import numpy as np
import pytest

from harness.egocentric_goto import (
    DECLARED_TARGET_HUE, OPTION, SCHEMA, EgocentricGoto, command_delta, duty,
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


def far_observation(xy, area, hue):
    item = observation(xy, area=area)
    item.update(hue=hue, pixels=200)
    return item


def far_reasons(controller):
    return [e['reason'] for e in controller.events
            if e['reason'].startswith('far_candidate')]


def test_far_candidate_default_off_is_inert():
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12)
    for i in range(8):
        action = c.step(.1*i, forward_command() if i else None,
                        [far_observation([-1., -.2], .02+.01*i, 12)])
    assert action['kind'] == 'search' and action['drive'] == [0., 0., 1.]
    assert not c.memories and not c.done and c.far_candidate_state is None
    assert far_reasons(c) == []
    with pytest.raises(ValueError, match='INVALID_FAR_CANDIDATE_FLAG'):
        EgocentricGoto(option=OPTION, footprint_radius_m=.12,
                       far_candidate='yes')


def test_far_candidate_fails_closed_without_a_declared_hue_class():
    # Fail-closed only when the task/detector profile declares no target hue
    # class; an observed confirmation is never required and never used.
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True,
                       declared_target_hue=None)
    for i in range(8):
        action = c.step(.1*i, forward_command() if i else None,
                        [far_observation([-1., -.2], .02+.01*i, 12)])
    assert action['kind'] == 'search' and not c.memories and not c.done
    assert 'far_candidate_accepted' not in far_reasons(c)
    assert 'far_candidate_turn' not in far_reasons(c)
    rejected = [e for e in c.events if e['reason'] == 'far_candidate_rejected']
    assert rejected and rejected[-1]['reason_category'] == 'hue_reference_unavailable'
    assert rejected[-1]['blocked_object'] == 'orange_object_below_zone_marking_area'
    assert rejected[-1]['minimum_gap_m'] is None
    assert rejected[-1]['gap_status'] == 'not_measured'
    with pytest.raises(ValueError, match='INVALID_DECLARED_TARGET_HUE'):
        EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True,
                       declared_target_hue=200.)
    with pytest.raises(ValueError, match='INVALID_DECLARED_TARGET_HUE_TOLERANCE'):
        EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True,
                       declared_target_hue_tolerance=-1.)


def test_far_candidate_is_only_a_search_turn_hint():
    # The declared task-map hue class is available before any confirmation.
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True)
    for i in range(4):
        action = c.step(.1*i, forward_command() if i else None,
                        [far_observation([-1., -.2], .02, 12)])
    assert action['drive'] == [0., 0., 1.] and 'far_candidate_accepted' not in far_reasons(c)
    action = c.step(.4, forward_command(), [far_observation([-1., -.2], .03, 12)])
    assert action['kind'] == 'search' and action['drive'] == [0., 0., -1.]
    assert 'far_candidate_accepted' in far_reasons(c)
    turn = [e for e in c.events if e['reason'] == 'far_candidate_turn'][-1]
    assert turn['turn_sign'] == -1 and turn['hue'] == 12
    assert turn['declared_hue'] == pytest.approx(DECLARED_TARGET_HUE)
    assert turn['confirmed_hue'] is None
    assert turn['blocked_object'] == 'orange_object_below_zone_marking_area'
    assert turn['minimum_gap_m'] is None and turn['gap_status'] == 'not_measured'
    assert not c.memories and not c.done and c.seen_target is False


def test_far_candidate_uses_the_declared_hue_class_not_observations():
    # The old defect: no accepted marking yet -> hue_reference_unavailable.
    # Now a red-cargo patch (hue 1) is rejected against the declared orange
    # class even if some earlier observation had set confirmed_hue to 1.
    c = EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True)
    c.confirmed_hue = 1.
    for i in range(6):
        c.step(.1*i, forward_command() if i else None,
               [far_observation([-1., -.2], .02+.002*i, 1)])
    rejected = [e for e in c.events if e['reason'] == 'far_candidate_rejected']
    assert rejected[-1]['reason_category'] == 'hue_mismatch'
    assert rejected[-1]['hue'] == 1 and rejected[-1]['frames'] >= 2
    assert rejected[-1]['declared_hue'] == pytest.approx(DECLARED_TARGET_HUE)
    # Hue 13 is the measured p90 of the true marking, inside the class.
    edge = EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True)
    for i in range(6):
        edge.step(.1*(i+1), forward_command() if i else None,
                  [far_observation([-1., -.2], .02+.002*i, 13)])
    rejected = [e for e in edge.events if e['reason'] == 'far_candidate_rejected']
    assert rejected[-1]['reason_category'] != 'hue_mismatch'


def test_far_candidate_rejection_reasons_are_distinct():
    static = EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True)
    for i in range(6):
        static.step(.1*i, None, [far_observation([-1., -.2], .02+.002*i, 12)])
    rejected = [e for e in static.events if e['reason'] == 'far_candidate_rejected']
    assert rejected[-1]['reason_category'] == 'no_forward_approach'
    assert rejected[-1]['forward_approach'] is False
    cropped = EgocentricGoto(option=OPTION, footprint_radius_m=.12, far_candidate=True)
    for i in range(6):
        cropped.step(.1*i, forward_command() if i else None,
                     [far_observation([-1., -.2], .02, 12)])
    rejected = [e for e in cropped.events if e['reason'] == 'far_candidate_rejected']
    assert rejected[-1]['reason_category'] == 'no_area_growth'
    assert rejected[-1]['first_area_m2'] == pytest.approx(.02)
    assert not cropped.memories and not cropped.done

