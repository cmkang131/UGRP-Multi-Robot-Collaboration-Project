"""v98 dock look pans + bounded look recovery (zone_pair_highpose_relook).

Fast tests drive the real v98 ``OwnExecutor`` (scripted own estimate, no simulator). The two closed-loop tests
drive the real v98 ``Runtime`` with synthetic own observations (``tests/highpose_relook_synthetic.py``): measured
camera models, real PF/provider/admission/team; only the wall detector is replaced by expected rows at an
assumed true dock pose plus calibration-split residuals.
"""
from __future__ import annotations

import json
import math
import types

import numpy as np
import pytest

from harness import zone_own_guards as guards
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_lookaround as look
from harness import zone_pair_highpose_relook as relook
from harness import zone_pair_highpose_runtime as rt
from harness.owncam_drive import LOOK_P20, WIDE_LOOK_PANS
from harness.owncam_pose_source import PoseReport
from harness.zone_final_pair_guards import PairArmGuard
from harness.zone_own_executor import ZoneOwnExecutor
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint
from tests.test_zone_final_pair_v3 import MAPS
from tests.test_zone_own_executor import Driver
from tests.test_zone_own_executor_guards import scripted

STATIC = c.resolve(MAPS[0])[0]
REFUSED = {'accepted': False, 'rejected_reason': 'SELF_UNCERTAIN'}


class StuckPose:
    """Own estimate that never becomes admissible: r2 at the dock, sigma_x 30 mm, sigma_y 70 mm (std_xy 76 mm:
    gate uncertain, every dock pan clear)."""
    source = 'diagnostic_scripted_estimate'

    def __init__(self, x=-.9, y=-.85, sx=.03, sy=.07):
        self.x, self.y, self.sx, self.sy = x, y, sx, sy

    def on_command(self, row):
        pass

    def on_frame(self, now, rgb):
        return self.report(now)

    def set_motion_profile(self, t, name):
        pass

    def report(self, now):
        cov = ((self.sx**2, 0., 0.), (0., self.sy**2, 0.), (0., 0., 1e-4))
        return PoseReport(now, True, self.x, self.y, 0., cov, math.hypot(self.sx, self.sy), .01, .1,
                          source=self.source, last_fix_t=now - .1, fix_age_s=.1)


def executor(rid='r2', pose=None):
    ex = scripted(lambda t: (0., 0., 0., 0., 0., .1), rid=rid)
    ex.pose = pose or StuckPose()
    ex.guard = PairArmGuard(STATIC)
    rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={rid: ex}))
    return ex


def runtime_of(ex, sessions=()):
    return types.SimpleNamespace(actors={ex.robot_id: ex}, team=types.SimpleNamespace(sessions=list(sessions)))


def drive(ex, runtime, recovery, until_s, *, refusal=REFUSED, inject=None):
    """Opening look, then the v98 loop: pre_step, a refusal while idle, own step, base-command filter."""
    d = Driver(ex)
    ex.look_around()
    rid, issued_all = ex.robot_id, []
    while d.t < until_s - 1e-9:
        if round(d.t * 10) % 2 == 0:
            d.frame()
        recovery.pre_step(runtime, d.t)
        if ex.job is None and not recovery.exhausted(rid):
            recovery.on_refusal(runtime, rid, dict(refusal), d.t)
        decision = ex.step(d.t)
        rows = [(rid, cmd) for cmd in decision['commands']]
        if inject is not None:
            rows += inject(d.t, recovery)
        for _, cmd in recovery.filter(runtime, d.t, rows):
            if cmd['kind'] == 'arm':
                d.servo[cmd['servo_id']] = cmd['pulse']
            elif cmd['kind'] == 'look':
                d.servo[6] = cmd['pan_pulse']
            issued_all.append((round(d.t, 2), cmd))
            ex.on_command({'t': round(d.t, 4), **cmd})
        d.t = round(d.t + .1, 4)
    recovery.pre_step(runtime, d.t)
    return issued_all


def looks(ex):
    return [j for j in ex.jobs_done if j['kind'] == 'look_around']


# ------------------------------------------------------------------ dock look pans
def test_dock_look_visits_the_two_extra_pans_and_other_sweeps_keep_the_wide_pans():
    ex = executor('r1', StuckPose(y=.55, sx=.01, sy=.01))
    d = Driver(ex)
    ex.look_around()
    d.run(20., stop=lambda: ex.job is None)
    pans = [json.loads(raw)['commands'] for _, raw in d.decisions]
    reached = {c['pan_pulse'] for cmds in pans for c in cmds if c['kind'] == 'look'}
    assert {700, 2300} <= reached and min(reached) == 700 and max(reached) == 2300
    # Any other job kind (the delivery sweep) plans over WIDE_LOOK_PANS: spy on the guard's pan list.
    seen = []
    plan = ex.guard.plan
    ex.guard.plan = lambda cur, pose, pans, *a, **k: seen.append(tuple(pans)) or plan(cur, pose, pans, *a, **k)
    for kind in ('deliver', 'look_around'):
        job = types.SimpleNamespace(kind=kind, sweep=None, phase=None, ctl=None)
        ex.job = job
        rt.OwnExecutor._tick_sweep(ex, d.t, job)
    ex.job = None
    assert seen == [tuple(WIDE_LOOK_PANS), relook.DOCK_LOOK_PANS]
    assert rt.OwnExecutor._tick_sweep.v98_dock_pans == relook.DOCK_LOOK_PANS
    assert not hasattr(ZoneOwnExecutor._tick_sweep, 'v98_dock_pans')         # shared class untouched


@pytest.mark.parametrize('row_y', [-2.25, -.85, .55])
def test_guard_clears_every_dock_pan_at_every_dock_row(row_y):
    """Offline guard numbers of the r2 note: 700-2300 allowed to sigma 0.08 m (round) and 0.10 m (r2 ellipse)."""
    guard = look.LookAroundGuard(STATIC)
    pose_servo = {1: 2000, **LOOK_P20, 6: 1500}
    for std in (.03, .05, .065, .08):
        plan = guard.plan(pose_servo, pose_servo, list(relook.DOCK_LOOK_PANS), guards.OwnPose(-.8982, row_y, 0., std, math.radians(1.)),
                          loaded=False)
        assert plan['dropped'] == [] and plan['interval'] == (700, 2300), (std, plan)
    vx, vy = 32.**2, 56.**2
    scale = .1**2/(vx + vy)
    pose = guards.OwnPose(-.8982, row_y, 0., .1, math.radians(1.))
    guard.hint = (pose.x, pose.y, pose.yaw, pose.std_xy, pose.std_yaw, (vx*scale, 0., vy*scale))
    assert guard.plan(pose_servo, pose_servo, list(relook.DOCK_LOOK_PANS), pose, loaded=False)['dropped'] == []
    guard.hint = None
    blocked = guard.plan(pose_servo, pose_servo, list(relook.DOCK_LOOK_PANS), pose, loaded=False)
    assert blocked['interval'] is None                     # round 0.10 m: the guard already blocks every pan


def test_pans_only_guard_never_proposes_a_back_off():
    guard = look.LookAroundGuard(STATIC)
    servo = {1: 2000, **LOOK_P20, 6: 1500}
    pose = guards.OwnPose(-.87, -.85, math.radians(90.), .02, .01)      # facing north next to the west wall
    free = guard.plan(servo, servo, list(relook.DOCK_LOOK_PANS), pose, loaded=False, allow_backoff=True)
    assert free['backoff'] is not None and free['dropped']
    guard.pans_only = True
    held = guard.plan(servo, servo, list(relook.DOCK_LOOK_PANS), pose, loaded=False, allow_backoff=True)
    assert held['backoff'] is None and held['pans'] == free['pans'] and held['dropped'] == free['dropped']
    assert look.LookAroundGuard.pans_only is False                      # class default unchanged


# ------------------------------------------------------------------ look recovery
def test_two_relooks_then_exhausted_with_sigma_logged():
    ex = executor()
    runtime = runtime_of(ex)
    recovery = relook.LookRecovery(('r2',))
    drive(ex, runtime, recovery, 60.)
    st = recovery.state['r2']
    assert len(looks(ex)) == 3                                         # opening look + 2 re-looks, never a third
    assert [a['attempt'] for a in st['attempts']] == [1, 2]
    previous_end = looks(ex)[0]['ended_at_sim_s']
    for a, job in zip(st['attempts'], looks(ex)[1:]):
        assert a['job_id'] == job['job_id'] and a['outcome'] == job['outcome'] == 'LOOKED_POSE_UNCERTAIN'
        assert a['t_start'] >= previous_end + relook.RELOOK_GRACE_S - 1e-9
        for key in ('sigma_before', 'sigma_after'):
            assert a[key]['std_xy_m'] == pytest.approx(math.hypot(.03, .07), abs=1e-4)
            assert a[key]['sigma_y_m'] == pytest.approx(.07, abs=1e-4) and a[key]['gate'] == 'uncertain'
        assert a['trigger'] == 'SELF_UNCERTAIN' and a['pans'] == list(relook.DOCK_LOOK_PANS)
        assert job['ended_at_sim_s'] - job['started_at_sim_s'] > 9.          # a full eight-pan look each time
        previous_end = job['ended_at_sim_s']
    assert st['exhausted']['code'] == relook.EXHAUSTED and st['exhausted']['attempts'] == 2
    assert st['exhausted']['sim_s'] >= previous_end + relook.RELOOK_GRACE_S - 1e-9
    assert recovery.failures() == {'r2': relook.EXHAUSTED}
    assert ex.guard.pans_only is False


def test_install_stops_submitting_after_exhaustion():
    ex = executor()
    calls = []

    def inner(rid, item_ref=None, target_zone=None, partner_id=None, *, now):
        calls.append(now)
        return dict(REFUSED)

    runtime = types.SimpleNamespace(actors={'r2': ex}, team=types.SimpleNamespace(sessions=[], start=inner))
    recovery = relook.install(runtime, relook.LookRecovery(('r2',), max_relooks=0))
    d = Driver(ex)
    ex.look_around()
    d.run(20., stop=lambda: ex.job is None)
    t = d.t + relook.RELOOK_GRACE_S
    first = runtime.team.start('r2', 'cargoX', 'B', 'r1', now=t)
    assert first['rejected_reason'] == 'SELF_UNCERTAIN' and recovery.exhausted('r2') and len(calls) == 1
    again = runtime.team.start('r2', 'cargoX', 'B', 'r1', now=t + .05)
    assert again == {'robot_id': 'r2', 'api': 'pair_carry', 'accepted': False, 'rejected_reason': relook.EXHAUSTED}
    assert len(calls) == 1 and ex.job is None and len(looks(ex)) == 1


@pytest.mark.parametrize('refusal', ['SELF_INVALID_IMAGE', 'SELF_BUSY', 'PAIR_SUBMISSION_MISMATCH'])
def test_other_refusals_never_relook(refusal):
    ex = executor()
    recovery = relook.LookRecovery(('r2',))
    drive(ex, runtime_of(ex), recovery, 25., refusal={'accepted': False, 'rejected_reason': refusal})
    assert len(looks(ex)) == 1 and recovery.state['r2']['attempts'] == [] and not recovery.exhausted('r2')


def test_no_relook_while_loaded():
    ex = executor()
    ex.holding = lambda: {'answer': 'yes', 'source': 'test'}
    recovery = relook.LookRecovery(('r2',))
    drive(ex, runtime_of(ex), recovery, 25.)
    st = recovery.state['r2']
    assert len(looks(ex)) == 1 and st['attempts'] == [] and st['exhausted'] is None
    assert [s['reason'] for s in st['skipped']] == ['not_empty_handed']


def _pending_session(partner_state, now):
    channel = PairStatusChannel('pair-test', heartbeat_timeout_s=.15)
    ep = PairStatusEndpoint(channel, 'r1')
    ep.tick(partner_state, now)
    return {'closed': False, 'endpoints': {'r1': object()}, 'channel': channel}, ep


def test_relook_waits_while_the_partner_wire_phase_is_moving():
    ex = executor()
    session, partner = _pending_session('aligning', 0.)
    runtime = runtime_of(ex, [session])
    recovery = relook.LookRecovery(('r2',))
    assert relook.partner_phase(runtime.team, 'r2', 0.) == 'aligning'
    drive(ex, runtime, recovery, 20.)
    st = recovery.state['r2']
    assert len(looks(ex)) == 1 and st['attempts'] == []
    assert st['skipped'][-1] == {'sim_s': st['skipped'][-1]['sim_s'], 'reason': 'partner_in_motion_phase',
                                 'partner_phase': 'aligning'}
    partner.tick('start_ready', 20.)                               # the partner is admitted and waits
    assert relook.partner_phase(runtime.team, 'r2', 20.) == 'start_ready'
    assert recovery.on_refusal(runtime, 'r2', dict(REFUSED), 20.) is True
    assert st['active']['partner_phase'] == 'start_ready' and ex.job.kind == 'look_around'


def test_a_relook_issues_no_base_motion_and_a_base_command_fails_it():
    ex = executor()
    recovery = relook.LookRecovery(('r2',), max_relooks=1)
    issued = drive(ex, runtime_of(ex), recovery, 40.)
    start = recovery.state['r2']['attempts'][0]['t_start']
    assert [c for t, c in issued if t >= start and c['kind'] not in relook.RELOOK_COMMANDS] == []
    assert any(c['kind'] == 'look' for t, c in issued if t >= start)

    ex = executor()
    recovery = relook.LookRecovery(('r2',), max_relooks=1)
    bad = {'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': .2}

    def inject(t, rec):
        return [('r2', dict(bad))] if rec.state['r2']['active'] is not None else []

    issued = drive(ex, runtime_of(ex), recovery, 40., inject=inject)
    assert [c for _, c in issued if c['kind'] == 'mecanum'] == []
    attempt = recovery.state['r2']['attempts'][0]
    assert attempt['outcome'] == relook.BASE_MOTION and attempt['refused_command'] == bad
    assert looks(ex)[-1]['outcome'] == relook.BASE_MOTION and ex.guard.pans_only is False


def test_record_and_adoption():
    ex = executor()
    record = rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={}))
    assert record['dock_look'] == relook.record()
    assert record['dock_look']['relook_status_on_wire'] is False
    assert relook.RENDEZVOUS_TIMEOUT_S <= 30. and relook.RENDEZVOUS_TIMEOUT_S >= (
        5. + 3*relook.RELOOK_GRACE_S + 2*relook.LOOK_S)
    with pytest.raises(ValueError):
        relook.LookRecovery(('r2',), max_relooks=-1)
    assert type(ex) is rt.OwnExecutor and type(ex.guard) is look.LookAroundGuard


# ------------------------------------------------------------------ synthetic closed loop (real runtime + PF)
@pytest.fixture(scope='module')
def closed_loop(tmp_path_factory):
    from tests import highpose_relook_synthetic as hs
    mp = pytest.MonkeyPatch()
    try:
        cal = hs.admitted_copy(tmp_path_factory.mktemp('relook'), mp)
        dock = hs.build(cal, seed=0)
        dock_run = hs.run(dock, until_s=20., stop=hs.admitted)
        # Mutation: the five WIDE_LOOK_PANS (the pre-change dock look); recovery on.
        mp.setattr(rt.OwnExecutor, '_tick_sweep', relook.dock_sweep(ZoneOwnExecutor._tick_sweep, ZoneOwnExecutor._sweep_steps,
                                                                     WIDE_LOOK_PANS)[0])
        mp.setattr(rt.OwnExecutor, '_sweep_steps', relook.dock_sweep(ZoneOwnExecutor._tick_sweep, ZoneOwnExecutor._sweep_steps,
                                                                      WIDE_LOOK_PANS)[1])
        five = hs.build(cal, seed=0)
        five_run = hs.run(five, until_s=40., stop=hs.admitted)
    finally:
        mp.undo()
    return hs, (dock, dock_run), (five, five_run)


def _first_refusal_after_look(runtime, rid):
    own = runtime.actors[rid]
    end = own.jobs_done[0]['ended_at_sim_s']
    return [a for a in own.api_log if a['api'] == 'pair_carry' and not a['accepted'] and a['sim_s'] >= end - 1e-9]


def test_closed_loop_r2_is_admitted_after_the_extended_dock_look(closed_loop):
    hs, (dock, run), _ = closed_loop
    assert set(dock.submitted) == {'r1', 'r2'}
    for rid in ('r1', 'r2'):
        own = dock.actors[rid]
        assert [j['kind'] for j in own.jobs_done] == ['look_around'] and own.jobs_done[0]['outcome'] == 'LOOKED'
        assert own.jobs_done[0]['ended_at_sim_s'] <= relook.LOOK_S
        rep = own.pose.report(run['t_end'])
        assert rep.std_xy_m <= .05
        assert math.hypot(rep.x_m - hs.TRUE_DOCK[rid][0], rep.y_m - hs.TRUE_DOCK[rid][1]) <= .03   # evaluation only
        assert dock.look_recovery.state[rid]['attempts'] == []
    assert not any(c['kind'] not in relook.RELOOK_COMMANDS for _, _, c in run['issued'])          # no base motion
    assert dock.team.rendezvous_timeout_s == relook.RENDEZVOUS_TIMEOUT_S
    assert dock.record()['look_recovery']['robots']['r2']['attempts'] == []


def test_closed_loop_mutation_five_pans_refuses_r2_then_one_relook_admits_it(closed_loop):
    hs, _, (five, run) = closed_loop
    r2 = five.actors['r2']
    assert r2.jobs_done[0]['outcome'] == 'LOOKED_POSE_UNCERTAIN'                    # the five-pan look is not enough
    assert _first_refusal_after_look(five, 'r2')[0]['rejected_reason'] == 'SELF_UNCERTAIN'
    attempts = five.look_recovery.state['r2']['attempts']
    assert len(attempts) == 1 and attempts[0]['sigma_before']['std_xy_m'] > .05
    assert attempts[0]['sigma_after']['std_xy_m'] < attempts[0]['sigma_before']['std_xy_m']
    assert set(five.submitted) == {'r1', 'r2'}                                       # admitted after one re-look
    assert not any(c['kind'] not in relook.RELOOK_COMMANDS for _, _, c in run['issued'])
    # The partner admitted first waits through the re-look (5 s would have expired).
    session = five.team.sessions[0]
    r1_admitted = next(a['sim_s'] for a in five.actors['r1'].api_log if a['api'] == 'pair_carry' and a['accepted'])
    r2_admitted = next(a['sim_s'] for a in r2.api_log if a['api'] == 'pair_carry' and a['accepted'])
    assert r2_admitted - r1_admitted > 5. and len(session['endpoints']) == 2
    assert not any(ep.terminal for ep in session['endpoints'].values())
