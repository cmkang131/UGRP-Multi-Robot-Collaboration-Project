"""v98 same-tick final veto (Codex review of 73429982, 'same-tick abort/dispatch').

The shared ``zone_final_pair_runtime.Runtime.step`` collects each actor's commands in sequence and
polls the team afterwards, so motion collected from actor A before actor B aborted in the same tick
is still returned (A is already terminal by PARTNER_ABORT at that point). ``arm_step`` collects the
same way and has no poll at all. The v98 Runtime now vetoes terminal endpoints' non-hold commands
after propagation. These tests drive the REAL ``scripts/run_pair_highpose.student_run_case`` loop on
real pair endpoints (fake M2 controllers, fake backend) and read the commands at the backend
(``FakePhysics.actions``), i.e. at the command receipt, for both actor orders and both aborters.
"""
import json
from pathlib import Path
import re
import types

import pytest

from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_final_veto as fv
from harness import zone_pair_highpose_runtime as v98
from scripts import run_pair_highpose as run
from tests.test_highpose_dev_pilot import admit, dev_file
from tests.test_zone_final_pair_v3 import FakePhysics
from tests.test_zone_pair_executor import FakeM2, PoseReport, SEARCH_POSE, ends, pair_obs, setup, start

ROBOTS = ('r1', 'r2')
ORDERS = (('r1', 'r2'), ('r2', 'r1'))
START_S = 1.                      # FakePhysics.reset() returns 1.0
HORIZON_S = 1.                    # the fake backend stops the real loop 1 SIM s after the start
SHARED = v98.PreviousRuntime      # the frozen shared runtime (unvetoed)
CASES = [(order, aborter) for order in ORDERS for aborter in ROBOTS]
IDS = [f'order-{"".join(o)}-aborter-{a}' for o, a in CASES]


class ArmM2(FakeM2):
    """FakeM2 whose arm clock emits one look command (an arm-clock command that passes the real command guard) per arm tick once the carry starts."""
    def __init__(self, ep, plan, params):
        super().__init__(ep, plan, params)
        self.arm = types.SimpleNamespace(events=[(100., 1, 1500)], until=101., tick=self._arm_tick)

    def _arm_tick(self, now):
        if self.state != 'carry':
            return
        trigger = self.ep.own.abort_plan
        if trigger and trigger['phase'] == 'arm' and trigger['rid'] == self.ep.own.robot_id \
                and now >= trigger['t'] - 1e-9 and self.state != 'failed':
            self.state, self.failure = 'failed', 'ARM_TEST_FAIL'      # discovered only by the next check
        self.ep.port.apply({'kind': 'look', 'pan_pulse': SEARCH_POSE[6]}, now)


class GuardM2(FakeM2):
    """FakeM2 that lowers servo 1 once the carry starts. The REAL pair command guard vetoes it
    (PREGRASP_BEAM_UNSAFE) inside the arm clock: a natural arm-phase abort, no injected failure."""
    def __init__(self, ep, plan, params):
        super().__init__(ep, plan, params)
        self.arm = types.SimpleNamespace(events=[(100., 1, 1500)], until=101., tick=self._arm_tick)

    def _arm_tick(self, now):
        if self.state == 'carry':
            self.ep.port.apply({'kind': 'arm', 'servo_id': 1, 'pulse': 1500}, now)


class Rig(v98.Runtime):
    """v98 Runtime on real pair endpoints; only the heavy provider ``__init__`` is skipped.

    ``step``, ``arm_step`` and ``record`` are the production ones (or ``base`` for the unvetoed comparison).
    """
    def __init__(self, order, factory, abort_plan):
        self.host, self.exs = setup(factory=factory)
        for ex in self.exs.values():
            ex.abort_plan = abort_plan
        self.abort_plan = abort_plan
        self.actors = {r: self.exs[r] for r in order}
        self.team, self.started, self.submitted, self.task = self.host.pairs, True, set(order), {'target': 'B'}
        self.job_sim_limit_s, self.own_image_gates = c.CASE_CAP_S, {}
        self.fid, self.base_obs = 0, {r: pair_obs(r, 1, 0., SEARCH_POSE) for r in ROBOTS}
        self.look_recovery = v98.adopt_look_recovery(self)        # as Runtime/StagedRuntime do (dock/re-look diff)

    def initial_commands(self, now, commands):
        self.host.world.data.time = now
        for ex in self.exs.values():
            ex.now = now
        self._fresh_frames(now)
        ack = start(self.host)
        assert ack['accepted'], ack

    def _fresh_frames(self, now):
        self.fid += 1
        for r, ex in self.exs.items():
            if r in ROBOTS:
                ex.last_obs = {**self.base_obs[r], 'frame_id': self.fid + 1, 'sim_time': now}
                ex.last_report = PoseReport(t_est=now, initialized=True, x_m=0., y_m=0., yaw_rad=0.,
                                            std_xy_m=.01, std_yaw_rad=.01, last_fix_t=now, source=ex.pose.source)

    def on_frames(self, now, frames):
        self._fresh_frames(now)
        plan = self.abort_plan
        if plan and plan['phase'] == 'step' and now >= plan['t'] - 1e-9 and plan.get('fired') is None:
            plan['fired'] = now
            ctl = self.endpoints()[plan['rid']].controller
            ctl.state, ctl.failure = 'failed', 'STEP_TEST_FAIL'

    def endpoints(self):
        return self.host.pairs.sessions[-1]['endpoints']

    def on_command(self, rid, now, action):
        pass

    def close(self):
        pass

    def record(self):
        # The production v98 record(): shared record + final_veto. Only the localizer provider record is faked.
        for ex in self.exs.values():
            ex.pose = types.SimpleNamespace(record=lambda: {}, source=ex.pose.source)
        return super().record()


class UnvetoedRig(Rig):
    """Same rig with the shared parent's step/arm_step (what v98 did before the veto)."""
    step = SHARED.step
    arm_step = SHARED.arm_step


@pytest.fixture(scope='module')
def dev_artifacts(tmp_path_factory):
    """DEV_PILOT calibration file + carry bundle, built once (the file build is the slow part)."""
    root = tmp_path_factory.mktemp('dev')
    path, _ = dev_file(root)
    sha = c.base.sha(path)
    with pytest.MonkeyPatch.context() as mp:
        admit(mp, sha)
        # Not p03: p03 post-processing needs the real controller's checkpoint rows.
        case = c.cases('carry')[0]
        bundle = {**c.bundle(case['map_id'], 'carry', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    return bundle, path, sha


@pytest.fixture
def dev_bundle(dev_artifacts, monkeypatch):
    admit(monkeypatch, dev_artifacts[2])
    return dev_artifacts


class HorizonPhysics(FakePhysics):
    """FakePhysics that ends the (otherwise case-cap long) loop deliberately after HORIZON_S."""
    def advance_to(self, t):
        if t > START_S + HORIZON_S + 1e-9:
            raise RuntimeError('TEST_HORIZON')
        super().advance_to(t)


def drive(dev_bundle, tmp_path, name, rig_cls, order, factory, abort_plan):
    bundle, path, sha = dev_bundle
    holder, physics = {}, []

    def make_physics(*a, **kw):
        physics.append(HorizonPhysics(*a, **kw))
        return physics[-1]

    def make_runtime(*a, **kw):
        holder['rt'] = rig_cls(order, factory, abort_plan)
        return holder['rt']

    result = run.student_run_case(bundle, tmp_path/name, seed=911, backend_factory=make_physics,
                                  runtime_factory=make_runtime, calibration=path, calibration_sha=sha)
    assert result['failure']['message'] == 'TEST_HORIZON', result       # reached the horizon, nothing else broke
    return result, holder['rt'], physics[0]


@pytest.fixture(scope='module')
def first_motion_s():
    """Tick at which the fake carry first moves (no abort): the tick every scenario aborts at."""
    rig = Rig(('r1', 'r2'), FakeM2, None)
    rig.initial_commands(START_S, {})
    for i in range(10):
        now = round(START_S + i*.1, 8)
        rig.on_frames(now, {})
        if any(cmd['kind'] != 'hold' for _, cmd in rig.step(now)):
            return now
    raise AssertionError('fake carry never moved')


def at(physics, now):
    return [(rid, a) for t, rid, a in physics.actions if abs(t-now) < 1e-9]


def nonhold_after(physics, now):
    return [(t, rid, a) for t, rid, a in physics.actions if t >= now - 1e-9 and a['kind'] != 'hold']


def abort_plan(phase, aborter, t):
    return {'phase': phase, 'rid': aborter, 't': t, 'fired': None}


@pytest.mark.parametrize('order,aborter', CASES, ids=IDS)
def test_step_abort_tick_dispatches_only_holds_for_the_terminal_pair(tmp_path, dev_bundle, first_motion_s, order, aborter):
    result, rt, physics = drive(dev_bundle, tmp_path, 'veto', Rig, order, FakeM2,
                                abort_plan('step', aborter, first_motion_s))
    eps = rt.endpoints()
    assert all(ep.terminal for ep in eps.values())
    tick = at(physics, first_motion_s)
    assert sorted(rid for rid, _ in tick) == list(ROBOTS)                      # one command per robot ...
    assert all(a == {'kind': 'hold'} for _, a in tick)                         # ... and it is a hold
    assert nonhold_after(physics, first_motion_s) == []                        # nothing moves afterwards either
    # Before the abort tick the fake carry had not moved yet: the abort tick is the first motion tick.
    assert [a for t, _, a in physics.actions if t < first_motion_s-1e-9 and a['kind'] != 'hold'] == []


@pytest.mark.parametrize('order,aborter', CASES, ids=IDS)
def test_vetoed_command_is_logged_with_its_content_and_reason(tmp_path, dev_bundle, first_motion_s, order, aborter):
    result, rt, physics = drive(dev_bundle, tmp_path, 'log', Rig, order, FakeM2,
                                abort_plan('step', aborter, first_motion_s))
    stored = json.loads((tmp_path/'log'/'student_record.json').read_text())
    log = stored['final_veto']
    assert log['profile'] == fv.PROFILE and log['count'] == len(log['vetoes'])
    leaks = [v for v in log['vetoes'] if v['vetoed']]
    # The leak exists exactly when the aborter is processed after the other actor collected motion.
    leaked_order = order.index(aborter) == 1
    other = next(r for r in ROBOTS if r != aborter)
    if leaked_order:
        assert len(leaks) == 1
        entry = leaks[0]
        assert entry['robot_id'] == other and entry['phase'] == 'step' and entry['sim_s'] == pytest.approx(first_motion_s)
        assert entry['vetoed'] == [{'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15}]
        assert entry['reason'] == 'PARTNER_ABORT' and entry['newly_terminal'] is True
        assert entry['terminal_after'] == list(ROBOTS) and entry['hold_added'] is False
    else:
        assert leaks == []
    assert result['commands_issued'] and stored['pair']          # the existing record content is intact


@pytest.mark.parametrize('order,aborter', CASES, ids=IDS)
def test_arm_step_abort_tick_ends_in_hold_and_dispatches_no_arm_clock_command(tmp_path, dev_bundle, order, aborter):
    # Find the first tick at which the fake carry emits an arm command (no abort).
    rig = Rig(order, ArmM2, None)
    rig.initial_commands(START_S, {})
    first_arm = None
    for i in range(10):
        now = round(START_S + i*.1, 8)
        rig.on_frames(now, {})
        rig.step(now)
        if any(cmd['kind'] == 'look' for _, cmd in rig.arm_step(now)):
            first_arm = now
            break
    assert first_arm is not None
    result, rt, physics = drive(dev_bundle, tmp_path, 'arm', Rig, order, ArmM2, abort_plan('arm', aborter, first_arm))
    assert all(ep.terminal for ep in rt.endpoints().values())
    tick = at(physics, first_arm)
    # No arm command reaches the backend at or after the abort tick, and each robot's last command at the tick is a hold.
    assert [a for t, _, a in physics.actions if t >= first_arm-1e-9 and a['kind'] == 'look'] == []
    for rid in ROBOTS:
        assert [a for r, a in tick if r == rid][-1] == {'kind': 'hold'}
    assert nonhold_after(physics, first_arm+.1) == []
    vetoes = json.loads((tmp_path/'arm'/'student_record.json').read_text())['final_veto']['vetoes']
    assert vetoes and {v['phase'] for v in vetoes} == {'arm_step'}
    assert any(v['vetoed'] and v['vetoed'][0]['kind'] == 'look' for v in vetoes)


def pair_record(rt):
    # The session/task id is a random uuid per run; everything else must match byte for byte.
    return re.sub(r'pair-[0-9a-f]{32}', 'pair-ID', json.dumps(rt.team.records(), sort_keys=True, default=str))


@pytest.mark.parametrize('order', ORDERS)
def test_guard_abort_in_arm_clock_gives_every_robot_a_hold_in_that_tick(tmp_path, dev_bundle, order):
    """Real-guard abort in arm_step; the partner goes terminal by PARTNER_ABORT with nothing queued in that phase.

    Its step-phase motion was already dispatched earlier in the tick, so the stop must arrive in the same
    tick through the arm-phase hold (``hold_added``). The shared runtime emits nothing for the partner there.
    """
    _, rt, physics = drive(dev_bundle, tmp_path, 'guard', Rig, order, GuardM2, None)
    log = rt.final_veto_log
    tick = min(entry['sim_s'] for entry in log)
    assert all(ep.terminal for ep in rt.endpoints().values())
    assert any(entry['hold_added'] and entry['phase'] == 'arm_step' for entry in log)
    for rid in ROBOTS:
        assert [a for r, a in at(physics, tick) if r == rid][-1] == {'kind': 'hold'}
    assert [a for t, _, a in physics.actions if t >= tick-1e-9 and a['kind'] == 'arm'] == []
    assert nonhold_after(physics, tick+.1) == []
    _, _, plain = drive(dev_bundle, tmp_path, 'guard-plain', UnvetoedRig, order, GuardM2, None)
    assert any([a for r, a in at(plain, tick) if r == rid][-1]['kind'] != 'hold' for rid in ROBOTS)


@pytest.mark.parametrize('order', ORDERS)
def test_no_abort_run_is_identical_to_the_unvetoed_runtime(tmp_path, dev_bundle, order):
    """No terminal endpoint, no change: same commands, same pair record, empty veto log."""
    ra, rta, pa = drive(dev_bundle, tmp_path, 'veto', Rig, order, ArmM2, None)
    rb, rtb, pb = drive(dev_bundle, tmp_path, 'plain', UnvetoedRig, order, ArmM2, None)
    assert pa.actions == pb.actions and any(a['kind'] != 'hold' for _, _, a in pa.actions)
    assert ra['commands_issued'] == rb['commands_issued']
    assert rta.final_veto_log == []
    assert pair_record(rta) == pair_record(rtb)


@pytest.mark.parametrize('order,aborter', CASES, ids=IDS)
def test_mutation_unvetoed_runtime_leaks_exactly_when_the_aborter_runs_second(tmp_path, dev_bundle, first_motion_s, order, aborter):
    """Control: the shared step leaks a non-hold at the abort tick (the Codex claim) in exactly two of four cases."""
    _, rt, physics = drive(dev_bundle, tmp_path, 'leak', UnvetoedRig, order, FakeM2,
                           abort_plan('step', aborter, first_motion_s))
    leaked = [(rid, a['kind']) for rid, a in at(physics, first_motion_s) if a['kind'] != 'hold']
    other = next(r for r in ROBOTS if r != aborter)
    assert leaked == ([(other, 'mecanum')] if order.index(aborter) == 1 else [])


@pytest.mark.parametrize('order', ORDERS)
def test_mutation_arm_step_without_propagation_leaks(tmp_path, dev_bundle, monkeypatch, order):
    """Mutation: an arm_step veto that does not propagate state first cannot see the peer abort."""
    monkeypatch.setattr(v98.Runtime, 'arm_step',
                        lambda self, now: self._vetoed('arm_step', now, super(v98.Runtime, self).arm_step, lambda t: None))
    aborter = order[1]
    rig = Rig(order, ArmM2, None)
    rig.initial_commands(START_S, {})
    first_arm = None
    for i in range(10):
        now = round(START_S + i*.1, 8)
        rig.on_frames(now, {})
        rig.step(now)
        if any(cmd['kind'] == 'look' for _, cmd in rig.arm_step(now)):
            first_arm = now
            break
    _, rt, physics = drive(dev_bundle, tmp_path, 'noprop', Rig, order, ArmM2, abort_plan('arm', aborter, first_arm))
    assert [a for t, _, a in physics.actions if abs(t-first_arm) < 1e-9 and a['kind'] == 'look']


def test_final_veto_function_edge_cases():
    team = types.SimpleNamespace(sessions=[])
    mec = {'kind': 'mecanum', 'forward': .1}
    arm = {'kind': 'arm', 'servo_id': 1, 'pulse': 1500}
    hold = {'kind': 'hold'}
    log = []
    # Nothing terminal: the very same list contents, no log.
    issued = [('r1', mec), ('r2', arm)]
    assert fv.final_veto(issued, 0., 'step', set(), set(), team, log) == issued and log == []
    # Terminal with only holds, already terminal before: untouched, nothing added.
    issued = [('r1', hold), ('r1', hold)]
    assert fv.final_veto(issued, 0., 'step', {'r1'}, {'r1'}, team, log) == issued and log == []
    # Several non-holds collapse into one hold at the first position; the other robot is untouched.
    issued = [('r1', mec), ('r2', arm), ('r1', arm), ('r1', hold)]
    out = fv.final_veto(issued, .5, 'step', set(), {'r1'}, team, log)
    assert out == [('r1', hold), ('r2', arm)]
    assert [(e['robot_id'], e['vetoed'], e['sim_s']) for e in log] == [('r1', [mec, arm], .5)]
    # Newly terminal robot with nothing queued still gets its hold in the same call; a second one does not.
    log.clear()
    out = fv.final_veto([('r2', arm)], 1., 'arm_step', set(), {'r1'}, team, log)
    assert out == [('r2', arm), ('r1', hold)] and log[0]['hold_added'] and log[0]['robot_id'] == 'r1'
    log.clear()
    assert fv.final_veto([('r1', hold)], 1., 'step', set(), {'r1'}, team, log) == [('r1', hold)] and log == []
    # The returned holds are fresh objects, not the shared constant.
    out = fv.final_veto([('r1', mec)], 1., 'step', set(), {'r1'}, team, [])
    assert out[0][1] == hold and out[0][1] is not fv.HOLD
    assert issued[0][1] is mec and mec == {'kind': 'mecanum', 'forward': .1}


def test_endpoint_lookup_uses_the_latest_session_and_never_the_peer():
    old = types.SimpleNamespace(terminal=True)
    new = types.SimpleNamespace(terminal=False)
    team = types.SimpleNamespace(sessions=[{'endpoints': {'r1': old, 'r2': old}}, {'endpoints': {'r1': new}}])
    assert fv.endpoint(team, 'r1') is new and fv.endpoint(team, 'r2') is old and fv.endpoint(team, 'r3') is None
    assert fv.terminal_robots(team, ['r1', 'r2', 'r3']) == {'r2'}


class SpyRig(Rig):
    """Rig that counts the look-recovery hooks the production ``step`` must call."""
    calls = None

    def __init__(self, *args):
        super().__init__(*args)
        type(self).calls = calls = {'pre_step': 0, 'filter': 0}
        rec = self.look_recovery
        pre, flt = rec.pre_step, rec.filter

        def pre_step(runtime, now):
            calls['pre_step'] += 1
            return pre(runtime, now)

        def filter_(runtime, now, issued):
            calls['filter'] += 1
            return flt(runtime, now, issued)
        rec.pre_step, rec.filter = pre_step, filter_


def test_step_runs_the_look_recovery_hooks_and_the_final_veto_in_one_override(tmp_path, dev_bundle, first_motion_s):
    # The dock/re-look diff and this diff each defined ``Runtime.step``; a second ``def step`` would silently
    # shadow the first. One override must run both: look-recovery bookkeeping/filter, then the final veto.
    assert sum(1 for line in Path(v98.__file__).read_text().splitlines() if line.startswith('    def step(')) == 1
    order, aborter = ('r1', 'r2'), 'r2'
    _, rt, physics = drive(dev_bundle, tmp_path, 'spy', SpyRig, order, FakeM2, abort_plan('step', aborter, first_motion_s))
    assert SpyRig.calls['pre_step'] > 0 and SpyRig.calls['pre_step'] == SpyRig.calls['filter']
    assert all(a == {'kind': 'hold'} for _, a in at(physics, first_motion_s))          # the veto still ran last
    assert rt.final_veto_log and 'look_recovery' in rt.record()
