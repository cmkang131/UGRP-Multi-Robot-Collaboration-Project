"""PR #206 review 5: conflicting holding judgments must not hide cargo-wall contacts.

Real own-camera judgments on a blank fixture plus fake contacts; no MuJoCo physics.
"""
from __future__ import annotations

import copy
import types

import pytest

from tests.test_zone_own_executor import obs, rgb_of
from tests.test_zone_own_executor_review4 import cargo_host


def conflicting_carry(phase):
    host, ex, ctl = cargo_host()
    ctl.phase, ctl.skill.phase = 'skill', phase
    assert ctl.leg is None and ex.job.driver is None
    assert ex._holding_after['answer'] == 'no'
    ex.now = .1
    ex.last_report = ex.pose.report(ex.now)
    frame = obs('r1', 1, ex.now, ex.servo)
    assert ex._judge(ex.now, frame, rgb_of(frame), ex.last_report)
    check = ex.holding()
    assert check['camera_check']['answer'] == 'no'
    assert check['camera_check']['confidence'] == pytest.approx(.75)
    assert check['answer'] == 'unknown' and check['conflict']
    assert not ex.loaded  # Keep the existing control-side load assumption unchanged.
    return host, ex, ctl


def wall_contact(reverse, cargo_geom=10):
    pair = (cargo_geom, 99) if reverse else (99, cargo_geom)
    return types.SimpleNamespace(ncon=1, contact=[types.SimpleNamespace(geom1=pair[0], geom2=pair[1])])


@pytest.mark.parametrize('phase', ['to_carry_posture', 'nav_preplace', 'grip_check', 'pre_release'])
@pytest.mark.parametrize('reverse', [False, True], ids=['wall-cargo', 'cargo-wall'])
def test_p2_conflicting_holding_preserves_unreleased_cargo_contacts(phase, reverse):
    host, ex, _ = conflicting_carry(phase)
    before = copy.deepcopy((ex.status(), ex.belief_projection(), ex.events, ex.api_log,
                            ex.judgment_log, ex.servo, ex._holding_after, ex.pose.loc.commands))
    kinds, fingers = host._contact_kinds(wall_contact(reverse))
    host._record_contacts(ex.now, kinds)
    assert kinds['r1'] == {'wall', 'cargo_wall'}
    assert kinds['r2'] == kinds['r3'] == set() and not any(fingers.values())
    assert host.eval_only['kind_steps']['r1'] == {'wall': 1, 'cargo_wall': 1}
    assert {(row['robot_id'], row['kind']) for row in host.eval_only['contacts']} == {
        ('r1', 'wall'), ('r1', 'cargo_wall')}
    assert not ex.loaded
    assert (ex.status(), ex.belief_projection(), ex.events, ex.api_log,
            ex.judgment_log, ex.servo, ex._holding_after, ex.pose.loc.commands) == before


@pytest.mark.parametrize('state', ['released', 'unheld', 'unassigned'])
@pytest.mark.parametrize('reverse', [False, True], ids=['wall-cargo', 'cargo-wall'])
def test_p2_conflict_fallback_does_not_attribute_other_cargo_states(state, reverse):
    host, ex, ctl = conflicting_carry('nav_preplace')
    if state == 'released':
        # A confirmed release must override the evaluation fallback even if held is stale.
        ctl.skill.events.append({'event': 'release_confirmed'})
    elif state == 'unheld':
        ctl.skill.box.held = False
    assert not ex.loaded
    kinds, fingers = host._contact_kinds(wall_contact(reverse, 11 if state == 'unassigned' else 10))
    assert not any(kinds.values()) and not any(fingers.values())
