"""v98 re-look posture deferral: replay of the af2f7c2a r2 align timeline (simulator-free).

Real pieces: ``ArmSequence`` (the pair executor's arm queue), the shared ``PairAlignRelook`` re-look state machine and
``relook_reason``, the measured camera-model keys of the v98 DEV calibration and ``camera_key``. Fakes: the port,
status channel, and a provider that mimics the measured behaviour of the v98 provider: a frame taken 0.3 s after
the last own servo command (PF ``settle_s``) at a posture without a measured camera model fails the provider closed
(``UNMEASURED_V3_CAMERA_POSTURE``); during a re-look a settled frame at a measured posture gives a fix.

Recorded r2 timeline (outputs/v98-dev-probe-raise_high_align-af2f7c2a): look posture p45 at 20.2 s, inspect
(``band_clipped``) at 24.9 s, ``fix_gap`` re-look at 25.0 s, stopped pose 25.2 s, provider failure 25.25 s with
key 765,1991,1865,1500, fix rejections 26.6/27.6/28.6 s, ``ALIGN_RELOOK_NO_FIX``.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import owncam_pair_beam_v2 as ob2
from harness import zone_pair_highpose_posture_defer as defer
from harness.owncam_pose_source import PoseReport
from harness.vision_pose_source_final import camera_key
from harness.zone_pair_align import PairAlignRelook
from scripts.zone_teacher import ArmSequence

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT/'experiments'/'2026-10-03-v92-dev-pilot'/'calibration_dev_pilot.json'
SETTLE_S = .3                      # PF measurement settle_s (recorded: last command 24.95 s -> failure 25.25 s)
STOP_READY_S = .2                  # recorded: re-look 25.0 s -> stopped pose 25.2 s
FREEZE_KEY = '765,1991,1865,1500'
TICK = .05


def _keys():
    return defer.measured_keys(json.loads(CALIBRATION.read_text()))


class Provider:
    def __init__(self, keys, last_fix_t):
        self.keys, self.last_fix_t = keys, last_fix_t
        self.last_cmd_t, self.failure, self.looking, self.loc = -1., None, False, object()

    def on_command(self, now):
        self.last_cmd_t = now

    def begin_relocalization(self, now, servo):
        self.looking = True

    def frame(self, now, servo):
        if self.failure is not None or now - self.last_cmd_t < SETTLE_S - 1e-9:
            return
        key = camera_key(servo)
        if key not in self.keys['unloaded']:
            self.failure = {'t': round(now, 4), 'reason': f'UNMEASURED_V3_CAMERA_POSTURE: unloaded:{key}'}
        elif self.looking:
            self.last_fix_t, self.looking = now, False

    def report(self, now):
        if self.failure is not None:
            return PoseReport(t_est=now, initialized=False)
        return PoseReport(t_est=now, initialized=True, x_m=.4, y_m=-.2, yaw_rad=0., std_xy_m=.023,
                          std_yaw_rad=.014, last_fix_t=self.last_fix_t, fix_age_s=now-self.last_fix_t,
                          load_state='unloaded')


class Port:
    def __init__(self, servo, provider):
        self.provider, self.holds, self.arm_commands = provider, [], []
        self.own = SimpleNamespace(servo=dict(servo), last_report=None, gate=SimpleNamespace(ok=True),
                                   pose=SimpleNamespace(loc=provider.loc,
                                                        begin_relocalization=provider.begin_relocalization))

    def hold(self, now):
        self.holds.append(round(now, 4))

    def apply(self, cmd, now):
        sid, pulse = (6, cmd['pan_pulse']) if cmd['kind'] == 'look' else (cmd['servo_id'], cmd['pulse'])
        self.own.servo[sid] = pulse
        self.arm_commands.append((round(now, 4), sid, pulse))
        self.provider.on_command(now)


class Status:
    def __init__(self):
        self.ticks, self.partner = [], {}

    def partner_view(self, rid, now):
        return self.partner

    def tick(self, state, now):
        self.ticks.append((round(now, 4), state))


class Base:
    """The parts of the frozen study controller the re-look path uses (set/fail/tick/_set_look/_align)."""

    def set(self, state, now, **detail):
        self.log(self.rid, 'state', now, state=state, **detail)
        self.state, self.state_t = state, now

    def fail(self, reason, now):
        self.failure = reason
        self.set('failed', now, reason=reason)

    def tick(self, now):
        idle = now >= self.arm.until and not self.arm.events
        handler = getattr(self, '_' + self.state, None)
        if handler is not None:
            handler(now, idle)

    def _set_look(self, name, now, **why):
        self.log(self.rid, 'look_posture', now, posture=name, **why)
        self.look_name = name
        self.arm.queue(ob2.pose_of(name), now, duration=.6)

    def _align(self, now, idle):
        if idle:
            self.align_ticks.append(round(now, 4))


class Stubs:
    """Collision-checked view choice and the post-stop report wait are tested elsewhere; fixed here."""

    def align_stop_ready(self, now):
        return now - self.align_look_started_at >= STOP_READY_S - 1e-9

    def align_look_choices(self):
        return [{'pan': 1500, 'observability_score': 1.}, {'pan': 1230, 'observability_score': .5}]

    def look(self, now):
        return {'sim_time': now, 'frame_id': int(round(now/TICK)), 'sha256': '0'*64}


def make(cls_mixins=(defer.DeferRelook,), *, posture='p45', last_fix_t=19.0):
    keys = _keys()
    provider = Provider(keys, last_fix_t)
    servo = {1: 2000, **ob2.pose_of(posture)}
    port = Port(servo, provider)
    cls = type('Ctl', (*cls_mixins, Stubs, PairAlignRelook, Base), {})
    ctl = cls.__new__(cls)
    ctl.rid, ctl.port, ctl.provider, ctl.events = 'r2', port, provider, []
    ctl.log = lambda rid, kind, now, **v: ctl.events.append({'event': kind, 'sim_s': round(now, 4), **v})
    ctl.arm = ArmSequence(port, servo)
    ctl.status = (Status(), Status())
    ctl.policy = SimpleNamespace(beam_relative=False, posterior_relook=False, align_fine_motion=False)
    ctl.driver = SimpleNamespace(loc=provider.loc)
    ctl.look_name, ctl.beam_grasp_confirmed, ctl.align_ticks = posture, False, []
    ctl.state, ctl.state_t, ctl.align_started_at = 'align', 20.2, 20.2
    ctl.v98_measured_camera_keys = keys
    return ctl


def run(ctl, t0, t1, *, at=None):
    """Pair tick order: own frame -> report -> control tick -> arm clock."""
    at = at or {}
    for i in range(int(round((t1 - t0)/TICK)) + 1):
        now = round(t0 + i*TICK, 4)
        ctl.provider.frame(now, ctl.port.own.servo)
        ctl.port.own.last_report = ctl.provider.report(now)
        if now in at:
            at[now](ctl, now)
        if ctl.state != 'failed':
            ctl.tick(now)
        ctl.arm.tick(now)
    return ctl


def inspect_at_24_9(ctl, now):
    ctl._set_look('inspect', now, reason='band_clipped')


def kinds(ctl, kind):
    return [e for e in ctl.events if e['event'] == kind]


def test_fixture_reproduces_the_recorded_freeze_without_the_deferral():
    ctl = run(make(cls_mixins=()), 20.2, 29.0, at={24.9: inspect_at_24_9})
    trig = kinds(ctl, 'align_relook_trigger')
    assert [(t['sim_s'], t['reason']) for t in trig] == [(25.0, 'fix_gap')]
    assert ctl.provider.failure == {'t': 25.25, 'reason': f'UNMEASURED_V3_CAMERA_POSTURE: unloaded:{FREEZE_KEY}'}
    assert ctl.failure in ('ALIGN_RELOOK_NO_FIX', 'ALIGN_RELOOK_TIMEOUT')


def test_af2f7c2a_r2_timeline_relook_waits_for_the_inspect_posture():
    ctl = run(make(), 20.2, 30.0, at={24.9: inspect_at_24_9})
    deferred = kinds(ctl, 'align_relook_deferred')
    assert [(d['sim_s'], d['reason'], d['posture_key'], d['moving']) for d in deferred] == \
        [(25.0, 'fix_gap', FREEZE_KEY, True)]
    # The inspect interpolation was never cut: every queued step went out, the last at 25.5 s.
    inspect = ob2.pose_of('inspect')
    assert [c for c in ctl.port.arm_commands if c[0] <= 25.5][-4:] == [(25.5, s, inspect[s]) for s in (3, 4, 5, 6)]
    end = kinds(ctl, 'align_relook_defer_end')
    assert len(end) == 1 and end[0]['posture_key'] == camera_key(inspect) and end[0]['sim_s'] == 25.55
    trig = kinds(ctl, 'align_relook_trigger')
    assert [(t['sim_s'], t['reason']) for t in trig] == [(25.55, 'fix_gap')]
    assert ctl.provider.failure is None                        # the provider stays initialized
    assert kinds(ctl, 'align_relook_fix') and not kinds(ctl, 'align_relook_fix_rejected')
    assert ctl.state == 'align' and getattr(ctl, 'failure', None) is None
    assert [t for t in ctl.align_ticks if t > trig[0]['sim_s']]          # align proceeds after the re-look
    assert ctl.port.holds and ctl.port.holds[0] == 25.0
    assert (25.0, 'aligning') in ctl.status[1].ticks and (25.5, 'aligning') in ctl.status[1].ticks


def test_mutation_without_the_transition_check_freezes_at_the_unmeasured_posture(monkeypatch):
    real = defer.posture

    def ready_whenever_measured_or_moving(ctl, now):
        st = real(ctl, now)
        return {**st, 'ready': True}
    monkeypatch.setattr(defer, 'posture', ready_whenever_measured_or_moving)
    ctl = run(make(), 20.2, 29.0, at={24.9: inspect_at_24_9})
    assert ctl.provider.failure is not None and FREEZE_KEY in ctl.provider.failure['reason']
    assert getattr(ctl, 'failure', None) is not None


def test_idle_measured_posture_starts_at_once_as_before():
    ctl = run(make(last_fix_t=19.0), 20.2, 25.2)
    assert not kinds(ctl, 'align_relook_deferred')
    assert [(t['sim_s'], t['reason']) for t in kinds(ctl, 'align_relook_trigger')] == [(25.0, 'fix_gap')]


def test_interrupted_transition_returns_to_the_last_measured_posture_before_observing():
    def interrupt(ctl, now):                       # some other cause drops the queue mid-way (executor _clear style)
        ctl.arm.events.clear()
        ctl.arm.until = now
    ctl = run(make(last_fix_t=19.5), 20.2, 30.0, at={24.9: inspect_at_24_9, 25.0: interrupt})
    restore = kinds(ctl, 'align_posture_restore')
    p45 = camera_key(ob2.pose_of('p45'))
    assert len(restore) == 1 and restore[0]['sim_s'] == 25.0 and restore[0]['to_key'] == p45
    assert restore[0]['from_key'] not in _keys()['unloaded']
    trig = kinds(ctl, 'align_relook_trigger')
    assert trig and trig[0]['sim_s'] > restore[0]['sim_s']
    assert ctl.provider.failure is None and ctl.state == 'align'


def test_no_measured_posture_known_fails_closed():
    ctl = make()
    ctl.port.own.servo.update({3: 765, 4: 1991, 5: 1865})      # idle at an unmeasured posture from the start
    ctl.arm.commanded.update({3: 765, 4: 1991, 5: 1865})
    run(ctl, 25.0, 25.1)
    assert ctl.failure == defer.NO_RESTORE_CODE


def test_partner_abort_while_queued():
    def abort(ctl, now):
        ctl.status[0].partner = {'r1': {'state': 'abort'}}
    ctl = run(make(), 20.2, 26.0, at={24.9: inspect_at_24_9, 25.2: abort})
    assert ctl.failure == 'PARTNER_ABORT' and kinds(ctl, 'state')[-1]['sim_s'] == 25.2


def test_wait_is_bounded_by_the_existing_look_allowance():
    def stuck(ctl, now):                            # e.g. arm commands held back forever
        ctl.arm.events = [(1e9, 3, 600)]
    ctl = run(make(), 20.2, 34.0, at={24.9: inspect_at_24_9, 24.95: stuck})
    assert ctl.failure == defer.TIMEOUT_CODE
    assert kinds(ctl, 'state')[-1]['sim_s'] == pytest.approx(25.0 + defer.MAX_LOOK_S)


def test_align_entry_during_a_transition_enters_align_and_fires_later():
    ctl = make(last_fix_t=24.0)
    ctl.state = 'align_start'
    ctl.arm.queue(ob2.pose_of('search'), 24.0, duration=.8)
    ctl.set('align', 24.0)                       # PairAlignRelook.set -> _begin_align_relook('align_entry')
    assert ctl.state == 'align' and kinds(ctl, 'align_relook_deferred')[0]['reason'] == 'align_entry'
    run(ctl, 24.05, 26.0)
    trig = kinds(ctl, 'align_relook_trigger')
    assert trig and trig[0]['reason'] == 'align_entry' and trig[0]['sim_s'] >= 24.8
    assert ctl.provider.failure is None


def test_unbuilt_controller_raises_on_the_align_path():
    ctl = make()
    ctl.v98_measured_camera_keys = None
    with pytest.raises(RuntimeError):
        ctl._begin_align_relook(25.0, 'fix_gap')


def test_runtime_wiring_and_record():
    from harness import zone_pair_highpose_runtime as rt
    cls = rt.controller_class(type('B', (PairAlignRelook, Base), {}))
    assert cls.__mro__[1] is rt.LightFail and cls.__mro__[2] is defer.DeferRelook   # v105 DEV light in front
    rec = defer.record()
    assert rec['id'] == defer.ID and rec['shared_sources_modified'] is False and rec['bound_s'] == defer.MAX_LOOK_S
    src = (ROOT/'harness'/'zone_pair_highpose_runtime.py').read_text()
    assert "posture_defer.measured_keys(kwargs['calibration'])" in src and "'relook_posture_defer'" in src


def test_mutation_without_the_restore_lets_the_provider_fail(monkeypatch):
    monkeypatch.setattr(defer.DeferRelook, '_v98_restore', lambda self, now, st: None)

    def interrupt(ctl, now):
        ctl.arm.events.clear()
        ctl.arm.until = now
    ctl = run(make(last_fix_t=19.5), 20.2, 27.0, at={24.9: inspect_at_24_9, 25.0: interrupt})
    assert ctl.provider.failure is not None and FREEZE_KEY in ctl.provider.failure['reason']
