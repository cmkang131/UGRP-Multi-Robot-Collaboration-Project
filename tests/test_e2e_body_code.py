"""Strong rule and terminal-idle dispatch checks; no model or simulation."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import e2e_body_code as m
from harness import e2e_body_semantics as sem
from tests.test_e2e_body_controller import fixture


def gate(phase='mapping', complete=False):
    old, tr, robots, _ = fixture(phase, complete, send=lambda p: pytest.fail('code must never call a provider'))
    g = m.CodeBodyGate(tr, robots, old.client, profiles={})
    for robot in robots.values():
        robot.nav_command = sem.pulse('forward_short')
    return g, tr, robots


def terminal(g, robots, rid='r2'):
    n = NS(finished=True, failed=False, phase=None, sweep_pending=None, blacklist=[[1, 2]], visited=[[3, 4]],
           reset_action=lambda: None, target=None, path=[], locked=False)
    robots[rid].goal.explorer.navigator = n
    robots[rid].goal.stage = 'explore'; robots[rid].goal.done = False
    return n


def test_code_dispatch_zero_provider_no_fake_api_wait():
    g, _, _ = gate()
    emitted = g.filter(0, [('r1', sem.pulse('forward_short'))])
    assert g.rows[-1]['choice'] == 'follow_own_path' and g.rows[-1]['sim_hold_s'] == 0
    emitted += g.filter(.2, [('r1', sem.pulse('forward_short'))])
    assert any(c.get('forward', 0) > 0 for _, c in emitted)
    s = g.summary()
    assert s['decisions'] == 1 and s['calls'] == s['provider_calls'] == 0
    assert s['cost_usd'] == 0 and s['cost_unknown_calls'] == 0


def test_terminal_hold_replans_immediately_then_bounded_recovery_preserves_pose():
    g, _, robots = gate()
    n = terminal(g, robots)
    pose = robots['r2'].goal.explorer.local_pose.copy()
    g.filter(67.2, [('r2', {'kind': 'hold'})])
    assert g.rows[-1]['choice'] == 'replan_frontier' and not n.finished
    assert g.replan_counts['r2'] == 1
    np.testing.assert_array_equal(pose, robots['r2'].goal.explorer.local_pose)
    assert not n.blacklist and not n.visited
    # No frontier on the next own image: do not repeat replan or wait 30 s.
    n.finished = True
    g.filter(67.4, [('r2', {'kind': 'hold'})])
    assert len(g.rows) == 1
    g.filter(67.85, [('r2', {'kind': 'hold'})])
    g.filter(67.9, [('r2', {'kind': 'hold'})])
    assert len(g.rows) == 2 and g.rows[-1]['choice'] not in (*m.WAIT, 'replan_frontier')


@pytest.mark.parametrize('guard', ['failed','done','handoff','packet','queued','clearance','r3'])
def test_terminal_recovery_does_not_steal_motion_ownership(guard):
    g, tr, robots = gate()
    n = terminal(g, robots)
    if guard == 'failed': n.failed = True
    elif guard == 'done': robots['r2'].goal.done = True
    elif guard == 'handoff': tr.state = 'align'
    elif guard == 'packet': robots['r2'].packet = {'own_route': True}
    elif guard == 'queued': tr.queue = [(70, 'r2', {'kind': 'arm'})]
    elif guard == 'clearance': tr.arm_clearance = NS(busy=lambda r: True)
    elif guard == 'r3':
        robots['r3'] = robots.pop('r2')
        assert not g.terminal_mapping('r3', 67.2)
        return
    assert not g.terminal_mapping('r2', 67.2)


def test_shared_safety_then_away_side_and_failed_opposite_detour():
    g, _, _ = gate()
    menu, proposal, facts = g.menu_direct('r1', 0, [sem.pulse('forward_short')])
    facts['peer_in_own_rgb'] = dict(visible=True, direction='left', distance='near', in_path=True, bearing_deg=30, half_width_deg=20)
    facts['blocked_persistently'] = True
    safe, choice, f = g.prepare_decision('r1', 0, 'motion', menu, proposal, facts)
    assert 'detour_left' not in safe and choice == 'detour_right'
    # Peer now ahead: the failed right side loses to a safe opposite side.
    facts['peer_in_own_rgb'] = dict(visible=True, direction='ahead', distance='near', in_path=True, bearing_deg=0, half_width_deg=10)
    g.memory['r1'].history.append(dict(t=0, choice='detour_right', status='ok', visual_before='visible', visual_after='visible', distance_change_m=0))
    _, choice, f = g.prepare_decision('r1', 1, 'motion', menu, proposal, facts)
    assert choice == 'detour_left' and f['same_stage_failure_memory']


def test_three_unchanged_choices_removed_and_stage_memory_reset():
    g, tr, _ = gate()
    menu, proposal, facts = g.menu_direct('r1', 0, [sem.pulse('forward_short')])
    for t in (1, 2, 3):
        g.memory['r1'].history.append(dict(t=t, choice='follow_own_path', status='ok', visual_before='visible', visual_after='visible', distance_change_m=0))
    safe, choice, f = g.prepare_decision('r1', 4, 'motion', menu, proposal, facts)
    assert 'follow_own_path' not in safe and choice not in m.WAIT
    tr.state = 'align'
    assert not g.facts('r1', 5)[0]['recent_decisions']


def test_safety_wait_survives_repetition_and_agreement_guard():
    g, _, _ = gate('grasp_lift')
    facts = g.facts('r1', 0)[0]
    choice, _ = g.decide('r1', 0, 'grasp_lift', g.batch_menu('grasp_lift'), 'grasp_and_lift', facts)
    assert choice == 'wait_and_reobserve'
    assert not g.rows[-1]['provider_called']


def test_exhausted_alignment_recoveries_offer_safe_opposite_viewpoint():
    g, _, _ = gate('align')
    g.facts('r1', 0)
    g.memory['r1'].tried = ['recover_wide_view', 'recover_standoff', 'recover_camera_pan', 'recover_detour_left']
    menu, proposal, facts = g.menu_direct('r1', 61, [sem.pulse('forward_short')])
    assert 'recover_detour_right' in menu
    _, choice, _ = g.prepare_decision('r1', 61, 'motion', menu, proposal, facts)
    assert choice == 'recover_detour_right'


def test_code_install_needs_no_relay_or_credentials(tmp_path, monkeypatch):
    from harness.e2e_body_controller import install
    old, tr, robots, _ = fixture()
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('unexpected network'))
    b = {'e2e_options': dict(body_controller='jev_v1', body_backend='code_v1', body_skills='bounded_v1')}
    g = install(tr, robots, b, tmp_path, tmp_path/'missing-receipt.json', Path(__file__).resolve().parents[1])
    assert isinstance(g, m.CodeBodyGate) and g.client is None


def test_actual_native_planner_resumes_from_saved_terminal_fixture():
    from scripts.replay_e2e_idle import restored, FIXTURE
    goal, nav, costmap, pose = restored(json.loads(FIXTURE.read_text())[0], 'off')
    g, _, robots = gate()
    rid = goal.robot_id
    robots[rid].goal = goal
    goal.explorer.local_pose = pose
    before = costmap.raw.copy()
    g.filter(0, [(rid, {'kind': 'hold'})])
    assert g.rows[-1]['choice'] == 'replan_frontier'
    action, trace = goal.receive(robot_id=rid, t=.2)
    assert action.get('turn', 0) != 0 or action.get('forward', 0) != 0
    np.testing.assert_array_equal(before, costmap.raw)


def test_toggle_identity():
    b = {'execution_bundle_id': 'e2e18-v344', 'e2e_options': {'body_backend': 'liquid_d1'}}
    old = copy.deepcopy(b)
    assert m.compose(b) == () and b == old
    m.compose(b, True)
    assert m.parent_for_validation(b)['execution_bundle_id'] == 'e2e18-v344'
