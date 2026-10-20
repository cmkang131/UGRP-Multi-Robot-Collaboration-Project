"""pairact P1 cand-2b: align refresh keyed on the pulse path (default off)."""
import argparse
import inspect
from copy import deepcopy

from sim.grasp_act_align_refresh2 import MODE, MODE_KEY, maybe_begin, pulse_blockers, pulse_points
from sim.grasp_act_reobserve import remembered_blockers
from sim.grasp_act_search15_modes import ALL_MODES, add_arguments
from tests_helpers_r3 import teacher

POSE = [-.8, -.3, 0.]


def world(*observations):
    return {'t': 10., 'robots': {'r1': {'pose': list(POSE)}}, 'objects': {}, 'walls': [],
            'beam': {'pose': [0., 0., 0.], 'ends': {'teal': [-.27, 0., .024], 'blue': [.27, 0., .024]}},
            'visibility': {'r1': {'visible_probes': 15, 'peers': [], 'objects': [],
                                  'observations': {m['id']: deepcopy(m) for m in observations}}}}


def cargo(key, x, y, seen_t=0.):
    return {'kind': 'cargo', 'id': key, 'xyz': [x, y, .02], 'yaw': 0., 'radius': .03,
            'top_z_bound_m': .05, 'seen_t': seen_t}


# folded, low cargo: blocked if a sample is closer than .13 + .03 + .005 = .165 m
NEAR_AHEAD = cargo('red_1', POSE[0]+.168, POSE[1])   # clear of the pose, inside after a forward pulse


def _forward(t):
    return t._continuous(10., .03, 0., 0.)


def test_registered_default_off_and_plumbed():
    assert ALL_MODES[MODE_KEY] == MODE
    from scripts.run_grasp_act_teacher import run
    assert MODE_KEY in inspect.signature(run).parameters
    parser = argparse.ArgumentParser(); add_arguments(parser)
    assert getattr(parser.parse_args([]), MODE_KEY) == 'off'
    t = teacher(); t.phase = 'align'
    assert not maybe_begin(t, world(NEAR_AHEAD), _forward(t), t._hold(10.), 10.)
    assert t.reobserver.active is None


def test_pulse_path_finds_the_stale_obstacle_the_goal_rule_misses():
    t = teacher()
    w = world(NEAR_AHEAD)
    pts = pulse_points(POSE, _forward(t))
    assert pts[0] == tuple(POSE[:2]) and pts[-1][0] > POSE[0]
    # r14 v1 input: no blocked_goal stance (align stance is feasible) -> empty
    assert remembered_blockers(w, 'r1', [{'reason': 'feasible', 'goal': POSE[:2]}], True) == {}
    # start pose alone is clear; the pulse path enters the padded disc
    assert remembered_blockers(w, 'r1', [{'reason': 'blocked_goal', 'goal': POSE[:2]}], True) == {}
    assert set(pulse_blockers(w, 'r1', POSE, _forward(t), True)) == {'red_1'}


def test_pulse_blockers_keep_the_existing_exclusions():
    t = teacher()
    fresh = cargo('red_1', POSE[0]+.168, POSE[1], seen_t=10.)
    beam = {**cargo('beam_1', POSE[0]+.168, POSE[1]), 'id': 'beam_1'}
    far = cargo('red_2', POSE[0]+.5, POSE[1])
    assert pulse_blockers(world(fresh, beam, far), 'r1', POSE, _forward(t), True) == {}
    wall = {'kind': 'wall', 'id': 'wall_0', 'xyz': [POSE[0]+.13+.05+.002, POSE[1], .1],
            'half_extents': [.05, .5], 'yaw': 0., 'seen_t': 0.}
    assert set(pulse_blockers(world(wall), 'r1', POSE, _forward(t), True)) == {'wall_0'}


def test_rejected_align_pulse_starts_the_bounded_refresh():
    t = teacher(**{MODE_KEY: MODE}); t.phase = 'align'
    w = world(NEAR_AHEAD)
    assert maybe_begin(t, w, _forward(t), t._hold(10.), 10.)
    assert t.reobserver.active['kind'] == 'obstacle' and set(t.reobserver.active['targets']) == {'red_1'}
    assert t.recovery_log[-1]['event'] == 'align_refresh2_begin'
    # already active -> no second start
    assert not maybe_begin(t, w, _forward(t), t._hold(10.1), 10.1)


def test_scope_and_budget():
    w = world(NEAR_AHEAD)
    t = teacher(**{MODE_KEY: MODE}); t.phase = 'approach'
    assert not maybe_begin(t, w, _forward(t), t._hold(10.), 10.)
    t.phase = 'align'
    assert not maybe_begin(t, w, t._hold(10.), t._hold(10.), 10.)        # intentional hold
    assert not maybe_begin(t, w, _forward(t), _forward(t), 10.)          # pulse admitted
    assert t.reobserver.active is None
    t.reobserver.used['obstacle'] = t.reobserver.MAX_ENCOUNTERS          # budget spent before align
    assert not maybe_begin(t, w, _forward(t), t._hold(10.), 10.)
    assert t.search20_log[-1]['reason'] == 'obstacle_encounters_spent'
    n = len(t.search20_log)
    assert not maybe_begin(t, w, _forward(t), t._hold(10.1), 10.1)
    assert len(t.search20_log) == n                                       # skip logged once per reason
