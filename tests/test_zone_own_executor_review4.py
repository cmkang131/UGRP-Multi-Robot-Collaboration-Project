"""PR #206 review 4: gate-budget, cargo attribution and archived leg regressions.

Only scripted own estimates, fake ports and contact records; no MuJoCo world or physics.
"""
from __future__ import annotations

import copy
import json
import types

import pytest

from harness.owncam_drive import CARRY_POSTURE, SEARCH_POSE, SETTLE_S
from harness.zone_own_sweep import SWEEP_REOBSERVE_S
from tests.test_zone_own_executor import Driver
from tests.test_zone_own_executor_guards import scripted
from tests.test_zone_own_executor_host import FakeHost, start_hold, team
from tests.test_zone_own_executor_review3 import deliver_at, ready_gate


def gate_wait_executor(api):
    ex = scripted(lambda t: (1.85, -.70, 0., .055, .02, .1))
    driver = Driver(ex)
    ack = ex.look_around() if api == 'look_around' else ex.deliver('o1', 'A2')
    assert ack['accepted']
    return ex, driver


@pytest.mark.parametrize('api', ['look_around', 'deliver'])
def test_p1_backoff_gate_wait_ends_within_reobserve_budget(api):
    ex, driver = gate_wait_executor(api)
    driver.run(.1)
    assert ex.job.sweep['stage'] == 'backoff' and not ex.gate.ok
    driver.run(SWEEP_REOBSERVE_S + .2, stop=lambda: ex.job is None)
    ends = [e for e in ex.events if e['event'] in ('job_failed', 'job_done')]
    assert len(ends) == 1, 'gate wait must not consume the 720 s job deadline'
    assert ends[0]['detail']['reason'] == 'SWEEP_GATE_TIMEOUT'
    assert SWEEP_REOBSERVE_S <= ends[0]['sim_s'] <= SWEEP_REOBSERVE_S + .1
    assert ends[0]['detail']['guard']['waited_s'] == pytest.approx(SWEEP_REOBSERVE_S)
    assert all(c['kind'] == 'hold' for _, raw in driver.decisions for c in json.loads(raw)['commands'])
    ex.step(720.1)
    assert len([e for e in ex.events if e['event'] == 'job_failed']) == 1


def test_p1_backoff_gate_and_later_arm_wait_share_one_budget():
    ex, _ = gate_wait_executor('look_around')
    ex.step(0.)
    ex.step(6.)
    sweep = ex.job.sweep
    # Script the end of the retreat, retaining the uncertain own pose: no physics replay.
    ex.gate = ready_gate(False)
    sweep['until'] = 6. - SETTLE_S
    ex.step(6.)
    assert sweep['stage'] == 'arm'
    ex.step(SWEEP_REOBSERVE_S)
    assert ex.job is None, 'backoff gate wait must not grant another 10 s to the arm'
    end = ex.events[-1]
    assert end['detail']['reason'] == 'SWEEP_TRANSITION_BLOCKED'
    assert end['detail']['guard']['stage'] == 'arm'
    assert end['detail']['guard']['waited_s'] == pytest.approx(SWEEP_REOBSERVE_S)


def test_p1_gate_reentry_keeps_prior_wait_but_excludes_motion_time():
    ex, _ = gate_wait_executor('look_around')
    ex.step(0.)
    ex.step(4.)
    sweep = ex.job.sweep
    sweep['until'] = 100.  # keep this fixture in backoff while the gate changes
    ex.gate = ready_gate(False)
    ex.step(4.)
    ex.step(6.)
    ex.gate.state = 'uncertain'
    ex.step(6.)
    ex.step(11.9)
    assert ex.job is not None  # 4 + 5.9 waiting seconds; the 2 motion seconds do not count
    ex.step(12.)
    assert ex.job is None
    assert ex.events[-1]['detail']['reason'] == 'SWEEP_GATE_TIMEOUT'
    assert ex.events[-1]['detail']['guard']['waited_s'] == pytest.approx(SWEEP_REOBSERVE_S)


def cargo_host():
    ex = scripted(lambda t: (1., -.85, 0., .02, .01, .1))
    host = FakeHost(team(ex), start_hold(1.))
    host._wall, host._all_box = {99}, {10, 11}
    host._own = {'r1': {1, 2}, 'r2': {3, 4}, 'r3': {5, 6}}
    host._fingers = {r: ({min(gs)}, {max(gs)}) for r, gs in host._own.items()}
    host._box_geom, host.assigned_box = {'cyan0': {10}, 'red0': {11}}, {'r1': 'cyan0'}
    host.eval_only.update(kind_steps={r: {} for r in host.robots}, contacts=[])
    ex.deliver('o1', 'A2')
    ctl = deliver_at((1., -.85, 0., .02, .01, .1), servo=CARRY_POSTURE)
    ctl.skill = types.SimpleNamespace(phase='nav_preplace', box=types.SimpleNamespace(held=True), events=[])
    ex.job.ctl, ex.servo = ctl, dict(CARRY_POSTURE)
    return host, ex, ctl


@pytest.mark.parametrize('state', ['aborted', 'goto_pending', 'goto_loaded', 'goto_ended'])
@pytest.mark.parametrize('reverse', [False, True])
def test_p2_1_cargo_wall_contact_survives_abort_and_loaded_goto(state, reverse):
    host, ex, _ = cargo_host()
    assert ex.abort('fixture')['accepted']
    assert ex.holding()['answer'] == 'unknown'
    if state != 'aborted':
        assert ex.goto([1.5, -.85])['accepted']
        if state != 'goto_pending':
            ex.step(0.)  # pending abort hold
            ex.step(.1)
            assert ex.job.driver.loaded
            if state == 'goto_ended':
                ex.cancel(.2, 'fixture')
    pair = (10, 99) if reverse else (99, 10)
    data = types.SimpleNamespace(ncon=1, contact=[types.SimpleNamespace(geom1=pair[0], geom2=pair[1])])
    before = copy.deepcopy((ex.events, ex.status(), ex.api_log))
    kinds, fingers = host._contact_kinds(data)
    host._record_contacts(.3, kinds)
    assert kinds['r1'] == {'wall', 'cargo_wall'}
    assert kinds['r2'] == kinds['r3'] == set() and not any(fingers.values())
    assert host.eval_only['kind_steps']['r1'] == {'wall': 1, 'cargo_wall': 1}
    assert (ex.events, ex.status(), ex.api_log) == before  # evaluation never feeds control or events


@pytest.mark.parametrize('held', [False, True])
def test_p2_1_released_and_unassigned_cargo_are_not_attributed(held):
    host, ex, ctl = cargo_host()
    if not held:
        ctl.skill.phase, ctl.skill.box.held = 'finished', False
        ctl.skill.events.append({'event': 'release_confirmed'})
        ex.cancel(.1, 'fixture')
        assert ex.holding()['answer'] == 'no'
    geom = 11 if held else 10
    kinds, _ = host._contact_kinds(types.SimpleNamespace(
        ncon=1, contact=[types.SimpleNamespace(geom1=99, geom2=geom)]))
    assert not any(kinds.values())


def failed_carry_leg():
    ex = scripted(lambda t: (2., -.4, 0., 0., 0., .1))
    ex.deliver('o1', 'A2')
    ctl = deliver_at((2., -.4, 0., 0., 0., .1), servo={**SEARCH_POSE, 6: 1230})
    ctl.phase = 'skill'
    ctl.skill = types.SimpleNamespace(phase='nav_preplace', box=types.SimpleNamespace(held=True), events=[])
    # Pose conversion is a fixture; M1 scheduling and the leg's full sweep guard remain real.
    ctl._estimate = lambda report: types.SimpleNamespace(source=report.source)
    ctl._start_leg((3., 0.), loaded=True)
    leg = ctl.leg
    leg._start_look(0., 'fixture', allow_backoff=False)
    ctl.last_obs = {'frame_id': 1, 'sim_time': .1}
    ex.job.ctl = ctl
    decision = ex.step(.1)
    assert decision == {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
    assert leg.outcome == 'sweep_transition_blocked' and leg.sweep_failure is not None
    assert ctl.leg is None and ex.job is None
    assert len(ctl.legs) == 1
    return ex, ctl, leg


@pytest.mark.parametrize('destination', ['archive', 'event', 'job_record'])
def test_p2_2_carry_leg_guard_survives_removal(destination):
    ex, ctl, leg = failed_carry_leg()
    if destination == 'archive':
        evidence = ctl.legs[-1].get('sweep_failure')
    elif destination == 'event':
        ends = [e for e in ex.events if e['event'] == 'job_failed']
        assert len(ends) == 1
        assert ends[0]['detail']['reason'] == 'CARRY_LEG_sweep_transition_blocked'
        evidence = ends[0]['detail'].get('guard')
    else:
        evidence = ex.jobs_done[-1].get('guard')
    assert evidence == leg.sweep_failure
    assert evidence['limiting']['clearance_mm'] < 0.
    json.dumps(evidence, allow_nan=False)
    before = copy.deepcopy(evidence)
    leg.sweep_failure['own_estimate']['x_m'] = 999.
    assert evidence == before  # archive/event are snapshots, not references to a discarded driver
