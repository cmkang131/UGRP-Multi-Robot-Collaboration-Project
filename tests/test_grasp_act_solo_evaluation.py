import math
import pytest
from sim.grasp_act_solo_evaluation import bottom_z, Score
from sim.grasp_act_solo_teacher import VisibilityStats

I = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]


def test_clearance_uses_object_bottom_and_cylinder_axis():
    assert bottom_z('box', (0., 0., .018), I, (.03, .02, .006)) == pytest.approx(.012)
    assert bottom_z('cylinder', (0., 0., .037), I, (.019, .025)) == pytest.approx(.012)
    a = math.pi/6
    R = [[math.cos(a), 0., math.sin(a)], [0., 1., 0.], [-math.sin(a), 0., math.cos(a)]]
    assert bottom_z('cylinder', (0., 0., .1), R, (.019, .025)) == pytest.approx(.1-.019*.5-.025*math.cos(a))


def test_initial_floor_time_never_counts_as_postlift_release():
    score = Score()
    floor = dict(min_z=0., support_z=0., tilt_deg=0., finger_forces=[0., 0.], speed=0.,
                 open_issued=True, placement_offset=0., weld_active=False)
    for i in range(31):
        score.add(i*.1, **floor)
    assert not score.record(True)['release_success']
    lift = {**floor, 'min_z': .02, 'finger_forces': [.6, .6], 'open_issued': False}
    for i in range(31, 63):
        score.add(i*.1, **lift)
    assert score.record(False)['lift_success']
    assert not score.record(False)['physical_success']
    for i in range(63, 85):
        score.add(i*.1, **floor)
    assert score.record(True)['physical_success']
    with pytest.raises(ValueError, match='WELD'):
        score.add(8.5, **{**floor, 'weld_active': True})


def test_visibility_is_time_weighted_and_spans_phase_boundary():
    v = VisibilityStats()
    v.add(0., 'descent', False)
    v.add(.1, 'close', False)
    v.add(.2, 'close', True)
    v.add(.3, 'close', True)
    d = v.record()
    assert d['max_invisible_s'] == pytest.approx(.2)
    assert d['by_phase']['descent']['visible_ratio'] == 0.
    assert d['by_phase']['close']['visible_ratio'] == pytest.approx(.5)
