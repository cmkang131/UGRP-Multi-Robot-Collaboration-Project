"""pairact P1 cand-1: rectangle align-pulse guard (default off)."""
import inspect

import pytest

from sim.grasp_act_align_guard import MODE, MODE_KEY, rect_clear, rect_pulse_free
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_search17 import pulse_free
from tests_helpers_r3 import teacher  # noqa: F401  (shim below)


def _forward(t):
    return t._continuous(10., .03, 0., 0.)   # 0.35 board speed, ~4.6 mm forward


def test_registered_default_off_and_plumbed():
    assert ALL_MODES[MODE_KEY] == MODE
    from scripts.run_grasp_act_teacher import run
    assert MODE_KEY in inspect.signature(run).parameters
    t = teacher()
    t.phase = 'align'
    assert rect_clear(t, (0., 0., 0.), _forward(t), [], [], .13) is None


def test_rectangle_admits_pulse_the_circle_rejects():
    t = teacher()
    value = _forward(t)
    disc = [(.0925 + .03 + .010, 0., .03)]          # 10 mm ahead of the real front face
    assert not pulse_free((0., 0., 0.), value, disc, [], .13)   # circle: already inside, moving closer
    assert rect_pulse_free((0., 0., 0.), value, disc, []) is True


def test_rectangle_still_rejects_real_contact_and_defers_when_not_clear():
    t = teacher()
    value = _forward(t)
    assert rect_pulse_free((0., 0., 0.), value, [(.0925 + .03 + .003, 0., .03)], []) is False
    assert rect_pulse_free((0., 0., 0.), value, [(.0925 + .03 - .001, 0., .03)], []) is None
    wall = [(.0925 + .05 + .003, 0., .05, .5, 0.)]   # wall face 3 mm ahead
    assert rect_pulse_free((0., 0., 0.), value, [], wall) is False


def test_scope_align_folded_only():
    t = teacher(**{MODE_KEY: MODE})
    disc = [(.0925 + .03 + .010, 0., .03)]
    value = _forward(t)
    t.phase = 'align'
    assert rect_clear(t, (0., 0., 0.), value, disc, [], .13) is True
    assert rect_clear(t, (0., 0., 0.), value, disc, [], .17) is None      # unfolded arm
    t.phase = 'approach'
    assert rect_clear(t, (0., 0., 0.), value, disc, [], .13) is None
    t.phase = 'align'; t.search19_body_active = True
    assert rect_clear(t, (0., 0., 0.), value, disc, [], .13) is None
