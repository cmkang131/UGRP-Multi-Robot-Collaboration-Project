import math

import numpy as np
import pytest

from run_ras1_door_approach import blocked, choose_step


class VisibleProjection:
    use_raw = False

    def ground_pixels(self, points):
        return np.array([[180., 306.], [485., 308.]])


def door(heading=0., distance=.31, lateral=0.):
    n = np.array([math.cos(heading), math.sin(heading)])
    t = np.array([-n[1], n[0]])
    center = distance*n + lateral*t
    return dict(toward=n.tolist(), center=center.tolist(), wall_plane_m=distance,
                jambs=[(center + side*t).tolist() for side in (-.095,.095)])


def test_turns_body_toward_door_normal():
    assert choose_step(door(heading=-.45), VisibleProjection(), .22)[0] == 'rotate-right'


def test_corrects_lateral_alignment_before_forward():
    assert choose_step(door(lateral=.07), VisibleProjection(), .22)[0] == 'forward'
    action, _, _, bound = choose_step(door(), VisibleProjection(), .22)
    assert action == 'right'
    assert .31 - bound[0] >= .22


def test_stops_at_the_target_and_refuses_threshold_overrun():
    assert choose_step(door(distance=.222), VisibleProjection(), .22) is None
    with pytest.raises(ValueError, match='outside'):
        choose_step(door(distance=.095), VisibleProjection(), .13)


def test_obstacles_on_the_near_side_veto_the_step():
    opening = door()
    assert blocked(opening, [[.1,.03]], 'right', np.array([.06,0.]))
    assert not blocked(opening, [[.34,.03]], 'right', np.array([.06,0.]))
