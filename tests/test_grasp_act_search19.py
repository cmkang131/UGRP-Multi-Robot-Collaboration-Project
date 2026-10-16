"""Saved-input route pulse/peer admission, no simulator or renderer."""
import argparse
from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest
from harness.grasp_act_admission import recording_admission
from scripts.replay_grasp_act_search19 import BASE, KW
from sim.grasp_act_search15_modes import add_arguments, match, options
from sim.grasp_act_search19 import MODES, admitted, project_motion, body_fallback, BodyNavigation
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_visible_route import drive

DATA = json.loads((Path(__file__).parent/'fixtures/grasp_act_search19.json').read_text())
FIXTURE = DATA['rows']


def teacher(seed=315709):
    x = deepcopy(FIXTURE[str(seed)])
    t = VisibleOnlyGraspTeacher(x['rid'], 'blue' if seed == 315709 else 'teal',
                              {int(k): v for k, v in x['pwm'].items()}, **KW, **BASE, **MODES)
    t.folded_ready = True
    t.started = True
    t.phase = 'approach'
    t.path = x['path']
    t.sampled_stance = True
    t.approach_plan_valid = True
    return t, x


@pytest.mark.parametrize('key', MODES)
def test_off_by_default_cli_and_admission_bind_each_toggle(key):
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    assert options(parser.parse_args([]))[key] == 'off'
    assert key in inspect.signature(recording_admission).parameters
    with pytest.raises(ValueError, match=key):
        match({}, {key: MODES[key]}, 'recording')
    args = parser.parse_args(['--'+key.replace('_', '-'), MODES[key]])
    assert options(args)[key] == MODES[key]
    x = FIXTURE['315709']
    t = VisibleOnlyGraspTeacher('r1', 'blue', x['pwm'], **KW, **BASE)
    assert t.search15_modes[key] == 'off'


def test_failed_legacy_route_pulse_has_a_safe_progressing_issued_alternative():
    t, x = teacher()
    w = x['world']
    now = w['t']
    value = t._continuous(now, **drive(x['pose'], x['goal'], x['waypoint'], w['beam']['ends'][t.end]))
    before = dict(t.sink.pwm)
    assert not admitted(t, w, value, before)
    replacement = project_motion(t, w, value, before, now)
    assert replacement != value and any(replacement['wheels'])
    assert replacement['pwm'] == value['pwm']
    assert admitted(t, w, replacement, before)
    assert t.search19_log[-1]['event'] == 'route_pulse_projected'
    # Every already admitted pulse remains byte-for-byte identical.
    assert project_motion(t, w, replacement, before, now) == replacement
    for phase in ('align', 'ready', 'pick', 'complete'):
        t.phase = phase
        assert project_motion(t, w, value, before, now) == value


def test_genuine_peer_arm_obstruction_keeps_wait_and_original_budget():
    t, x = teacher(8311711)
    t.peer_wait_since = x['peer_wait_since']
    t.peer_wait_ids = set(x['peer_wait_ids'])
    t.peer_route_next = 0.
    before = (t.peer_wait_since, set(t.peer_wait_ids), t.outcome)
    selected, _ = body_fallback(t, x['world'], x['world']['t'])
    assert selected is None
    assert (t.peer_wait_since, t.peer_wait_ids, t.outcome) == before
    assert t.search19_log[-1]['feasible'] == 0


def test_search19_cannot_silently_enable_the_rejected_footprint():
    x = FIXTURE['315709']
    with pytest.raises(ValueError, match='footprint off'):
        VisibleOnlyGraspTeacher('r1', 'blue', x['pwm'], **KW,
                               **{**BASE, **MODES, 'search18_footprint': 'search18_footprint_v1'})


def test_failed_replan_cannot_unlatch_arm_sweep_checks(monkeypatch):
    t, x = teacher()
    t.search19_body_active = True
    def failed_replan(world, now, *, permit_pick):
        t.sampled_stance = False
        return t._hold(now), False
    monkeypatch.setattr(t, '_step', failed_replan)
    t.step(x['world'], x['world']['t'])
    assert t.sampled_stance


@pytest.mark.parametrize('seed,feasible', [(8311709, True), (8311723, False)])
def test_fallback_separates_saved_disc_false_rejection_from_real_cargo_overlap(seed, feasible):
    x = DATA['blocked'][str(seed)]
    t = VisibleOnlyGraspTeacher('r1', 'blue', x['pwm'], **KW, **BASE, **MODES)
    t.folded_ready = True
    selected, checked = body_fallback(t, x['world'], x['world']['t'])
    assert (selected is not None) == feasible
    assert t.search19_body_active == feasible
    if feasible:
        nav = BodyNavigation(t, x['world'])
        radius, ds, rs = t._constraints(x['world'])
        assert nav.free(selected['goal'], ds, rs, radius)
        assert all(nav.segment_free(a, b, ds, rs, radius)
                   for a, b in zip(selected['path'], selected['path'][1:]))
    else:
        assert all(c['reason'] != 'feasible' for c in checked)
