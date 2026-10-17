import math
import numpy as np
import cv2
import pytest

from sim.visual_goal_search import (TURN_STEP_RAD, VisualGoalSearch, Options, OPTION,
                                    EXPANDING_OPTION, EXPANDING_LEG_TICKS,
                                    ARRIVAL_AIM_INSET_M,
                                    paint_components, component_clear, signed_turn_wheels,
                                    mirrored_pulse_delta, MIRROR_OPTION,
                                    _point_covariance)


def _hsv_image(hue, s=200, v=150, rect=(200, 150, 120, 80)):
    hsv = np.zeros((480, 640, 3), np.uint8)
    hsv[..., 1] = 10
    hsv[..., 2] = 80
    x, y, w, h = rect
    hsv[y:y + h, x:x + w] = (hue, s, v)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def test_toggle_default_off_and_unknown():
    off = VisualGoalSearch()
    out = off.control(0.0, paint={}, walls=(), obstacles=())
    assert out['status'] == 'off' and out['stop'] and not out['found']
    with pytest.raises(ValueError):
        VisualGoalSearch(option='on')
    # The stored r2 pulse is positive yaw; the sign must follow the action.
    pulse = [-.35, .35, -.35, .35]
    assert signed_turn_wheels(+1, pulse) == pulse
    assert signed_turn_wheels(-1, pulse) == [.35, -.35, .35, -.35]


def test_destination_colour_component_and_wall_hue_rejection():
    blue = _hsv_image(110)
    comp = paint_components(blue, (104, 120))
    assert comp['reason'] == 'destination_colour_observed'
    assert comp['pixels'] >= 9000
    assert comp['bbox'][0] <= 200 and comp['bbox'][1] <= 150
    # v5 indigo wall hue is outside the destination band.
    wall = _hsv_image(133, s=81, v=110)
    assert paint_components(wall, (104, 120))['pixels'] == 0
    # v5 floor hue 108 is inside the band, but its measured S<=77 must not be
    # mistaken for paint (the preflight false positive on 2026-10-17).
    floor = _hsv_image(108, s=66, v=155, rect=(0, 60, 640, 360))
    assert paint_components(floor, (104, 120))['pixels'] == 0
    mid = _hsv_image(110, s=105, v=155, rect=(0, 60, 640, 360))
    assert paint_components(mid, (104, 120))['reason'] == 'destination_colour_absent'
    # A same-colour patch below the far gate is not a landmark hint.
    small = _hsv_image(110, rect=(300, 300, 8, 8))
    assert paint_components(small, (104, 120))['reason'] == 'destination_component_small'
    # The fitted-segment helper is restricted to the accepted component.
    clear = component_clear(comp)
    assert clear is not None and int(clear.sum()) >= comp['pixels']


def test_state_machine_look_wall_follow_gap_and_arrival():
    s = VisualGoalSearch(option=OPTION)
    # No cue: a full calibrated in-place scan (Nav2 Spin-style relative yaw).
    rounds = int(round(2 * math.pi / TURN_STEP_RAD))
    for i in range(rounds):
        a = s.control(i * 0.1, paint={}, walls=(), obstacles=())
        assert a['exact_turn'] == 1 and s.stage == 'orient'
    # After the scan a wall ahead is approached.
    wall = [dict(relative_xy_m=[1.2, 0.0], range_m=1.2, bearing_rad=0.0)]
    a = s.control(rounds * 0.1, paint={}, walls=wall, obstacles=())
    assert s.stage == 'approach_wall' and a['forward'] > 0
    # Close wall: turn left 90 deg to follow north with the wall on the right.
    wall = [dict(relative_xy_m=[0.5, 0.0], range_m=0.5, bearing_rad=0.0)]
    a = s.control((rounds + 1) * 0.1, paint={}, walls=wall, obstacles=())
    assert s.stage == 'follow_north' and a['exact_turn'] == 1
    t = (rounds + 2) * 0.1
    right = [dict(relative_xy_m=[0.2, -0.55], range_m=0.585, bearing_rad=math.radians(-70))]
    while s.turn_left > 0:
        s.control(t, paint={}, walls=right, obstacles=())
        t += 0.1
    s.control(t, paint={}, walls=right, obstacles=())
    t += 0.1
    assert s.stage == 'follow_north'
    a = s.control(t, paint={}, walls=right, obstacles=())
    assert a['forward'] > 0
    # Side wall disappears for three ticks: open the door/gap procedure.
    t += 0.1
    for _ in range(3):
        s.control(t, paint={}, walls=(), obstacles=())
        t += 0.1
    assert s.stage in ('gap_cross', 'gap_forward')
    assert any(e.get('stage_reason') == 'side_wall_gap_observed' for e in s.events)
    # Far destination colour: aim at it, then acquire the metric patch.
    s = VisualGoalSearch(option=OPTION)
    p = dict(pixels=800, bearing_rad=0.2, nearest_range_m=2.0, lower_centre_pixels=0,
             relative_xy_m=[1.9, 0.4], range_m=1.94)
    a = s.control(0.0, paint=p, walls=(), obstacles=())
    assert s.stage == 'target' and a['exact_turn'] == 1
    obs = s.memory_observation(1.0, (0.8, 0.0), dict(pixels=900))
    assert obs['kind'] == 'destination_zone' and s.found
    mem = [dict(relative_xy_m=[0.08, 0.0], range_m=0.08, bearing_rad=0.0, age_s=0.0,
                covariance_m2=_point_covariance((0.08, 0.0)).tolist())]
    p = dict(pixels=4000, bearing_rad=0.0, nearest_range_m=0.4, lower_centre_pixels=900,
             relative_xy_m=[0.4, 0.0], range_m=0.4)
    a = s.control(1.1, paint=p, walls=(), obstacles=(), memories=mem, patch_ok=True,
                  patch_xy=(0.08, 0.0))
    assert s.stage == 'approach'
    a = s.control(1.2, paint=p, walls=(), obstacles=(), memories=mem, patch_ok=True,
                  patch_xy=(0.08, 0.0))
    assert s.arrived and a['stop']
    # Empty scan (no wall foot projectable at long range): drive the initial
    # heading until the wall enters the 1.6 m fitted range.
    s = VisualGoalSearch(option=OPTION)
    for i in range(rounds):
        s.control(i * 0.1, paint={}, walls=(), obstacles=())
    a = s.control(rounds * 0.1, paint={}, walls=(), obstacles=())
    assert s.stage == 'seek_wall' and a['forward'] > 0
    wall = [dict(relative_xy_m=[1.5, 0.0], range_m=1.5, bearing_rad=0.0)]
    a = s.control((rounds + 1) * 0.1, paint={}, walls=wall, obstacles=())
    assert s.stage == 'approach_wall' and a['forward'] > 0


def test_approach_wall_accepts_seek_handover_range():
    # r4 west e00 handed over at 1.58 m but approach_wall only looked inside
    # 1.2 m, counted ten missing ticks, and restarted the scan.
    s = VisualGoalSearch(option=OPTION)
    s.stage = 'approach_wall'
    s.stage_t = 0.0
    wall = [dict(relative_xy_m=[1.5, 0.03], range_m=1.5, bearing_rad=0.02)]
    for i in range(12):
        a = s.control(i * 0.1, paint={}, walls=wall, obstacles=())
        assert s.stage == 'approach_wall'
        assert a['forward'] > 0
    # r6 west e00 handed over from the full scan at 2.71 m; the old 1.8 m
    # acceptance counted ten missing ticks and restarted the 27 s scan.
    s = VisualGoalSearch(option=OPTION)
    s.stage = 'approach_wall'
    s.stage_t = 0.0
    far = [dict(relative_xy_m=[2.7, 0.0], range_m=2.7, bearing_rad=0.0)]
    for i in range(12):
        a = s.control(i * 0.1, paint={}, walls=far, obstacles=())
        assert s.stage == 'approach_wall'
        assert a['forward'] > 0
    # A loose cargo cube in the seek cone must cause one bounded away-turn,
    # not abandon the divider for the lawnmower (r5 west e00).
    s = VisualGoalSearch(option=OPTION)
    s.stage = 'seek_wall'
    s.stage_t = 0.0
    cube = [dict(kind='cyan', xy=[0.45, -0.15], radius=0.03)]
    s.control(0.0, paint={}, walls=(), obstacles=cube)
    assert s.stage == 'seek_wall' and s.turn_left >= 10
    turned = 0
    t = 0.1
    while s.turn_left > 0:
        a = s.control(t, paint={}, walls=(), obstacles=())
        assert a['exact_turn'] == 1
        turned += 1
        t += 0.1
    assert turned >= 10
    a = s.control(t, paint={}, walls=(), obstacles=())
    assert s.stage == 'seek_wall' and a['forward'] > 0


def test_freshest_memory_wins_and_stale_memory_cannot_arrive():
    s = VisualGoalSearch(option=OPTION)
    s.stage = 'approach'
    s.stage_t = 0.0
    stale = dict(relative_xy_m=[0.2, 0.0], range_m=0.2, bearing_rad=0.0, age_s=32.0,
                 covariance_m2=_point_covariance((0.2, 0.0)).tolist())
    fresh = dict(relative_xy_m=[0.8, 0.0], range_m=0.8, bearing_rad=0.0, age_s=0.0,
                 covariance_m2=_point_covariance((0.8, 0.0)).tolist())
    a = s.control(1.0, paint={}, memories=[stale, fresh], patch_ok=True,
                  patch_xy=(0.8, 0.0))
    assert not s.arrived and a['forward'] > 0  # toward fresh 0.8 m, not stale 0.2 m
    a = s.control(1.1, paint={}, memories=[stale])
    assert not s.arrived and a['stop']


def test_expanding_search_is_default_off_and_schedule_does_not_close():
    # Default off: the gate-r4 square schedule is unchanged.
    off = VisualGoalSearch(option=OPTION)
    off._enter_east_search(0.0, reason='test')
    assert off.leg_len == 20 and off._turn_sign == -1
    off._next_leg(0.1, 'leg_complete')
    off._next_leg(0.2, 'leg_complete')
    off._next_leg(0.3, 'leg_complete')
    off._next_leg(0.4, 'leg_complete')
    assert off.leg == 0 and off.leg_len == 28  # 4-leg square grows only after 4 legs
    # Candidate C: first stroke is the gate-r4 2.6-4.4 m bound at the measured
    # 0.0128 m/tick (344 ticks), then the recorded lawnmower schedule, with a
    # right turn at every stroke so the parallel lines step off the start.
    s = VisualGoalSearch(option=OPTION, options=Options(
        expanding_search=True, arrival_aim_inset_m=ARRIVAL_AIM_INSET_M))
    s._enter_east_search(0.0, reason='test')
    assert s.leg_schedule == EXPANDING_LEG_TICKS
    assert s.leg_len == EXPANDING_LEG_TICKS[0] == 344
    assert s.turn_left == 69 and s._turn_sign == -1
    for want in EXPANDING_LEG_TICKS[1:]:
        s._next_leg(0.1, 'leg_complete')
        assert s.leg_len == want and s._turn_sign == -1
    # Exhausted schedule grows the last stroke instead of closing a square.
    last = s.leg_len
    s._next_leg(0.2, 'leg_complete')
    assert s.leg_len == min(400, last + 60) and s.leg == len(EXPANDING_LEG_TICKS) - 1


def test_arrival_aim_inset_moves_the_target_inward_and_keeps_tolerance():
    paint = dict(pixels=4000, bearing_rad=0.0, nearest_range_m=0.4,
                 lower_centre_pixels=900, relative_xy_m=[0.4, 0.0], range_m=0.4)
    mem_at = lambda x: [dict(relative_xy_m=[x, 0.0], range_m=abs(x), bearing_rad=0.0,
                             age_s=0.0, covariance_m2=_point_covariance((x, 0.0)).tolist())]
    # Gate-r4 false arrival: on-paint, fresh memory, base->point 0.098 m <= the
    # unchanged 0.10 m tolerance.  Default still declares there.
    a = VisualGoalSearch(option=OPTION)
    a.stage = 'approach'; a.stage_t = 0.0
    out = a.control(1.0, paint=paint, walls=(), obstacles=(), memories=mem_at(0.098),
                    patch_ok=True, patch_xy=(0.098, 0.0))
    assert a.arrived and out['stop']
    # Candidate C aims 0.142 m past the point: same geometry keeps driving.
    s = VisualGoalSearch(option=OPTION, options=Options(
        expanding_search=True, arrival_aim_inset_m=ARRIVAL_AIM_INSET_M))
    s.stage = 'approach'; s.stage_t = 0.0
    out = s.control(1.0, paint=paint, walls=(), obstacles=(), memories=mem_at(0.098),
                    patch_ok=True, patch_xy=(0.098, 0.0))
    assert not s.arrived and out['forward'] > 0
    # 0.06 m past the remembered point leaves the aim 0.082 m ahead: declare.
    out = s.control(1.1, paint=paint, walls=(), obstacles=(), memories=mem_at(-0.06),
                    patch_ok=True, patch_xy=(-0.06, 0.0))
    assert s.arrived and out['stop']
    assert any(e.get('aim_inset_m') == pytest.approx(ARRIVAL_AIM_INSET_M)
               for e in s.events)


def test_mirror_pulse_toggle_is_signature_gated_and_preserves_default():
    cal = dict(
        wheels=[-.35, .35, -.35, .35],
        duration_s=[0.027857142857142865] * 4,
        interval_s=0.1,
        mean_delta=[-8.834147012334151e-05, -2.0642641055137426e-04,
                    0.02292102597657116],
        qualified_servo={1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500},
        predictive_covariance=[[5.84e-06, -7.29e-07, 3.45e-07],
                               [-7.29e-07, 1.62e-06, -2.15e-07],
                               [3.45e-07, -2.15e-07, 3.97e-05]],
        source_sha256='test')
    servo = dict(cal['qualified_servo'])
    left = dict(wheels=list(cal['wheels']), duration_s=list(cal['duration_s']))
    right = dict(wheels=[-w for w in cal['wheels']],
                 duration_s=list(cal['duration_s']))
    # Default off: the module is unchanged unless the runner opts in, and the
    # helper itself never claims the calibrated left pulse.
    assert VisualGoalSearch().control(0.0, paint={}, walls=(),
                                      obstacles=())['status'] == 'off'
    assert mirrored_pulse_delta(left, cal, servo, servo, 0.1) is None
    m = mirrored_pulse_delta(right, cal, servo, servo, 0.1)
    assert m['source'] == MIRROR_OPTION
    assert m['delta'] == pytest.approx([cal['mean_delta'][0],
                                        -cal['mean_delta'][1],
                                        -cal['mean_delta'][2]])
    assert m['covariance'][0][2] == pytest.approx(-cal['predictive_covariance'][0][2])
    # Both indices of the (y, yaw) block flip, so that entry keeps its sign.
    assert m['covariance'][2][1] == pytest.approx(cal['predictive_covariance'][2][1])
    assert m['covariance'][1][1] == pytest.approx(cal['predictive_covariance'][1][1])
    # Unqualified servo state, interval or command signature must not match.
    assert mirrored_pulse_delta(right, cal, {**servo, 1: 1900}, servo, 0.1) is None
    assert mirrored_pulse_delta(right, cal, servo, {**servo, 5: 999}, 0.1) is None
    assert mirrored_pulse_delta(right, cal, servo, servo, 0.05) is None
    assert mirrored_pulse_delta(dict(wheels=[-w * .5 for w in cal['wheels']],
                                     duration_s=cal['duration_s']),
                                cal, servo, servo, 0.1) is None
    assert mirrored_pulse_delta(dict(wheels=right['wheels'], duration_s=[0.1] * 4),
                                cal, servo, servo, 0.1) is None
    assert mirrored_pulse_delta(None, cal, servo, servo, 0.1) is None
