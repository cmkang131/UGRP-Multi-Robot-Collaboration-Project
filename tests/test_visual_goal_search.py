import math
import numpy as np
import cv2
import pytest

from sim.visual_goal_search import (TURN_STEP_RAD, VisualGoalSearch, Options, OPTION,
                                    paint_components, component_clear, signed_turn_wheels,
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
