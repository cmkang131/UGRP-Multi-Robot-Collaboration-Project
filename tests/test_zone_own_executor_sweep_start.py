"""PR #206 startup regression: same s703 scene setup, no MuJoCo world/physics.

Spawn positions are fixture inputs to a diagnostic own-pose source, never injected into the
production estimator. Sigma traces are controlled counterexamples, not claimed s703 logs.
"""
from __future__ import annotations

import json

import pytest

from harness import zone_own_guards as guards
from harness.owncam_drive import LOOK_P20, SEARCH_POSE, WIDE_LOOK_PANS
from harness.zone_own_sweep import SWEEP_REOBSERVE_S, SweepRecheck
from tests.test_zone_own_executor import MAP, ROOT, Driver
from tests.test_zone_own_executor_guards import scripted, v3_like
from tests.test_zone_own_executor_host import FakeHost, terminal
from tests.test_zone_own_executor_review3 import deliver_at, driver_at


@pytest.fixture(scope='module')
def startup():
    # Exactly the setup used by test_team_host_isolation_abort_and_horizon_on_the_real_world.
    from sim.zone_cargo_contact import base_profile
    from sim.zone_landmarks import TaggedZoneScene
    scene = TaggedZoneScene.from_tagged('zone_wide_door_tags_v2', 703,
                                      {'A': {'cyan': 1}, 'B': {'cyan': 1}, 'C': {'cyan': 1}},
                                      {'red': 2, 'green': 1}, contact_profile=base_profile('cargo_noslip_v1'))
    assert scene.config['static_map'] == MAP
    return scene.config['setup_only']['spawns']


@pytest.mark.parametrize('rid', ['r1', 'r2', 'r3'])
def test_same_world_spawn_has_clear_nominal_sweep_but_uncertainty_can_block_all_pans(startup, rid):
    x, y, _, yaw = startup[rid]
    guard = guards.SweepGuard(MAP)
    nominal = guards.OwnPose(x, y, yaw, 0., 0.)
    inflated = guards.OwnPose(x, y, yaw, .05, .02)
    assert x == -.85 and SEARCH_POSE == {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
    assert guard.plan(SEARCH_POSE, LOOK_P20, WIDE_LOOK_PANS, nominal, loaded=False)['pans'] == list(WIDE_LOOK_PANS)
    rejected = guard.plan(SEARCH_POSE, LOOK_P20, WIDE_LOOK_PANS, inflated, loaded=False)
    assert not rejected['transition_clear'] and not rejected['pans'] and rejected['backoff'] is None
    evidence = guard.transition_diagnostic(SEARCH_POSE, LOOK_P20, inflated, loaded=False)
    limiting = evidence['limiting']
    assert limiting['wall_id'] == 'wall_west'
    assert limiting['raw_clearance_mm'] > 100. and limiting['clearance_mm'] < 0.
    assert limiting['margin_mm'] == pytest.approx(1000 * guard.margin(inflated, abs(limiting['sphere_center_base_m'][0])))
    # The invariant bearing alone blocks every pan at this uncertainty (130 - 135 = -5 mm).
    assert guard.arm_clearance({**SEARCH_POSE, **LOOK_P20}, inflated, loaded=False)[0] == pytest.approx(-.005)


def start_looks(host, kind, event, now):
    if kind == 'start':
        for rid in host.robots:
            host.call(rid, 'look_around')


def spawn_executor(startup, rid, *, converges=True):
    x, y, _, yaw = startup[rid]
    return scripted(lambda t: (x, y, yaw, .01 if converges and t >= 6. else .15, .02, .1), rid=rid)


def test_startup_hold_preserves_real_host_abort_and_horizon_semantics(startup):
    exs = {rid: spawn_executor(startup, rid) for rid in startup}
    host = FakeHost(exs, start_looks, hooks=[(1.5, lambda h: h.call('r1', 'abort', 'test'))])
    out = host.run(3.)
    assert out['outcome'] == 'SIM_LIMIT'
    assert terminal(host, 'r1')[0]['detail']['reason'] == 'ABORTED:test'
    for rid in ('r2', 'r3'):
        assert len(terminal(host, rid)) == 1
        assert terminal(host, rid)[0]['detail']['reason'] == 'EPISODE_END:SIM_LIMIT'
    assert all(kind == 'hold' for slot in host.robots.values() for _, kind, _ in slot.port.log)


def test_startup_reobserves_then_completes_a_sweep_after_refinement(startup):
    host = FakeHost({rid: spawn_executor(startup, rid) for rid in startup}, start_looks)
    host.run(30.)
    for rid, slot in host.robots.items():
        ends = terminal(host, rid)
        assert len(ends) == 1 and ends[0]['event'] == 'job_done', ends
        assert ends[0]['detail']['outcome'] == 'LOOKED'
        commands = [(t, kind, cmd) for t, kind, cmd in slot.port.log if kind != 'hold']
        assert commands and min(t for t, _, _ in commands) >= 6.
        assert all(kind in ('arm', 'look') for _, kind, _ in commands)  # base never moves
        assert set(WIDE_LOOK_PANS) <= {cmd['pan_pulse'] for _, kind, cmd in commands if kind == 'look'}
        current = dict(SEARCH_POSE)
        x, y, _, yaw = startup[rid]
        own = guards.OwnPose(x, y, yaw, .01, .02)
        # Check each actually issued tick as well as the end result, including restore.
        for t in sorted({t for t, _, _ in commands}):
            target = dict(current)
            for at, kind, cmd in commands:
                if at == t:
                    target[6 if kind == 'look' else cmd['servo_id']] = cmd.get('pan_pulse', cmd.get('pulse'))
            assert slot.executor.guard.transition_clear(current, target, own, loaded=False)
            current = target
        assert current == SEARCH_POSE


def test_startup_without_refinement_is_bounded_and_reports_own_guard_evidence(startup):
    ex = spawn_executor(startup, 'r2', converges=False)
    d = Driver(ex)
    ex.look_around()
    d.run(SWEEP_REOBSERVE_S + 2., stop=lambda: ex.job is None)
    end = [e for e in ex.events if e['event'] == 'job_failed']
    assert len(end) == 1 and end[0]['detail']['reason'] == 'SWEEP_TRANSITION_BLOCKED'
    assert SWEEP_REOBSERVE_S <= end[0]['sim_s'] <= SWEEP_REOBSERVE_S + .2
    assert all(c['kind'] == 'hold' for _, raw in d.decisions for c in json.loads(raw)['commands'])
    evidence = end[0]['detail']['guard']
    assert evidence['own_estimate'] == dict(x_m=-.85, y_m=-.85, yaw_rad=0., std_xy_m=.15, std_yaw_rad=.02)
    assert evidence['current_pwm'] == SEARCH_POSE
    assert evidence['target_pwm'] == {**SEARCH_POSE, **LOOK_P20}
    hit = evidence['limiting']
    assert hit['wall_id'] == 'wall_west' and hit['sphere_part'] in ('upper_arm', 'yaw_bearing')
    assert hit['overlap_mm'] == -hit['clearance_mm'] > 0.
    json.dumps(evidence, allow_nan=False)


@pytest.mark.parametrize('rid, jump_at', [('r2', 1.4), ('r3', 2.7)])
def test_initial_estimate_refinement_can_interrupt_and_resume_an_inflight_sweep(startup, rid, jump_at):
    x, y, _, yaw = startup[rid]
    ex = scripted(lambda t: (x, y, yaw, .15 if jump_at <= t < 6. else .01, .02, .1), rid=rid)
    d = Driver(ex)
    ex.look_around()
    d.run(30., stop=lambda: ex.job is None)
    assert ex.jobs_done[-1]['outcome'] == 'LOOKED'
    for t, raw in d.decisions:
        if jump_at <= t < 6.:
            assert all(c['kind'] == 'hold' for c in json.loads(raw)['commands'])


@pytest.mark.parametrize('caller', ['deliver', 'driver'])
def test_other_sweep_callers_wait_for_refinement_and_restore_all_safe_pans(startup, caller):
    x, y, _, yaw = startup['r2']
    values = (x, y, yaw, .15, .02, .1)
    if caller == 'deliver':
        from tests.test_zone_own_executor_guards import ScriptedPose
        ctl = deliver_at(values)
        ctl.guard = guards.SweepGuard(MAP)
        ctl._start_sweep(0., 'look', LOOK_P20, WIDE_LOOK_PANS, SEARCH_POSE, 'fixture')
        assert ctl._tick_sweep(0.) == [{'kind': 'hold'}] and ctl.outcome is None
        ctl.pose = ScriptedPose(lambda t: (x, y, yaw, .01, .02, .1))
        commands = ctl._tick_sweep(6.)
        assert ctl.sweep['queue'] == list(WIDE_LOOK_PANS)
    else:
        ctl = driver_at(values, servo=SEARCH_POSE)
        ctl.loaded = False
        ctl._start_look(0., 'fixture', allow_backoff=False)
        assert ctl._arm_step() == [{'kind': 'hold'}] and ctl.outcome is None
        ctl.loc.fn = lambda t: (x, y, yaw, .01, .02, .1)
        ctl.loc.predict_to(6.)
        commands = ctl._arm_step()
        assert ctl.look_queue == list(WIDE_LOOK_PANS)
    assert any(c['kind'] == 'arm' for c in commands) and ctl.outcome is None


def test_goto_terminal_event_carries_driver_failure_input(startup):
    ex = spawn_executor(startup, 'r2', converges=False)
    d = Driver(ex)
    ex.goto([0., -.85])
    d.run(SWEEP_REOBSERVE_S + 2., stop=lambda: ex.job is None)
    event = [e for e in ex.events if e['event'] == 'job_failed'][-1]
    assert event['detail']['reason'] == 'GOTO_sweep_transition_blocked'
    assert event['detail']['guard']['own_estimate']['x_m'] == -.85
    assert event['detail']['guard']['limiting']['wall_id'] == 'wall_west'


@pytest.mark.parametrize('caller', ['deliver', 'driver', 'executor'])
def test_stale_pan_queue_selects_a_reachable_pan_and_preserves_restore_guard(caller):
    values = (2.08, .14, 0., .01, .01, .1)
    current = {**SEARCH_POSE, **LOOK_P20}
    guard, pose = guards.SweepGuard(v3_like(MAP)), guards.OwnPose(*values[:5])
    assert not guard.transition_clear(current, {6: 2030}, pose, loaded=False)
    assert guard.transition_clear(current, {6: 1230}, pose, loaded=False)
    if caller == 'deliver':
        ctl = deliver_at(values, servo=current)
        ctl.sweep = {'stage': 'pan', 'target': 2030, 'queue': [1230, 1500], 'since': 0.,
                     'settled': False, 'restore': SEARCH_POSE}
        commands = ctl._tick_sweep(1.)
        target = ctl.sweep['target']
        assert ctl.outcome is None
    elif caller == 'driver':
        ctl = driver_at(values, static=v3_like(MAP), servo=current)
        ctl.loaded, ctl.state, ctl.arm_target, ctl.look_queue = False, 'look_pan', {6: 2030}, [1230, 1500]
        commands = ctl._arm_step()
        target = ctl.arm_target[6]
        assert ctl.outcome is None
    else:
        ctl = scripted(lambda t: values)
        ctl.servo, ctl.guard = dict(current), guard
        ctl.look_around()
        ctl.job.sweep = {'stage': 'pan', 'target': 2030, 'queue': [1230, 1500], 'since': 0.,
                         'loaded': False, 'restore': SEARCH_POSE}
        commands = ctl._tick_sweep(1., ctl.job)['commands']
        target = ctl.job.sweep['target']
        assert not ctl.jobs_done
    assert target == 1230
    assert [c for c in commands if c['kind'] != 'hold'] == [{'kind': 'look', 'pan_pulse': 1440}]


def test_retry_budget_is_not_reset_by_safe_ticks_or_changed_targets():
    guard, retry = guards.SweepGuard(MAP), SweepRecheck()
    pose = guards.OwnPose(-.85, -.85, 0., .15, .02)
    safe = guards.OwnPose(-.85, -.85, 0., .01, .02)
    assert retry.check(0., guard, SEARCH_POSE, LOOK_P20, pose, loaded=False) == 'wait'
    assert retry.check(6., guard, SEARCH_POSE, LOOK_P20, safe, loaded=False) == 'clear'
    assert retry.check(7., guard, SEARCH_POSE, {6: 1230}, pose, loaded=False) == 'wait'
    assert retry.check(11., guard, SEARCH_POSE, {6: 1500}, pose, loaded=False) == 'blocked'


def test_tall_wall_222_step_calibration_region_remains_rejected():
    record = json.loads((ROOT / 'experiments/2026-09-26-zone-own-executor/body_model_calibration.json').read_text())
    case = next(r for r in record['sweep_validation_0p40_walls']
                if r['pose_xy_m'] == [2.08, .18] and r['policy'] == 'full_sweep_v1')
    assert case['contact_steps'] == 222
    guard = guards.SweepGuard(v3_like(MAP))
    pose = guards.OwnPose(2.08, .18, 0., .01, .01)
    for pan in case['contact_pans']:
        assert not guard.transition_clear({**SEARCH_POSE, **LOOK_P20}, {6: pan}, pose, loaded=False)


def test_low_uncertainty_true_geometry_failure_has_detailed_terminal_event():
    ex = scripted(lambda t: (2., -.4, 0., 0., 0., .1))
    ex.servo, ex.guard = {**SEARCH_POSE, 6: 1230}, guards.SweepGuard(v3_like(MAP))
    ex.look_around()
    ex._tick_sweep(0., ex.job)
    event = [e for e in ex.events if e['event'] == 'job_failed'][-1]
    assert event['sim_s'] == 0. and event['detail']['guard']['waited_s'] == 0.
    assert event['detail']['guard']['limiting']['clearance_mm'] < 0.
