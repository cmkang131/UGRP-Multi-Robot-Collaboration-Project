"""PR #206 review 3: behavioral counterexamples, without MuJoCo physics."""
from __future__ import annotations

import importlib.util
import types

import pytest

from harness import zone_own_guards as guards
from harness.owncam_drive import CARRY_POSTURE, LOOK_P20, SEARCH_POSE, WIDE_LOOK_PANS
from harness.zone_own_deliver import _DeliverController
from harness.zone_own_driver import GuardedDriver
from harness.zone_own_executor import ZoneOwnExecutor
from tests.test_zone_own_executor import CALIB, MAP, ROOT, Driver
from tests.test_zone_own_executor_guards import ScriptedLoc, ScriptedPose, scripted, v3_like
from tests.test_zone_own_executor_host import FakeHost, OwnCamTeamHost, executor, start_hold, team, terminal


def ready_gate(loaded=True):
    gate = guards.UncertaintyGate(guards.GATE_LOADED if loaded else guards.GATE_UNLOADED)
    gate.update(0., True, .02, .01)
    gate.update(.4, True, .02, .01)
    assert gate.ok
    return gate


def driver_at(values=(1., -.85, 0., .02, .01, .1), *, static=MAP, servo=CARRY_POSTURE, goal=(1.5, -.85)):
    loc = ScriptedLoc(lambda t: values)
    d = GuardedDriver(loc, static, CALIB['params'], loaded=True, goal_xy=goal, door_xy=(2.2, .05),
                      initial_servo=servo, gate=ready_gate(), guard=guards.SweepGuard(static))
    d.state, d.state_since = 'drive', .4
    d.last_look_xy = values[:2]
    return d


@pytest.mark.parametrize('sigma', [(.20, .15), (.02, .15), (float('nan'), .01)])
def test_p1_1_entry_dwell_blocks_drive_immediately(sigma):
    d = driver_at((1., -.85, 0., *sigma, .1))
    d.gate.update(.5, True, *sigma)
    assert d.gate.ok  # Event hysteresis is deliberately still armed/ok.
    commands = d.tick(.5)
    assert not any(c['kind'] in ('drive', 'mecanum') for c in commands)


def test_p1_1_entry_dwell_blocks_arrival_after_a_fixed_look():
    d = driver_at((1., -.85, 0., .20, .15, .1), goal=(1., -.85))
    d.last_look = {'t': .4, 'fixed': True}
    d.gate.update(.5, True, .20, .15)
    d._arrive(.5)
    assert d.outcome != 'arrived'


def test_p1_1_executor_final_confirmation_uses_current_sigma():
    ex = scripted(lambda t: (1., -.85, 0., .20, .15, .1))
    ex.gate = ready_gate()
    ex.hold(1.)
    ex._finish(.5, 'own_camera_confirmed', 'fixture')
    assert ex.jobs_done[-1]['confirmation'] == 'unconfirmed'


def test_p1_1_entry_dwell_interrupts_backoff():
    d = driver_at((1., -.85, 0., .20, .15, .1))
    d._begin_backoff(.4, {'dx_base_m': -.08, 'dy_base_m': 0.}, then=('look', 'stall_recovery'))
    d.gate.update(.5, True, .20, .15)
    commands = d.tick(.5)
    assert d.gate.ok and not any(c['kind'] in ('drive', 'mecanum') for c in commands)


def deliver_at(values, *, servo=SEARCH_POSE):
    # Keep the behavioral counterexample inside a registered own-camera provider;
    # its estimate alone is scripted test data, never an allowed runtime source.
    from harness.owncam_pose_source import OwnCamPoseSource
    fixture = ScriptedPose(lambda t: values)
    pose = OwnCamPoseSource(MAP, CALIB['params'])
    pose.loc = fixture.loc
    pose.report, pose.on_frame = fixture.report, fixture.on_frame
    pose.set_motion_profile = fixture.set_motion_profile
    return _DeliverController(v3_like(MAP), CALIB['params'], box_kind='cyan', slot_id='A1', slot_xy=(3., 0.),
                              skill_factory=lambda order: None, pose_estimate_cls=tuple, search_rows_y=(),
                              shared_pose=pose, servo=servo,
                              slot_rect=((-1., 2.), (-2., 1.)), gate=ready_gate(False),
                              guard=guards.SweepGuard(v3_like(MAP)))


def test_p1_2_deliver_does_not_execute_rejected_look_transition():
    ctl = deliver_at((2., -.4, 0., 0., 0., .1), servo={**SEARCH_POSE, 6: 1230})
    plan = ctl.guard.plan(ctl.servo, LOOK_P20, WIDE_LOOK_PANS,
                          guards.OwnPose.from_report(ctl.pose.report(0.)), loaded=False)
    assert not plan['pans'] and not plan['transition_clear']
    ctl._start_sweep(0., 'look', LOOK_P20, WIDE_LOOK_PANS, SEARCH_POSE, 'fixture')
    decision = ctl.decide(.1)
    assert decision['mode'] == 'done' or not any(c['kind'] in ('arm', 'look') for c in decision['commands'])
    assert ctl.outcome == 'SWEEP_TRANSITION_BLOCKED'


def test_p1_2_executor_does_not_execute_rejected_transition_after_backoff():
    ex = scripted(lambda t: (2., -.4, 0., .01, .01, .1))
    ex.guard = guards.SweepGuard(v3_like(MAP))
    ex.gate = ready_gate(False)
    ex.servo = {**SEARCH_POSE, 6: 1230}
    ex.look_around()
    # An already completed backoff must re-check its own updated pose before moving the arm.
    ex.job.sweep = {'stage': 'backoff', 'until': 0., 'pose': LOOK_P20, 'loaded': False,
                    'guard': [], 'restore': dict(ex.servo)}
    decision = ex._tick_sweep(1., ex.job)
    assert not any(c['kind'] in ('arm', 'look') for c in decision['commands'])
    assert ex.job is None and ex.jobs_done[-1]['outcome'] == 'SWEEP_TRANSITION_BLOCKED'


@pytest.mark.parametrize('caller', ['deliver', 'executor', 'driver'])
def test_p1_2_restore_transition_is_checked(caller):
    values = (2., -.4, 0., 0., 0., .1)
    current = {**SEARCH_POSE, 6: 1230}
    target = {**LOOK_P20, 6: 1230}
    if caller == 'deliver':
        ctl = deliver_at(values, servo=current)
        ctl.sweep = {'purpose': 'look', 'pose': current, 'queue': [], 'restore': target,
                     'stage': 'restore', 'since': 0., 'settled': False}
        commands = ctl._tick_sweep(1.)
        outcome = ctl.outcome
    elif caller == 'executor':
        ex = scripted(lambda t: values)
        ex.guard, ex.servo = guards.SweepGuard(v3_like(MAP)), current
        ex.look_around()
        ex.job.sweep = {'stage': 'restore', 'restore': target, 'loaded': False, 'since': 0.}
        commands = ex._tick_sweep(1., ex.job)['commands']
        outcome = ex.jobs_done[-1]['outcome'] if ex.jobs_done else None
    else:
        ctl = driver_at(values, static=v3_like(MAP), servo=current)
        ctl.loaded, ctl.state, ctl.arm_target = False, 'posture_back', target
        commands = ctl.tick(1.)
        outcome = ctl.outcome
    assert not any(c['kind'] in ('arm', 'look') for c in commands)
    assert outcome is not None and 'transition_blocked' in outcome.lower()


def test_p1_3_stall_backoff_checks_loaded_arm_at_max_gain():
    d = driver_at((1.90, -.50, 0., 0., 0., .1), static=v3_like(MAP), goal=(1., -.5))
    pose = guards.OwnPose.from_estimate(d.loc.estimate())
    assert d.guard.chassis_clearance(pose.moved(.08 * 1.6, 0.))[0] > 0.
    assert d.guard.arm_clearance(d.servo, pose.moved(.08 * 1.6, 0.), loaded=True)[0] < 0.
    d.recoveries = 1
    d._start_recovery(1., pose)
    assert d.backoff is None


def test_p1_3_look_backoff_checks_current_arm_not_just_target_pose():
    guard = guards.SweepGuard(v3_like(MAP))
    pose = guards.OwnPose(2., -.4, 0., .01, .01)
    move = guard.backoff(CARRY_POSTURE, LOOK_P20, WIDE_LOOK_PANS, pose, loaded=True, have=0)
    if move is not None:
        for gain in [i * 1.6 / 40 for i in range(41)]:
            at = pose.moved(move['dx_base_m'] * gain, move['dy_base_m'] * gain)
            assert guard.arm_clearance(CARRY_POSTURE, at, loaded=True)[0] >= 0.


def test_p1_3_backoff_checks_between_clear_endpoints():
    guard = guards.SweepGuard({})
    pose = guards.OwnPose(0., 0., 0., 0., 0.)
    # Both ends clear: a narrow static wall crosses the carried arm mid-trajectory.
    guard.arm_clearance = lambda servo, p, loaded: (abs(p.x - .064) - .012, 'thin_wall')
    guard.chassis_clearance = lambda p: (1., None)
    assert not guard.translation_clear(CARRY_POSTURE, pose, .08, 0., loaded=True)


def test_p1_3_backoff_refuses_an_initial_chassis_margin_overlap():
    guard = guards.SweepGuard(v3_like(MAP))
    pose = guards.OwnPose(2.08, .18, 0., .01, .01)
    assert guard.chassis_clearance(pose)[0] < 0.
    assert guard.backoff(SEARCH_POSE, LOOK_P20, WIDE_LOOK_PANS, pose, loaded=False, have=0) is None


def test_p1_4_inconclusive_progress_looks_end_before_job_timeout():
    ex = scripted(lambda t: (1., -.85, 0., .02 if t < 1. else .065, .01, .1 if t < 1. else 30.),
                  job_sim_limit_s=250.)
    ex._holding_after = {'answer': 'unknown'}
    d = Driver(ex)
    ex.goto([1.6, -.85])
    d.run(251., stop=lambda: ex.job is None)
    failed = [e for e in ex.events if e['event'] == 'job_failed']
    assert len(failed) == 1 and failed[0]['detail']['reason'] == 'GOTO_progress_unconfirmed'
    assert failed[0]['sim_s'] < 150.


def test_p1_4_missing_estimate_and_monitor_reset_do_not_erase_failure_budget():
    d = driver_at()
    d.look_reason = 'progress_check'
    d.loc.estimate = lambda: {'initialized': False, 't': 1.}
    for _ in range(3):
        d._event(1., 'look_done', fixed=False)
        d.monitor.reset()
    commands = d.tick(1.)
    assert d.outcome == 'progress_unconfirmed' and commands == [{'kind': 'hold'}]


class LongWaitExecutor(ZoneOwnExecutor):
    def _step_hold(self, now, job):
        return {'mode': 'macro', 'action': {'kind': 'wait', 'duration': 5.}}


@pytest.mark.parametrize('limit', [0., .2, 1., 1.03])
def test_p2_1_long_wait_and_settle_never_exceed_horizon(limit):
    host = FakeHost({r: executor(LongWaitExecutor, rid=r) for r in ('r1', 'r2', 'r3')}, start_hold(20.))
    targets = []
    advance = host._physics_until
    def track(end):
        targets.append(end)
        advance(end)
    host._physics_until = track
    result = host.run(limit)
    assert result['outcome'] == 'SIM_LIMIT'
    assert result['sim_s'] <= limit + 1e-9
    assert max(targets) <= limit + 1e-9
    for rid in host.robots:
        assert len(terminal(host, rid)) == 1
        assert not host.robots[rid].timeline


def smoke_module():
    path = ROOT / 'experiments/2026-09-26-zone-own-executor/run_smoke_v2.py'
    spec = importlib.util.spec_from_file_location('smoke_review3', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p2_2_export_counts_recoveries_without_keepouts(monkeypatch):
    from harness import m1_contract, m1_owncam_contract
    monkeypatch.setattr(m1_owncam_contract, 'judge', lambda **kw: {'m1_success': False, 'diagnostic_success': False, 'counts_as_m1': False})
    monkeypatch.setattr(m1_contract, 'outcome_fields', lambda **kw: {'m1_success': False, 'counts_as_m1': False})
    monkeypatch.setattr(m1_owncam_contract, 'assert_exportable', lambda r: None)
    monkeypatch.setattr(m1_contract, 'validate_outcome', lambda r: None)
    ex = scripted(lambda t: (1., -.85, 0., .02, .01, .1))
    ex._summaries = [{'controller': {}, 'legs': [{'recoveries': 2, 'stall_keepouts': []}]},
                     {'driver_log': [{'event': 'stall_recovery'}], 'stall_keepouts': []}]
    slot = types.SimpleNamespace(executor=ex, exception=None, frames=[], commands=[], cancellations=[])
    host = types.SimpleNamespace(world=types.SimpleNamespace(data=None), objects={}, static=MAP,
                                 eval_only={'kind_steps': {'r1': {}}, 'max_eq_active': 0,
                                            'retention': {'r1': {'carry_steps': 0, 'both_finger_steps': 0, 'low_box_steps': 0}}})
    result = smoke_module().robot_result('r1', slot, host, {}, {'r1': {'order_id': 'o1', 'zone_slot': 'A1'}},
                                        {'r1': 'cyan0'}, {'orders': [{'order_id': 'o1'}]}, {'input_contract': 'fixture'})
    assert result['guards']['stall_recoveries'] == 3


@pytest.mark.parametrize('phase, expected', [('nav_preplace', {'wall', 'cargo_wall'}), ('done', set())])
def test_p2_3_cargo_wall_contacts_are_evaluation_only(phase, expected):
    host = FakeHost(team(executor()), start_hold(1.))
    host._wall, host._all_box = {99}, {10}
    host._own = {'r1': {1, 2}, 'r2': {3, 4}, 'r3': {5, 6}}
    host._fingers = {r: ({min(gs)}, {max(gs)}) for r, gs in host._own.items()}
    host._box_geom, host.assigned_box = {'cyan0': {10}}, {'r1': 'cyan0'}
    ex = host.robots['r1'].executor
    ex.hold(1.)
    ex.job.ctl = types.SimpleNamespace(skill=types.SimpleNamespace(
        phase=phase, box=types.SimpleNamespace(held=phase == 'nav_preplace')))
    before = list(ex.events)
    kinds, fingers = host._contact_kinds(types.SimpleNamespace(ncon=1, contact=[types.SimpleNamespace(geom1=99, geom2=10)]))
    assert kinds['r1'] == expected
    assert kinds['r2'] == kinds['r3'] == set() and not any(fingers.values())
    assert ex.events == before
