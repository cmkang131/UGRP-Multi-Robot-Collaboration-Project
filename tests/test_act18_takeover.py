"""Pure-Python C1 takeover tests: no simulator, GPU, torch or MuJoCo.

The frozen SoloTeacher snapshot is used when a checkout is available
(``UGRP_SOLO_TEACHER_SOURCE`` or the local reloc12/gcp2 locations); those
integration cases skip on hosts without it. All trigger/clock/hold/gate logic
runs unconditionally with test doubles.
"""
from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from scripts.act16w_dagger import prepare_single_step, prepare_takeover_step
from scripts.act18_takeover import (NOMINAL_HOLD_S, TakeoverRgb, TakeoverTrigger,
                                    TeacherTakeover, issued_pwm, takeover_teacher)

ROOT = Path(__file__).resolve().parents[1]


def _teacher_source():
    candidates = (os.environ.get('UGRP_SOLO_TEACHER_SOURCE'),
                  '/home/ubuntu/UGRP/outputs/reloc12/source-ff1ccf27',
                  '/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690')
    for candidate in candidates:
        if candidate and (Path(candidate)/'sim'/'grasp_act_solo_teacher.py').is_file():
            return str(Path(candidate))
    return None


SOLO_SOURCE = _teacher_source()
requires_teacher = pytest.mark.skipif(SOLO_SOURCE is None,
    reason='frozen solo-teacher source snapshot not available on this host')


def _command(wheels=(0., 0., 0., 0.), pwm=None, t=0.):
    pwm = pwm or {str(s): 1500 for s in (1, 3, 4, 5, 6)}
    return dict(t=t, wheels=list(wheels), duration_s=[.1]*4, pwm=dict(pwm))


# ---------------------------------------------------------------- C1 trigger

def test_trigger_needs_both_elapsed_six_seconds_and_twenty_ticks():
    trigger = TakeoverTrigger()
    for i in range(19):
        assert trigger.observe(6.+i*.1, _command((1., 0., 0., 0.))) is False
    assert trigger.observe(7.9, _command((1., 0., 0., 0.))) is True
    assert trigger.fired_elapsed_s == 7.9
    assert trigger.record()['motion_source'].startswith('own issued wheel command')


def test_trigger_waits_for_six_seconds_even_after_twenty_moving_ticks():
    trigger = TakeoverTrigger()
    for i in range(20):
        assert trigger.observe(i*.1, _command((1., 0., 0., 0.))) is False
    for i in range(20, 60):
        assert trigger.observe(i*.1, _command((1., 0., 0., 0.))) is False
    assert trigger.observe(6.0, _command((1., 0., 0., 0.))) is True


def test_trigger_streak_resets_when_motion_class_changes():
    trigger = TakeoverTrigger()
    for i in range(10):
        trigger.observe(6.+i*.1, _command((1., 0., 0., 0.)))
    for i in range(10, 20):
        assert trigger.observe(6.+i*.1, _command()) is False  # max streak 10
    for i in range(20, 29):  # stopped streak reaches 19
        assert trigger.observe(6.+i*.1, _command()) is False
    assert trigger.observe(6.+29*.1, _command()) is True  # twentieth stopped tick


def test_stopped_student_also_triggers_after_twenty_ticks():
    trigger = TakeoverTrigger()
    for i in range(19):
        assert trigger.observe(6.+i*.1, _command()) is False
    assert trigger.observe(7.9, _command()) is True


# ------------------------------------------------------ state handoff / clock

def _fake_command(t):
    return dict(t=t, wheels=[0.]*4, duration_s=[0.]*4,
                pwm={str(s): 1500 for s in (1, 3, 4, 5, 6)})


class FakeTeacher:
    """Minimal teacher double: fold -> hold -> lower on the frozen 3 s gate."""

    def __init__(self):
        self.phase, self.phase_t, self.events, self.result = 'start', None, [], None
        self.sink = type('Sink', (), {'pwm': {1: 1502, 3: 1600, 4: 1900, 5: 2000, 6: 1200}})()
        self.holding = False
        self.low = self.grasp_xyz = None

    def _set(self, phase, now):
        self.events.append((phase, float(now)))
        self.phase, self.phase_t = phase, float(now)

    def step(self, now, *, measurement=None, rgb_holding='unknown', own_rgb=None):
        if self.phase == 'start':
            self._set('fold', now)
        elif self.phase == 'fold':
            self._set('hold', now)
        elif self.phase == 'hold' and now-self.phase_t >= NOMINAL_HOLD_S-1e-8:
            self._set('lower', now)
        return _fake_command(now), self.phase == 'lower'


def test_takeover_seeds_student_pwm_and_resets_phase_clock():
    captured = {}

    def factory(pwm):
        captured['pwm'] = pwm
        return FakeTeacher()

    pwm = {1: 1502, 3: 1600, 4: 1900, 5: 2000, 6: 1200}
    command = _command(pwm={str(k): v for k, v in pwm.items()})
    takeover = takeover_teacher({'kind': 'cyan', 'role': 'west'}, command,
                                now=12.3, hold_s=2.0, teacher_factory=factory)
    assert captured['pwm'] == pwm
    assert issued_pwm(command) == pwm
    # The fresh teacher's own _set(now) path stamps the takeover clock.
    assert takeover.teacher.events[0] == ('start', 12.3)
    assert takeover.teacher.phase_t == 12.3
    assert takeover.started_t == 12.3


@pytest.mark.parametrize('hold_s,expected_ticks,transition_t', [(3.0, 30, 3.1), (2.0, 20, 2.1)])
def test_hold_parameter_changes_only_the_hold_phase_clock(hold_s, expected_ticks, transition_t):
    command = _command()
    takeover = takeover_teacher({'kind': 'cyan', 'role': 'west'}, command, now=0.,
                                hold_s=hold_s, teacher_factory=lambda pwm: FakeTeacher())
    done = False
    for i in range(80):
        _, done = takeover.step(i*.1, measurement=None, rgb_holding='yes')
        if done:
            break
    assert takeover.teacher.phase == 'lower'
    assert abs(takeover.teacher.phase_t-transition_t) < 1e-9
    assert takeover.hold_ticks == expected_ticks
    assert takeover.phase_t_shift_s == pytest.approx(NOMINAL_HOLD_S-hold_s)
    assert 'lower' in takeover.phases and 'complete' not in takeover.phases


def test_hold_parameter_is_validated():
    with pytest.raises(ValueError):
        TeacherTakeover(FakeTeacher(), now=0., hold_s=0.)
    with pytest.raises(ValueError):
        TeacherTakeover(FakeTeacher(), now=0., hold_s=60.1)


def test_issued_pwm_rejects_partial_student_command():
    with pytest.raises(ValueError):
        issued_pwm(_command(pwm={'1': 2000, '3': 1500}))
    with pytest.raises(ValueError):
        issued_pwm(dict(wheels=[0.]*4))


# -------------------------------------------------------------- RGB channel

class FakeObserver:
    def __init__(self, kind):
        self.kind, self.calls = kind, []

    def start(self, frame, command, save):
        self.calls.append(('start', command['t']))

    def issue(self, command, phase):
        self.calls.append(('issue', phase))

    def observe(self, frame, command, *, complete, save):
        self.calls.append(('observe', bool(complete), command['t']))
        return {'answer': 'yes', 'evidence': 'fake_lookback'}


def _fake_save(tag, frame, now):
    return {'tag': tag, 't': now}


def test_lookback_channel_mirrors_the_episode_order():
    rgb = TakeoverRgb('cyan', mode='solo_lift_lookback_v1', save=_fake_save,
                      observer_factory=FakeObserver)
    frame = np.zeros((4, 4, 3), np.uint8)
    previous = _command(t=0.)
    teacher = type('Frozen', (), {'low': None, 'grasp_xyz': None,
                                  'sink': type('Sink', (), {'pwm': {}})()})()
    assert rgb.before_step(frame, now=.5, previous=previous, phase='lift',
                           teacher=teacher) == 'unknown'
    rgb.after_step(frame, now=.6, previous=previous, command=_command(t=.6),
                   phase_before='approach', phase_after='hover')
    assert rgb.before_step(frame, now=.7, previous=previous, phase='verify_lift',
                           teacher=teacher) == 'yes'
    assert rgb.observer.calls == [('observe', False, .5), ('start', .6),
                                  ('issue', 'hover'), ('observe', True, .7)]
    assert rgb.answers == ['yes']


def test_lift_answer_channel_is_used_when_not_lookback():
    calls = []

    def lift_answer(frame, pwm, kind, low, floor_xy):
        calls.append((kind, low, floor_xy))
        return 'no', {'evidence': 'fake_lift_answer'}

    rgb = TakeoverRgb('cyan', mode='solo_rgb_lift_v3', save=_fake_save,
                      lift_answer=lift_answer)
    frame = np.zeros((4, 4, 3), np.uint8)
    teacher = type('Frozen', (), {'low': {1: 1500}, 'grasp_xyz': (0.15, 0., 0.03),
                                  'sink': type('Sink', (), {'pwm': {'1': 1500}})()})()
    assert rgb.before_step(frame, now=1., previous=_command(), phase='hold',
                           teacher=teacher) == 'no'
    assert calls == [('cyan', {1: 1500}, (0.15, 0.))]


def test_oracle_bank_returns_takeover_commands_without_mutating_state(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    from act16w_oracle import OracleBank
    command = {'t': .5, 'wheels': [0.]*4, 'duration_s': [0.]*4,
               'pwm': {str(s): 1500 for s in (1, 3, 4, 5, 6)}}
    class FakeOracle:
        takeover_enabled = False
        takeover_ticks = 1
        audit = SimpleNamespace(invisible_measurements=0, held_world_reads=0)
        def blocked(self):
            return True
        def query(self, eyes, selected):
            self.takeover_command = command
            return {'sample_id': 'ep:0:r1', 't': .5, 'label_valid': True,
                    'takeover': True, 'done': False}
    state = np.array([1., 2., 3.])
    public = [({'t': .5, 'issued': []}, (b'jpeg',))]
    owner = SimpleNamespace(n=1, c=SimpleNamespace(command=lambda x: x),
        current=public, previous=[{'t': 0.}],
        integration=lambda: {'qpos': state.copy()},
        read_actor=lambda i: (public[i][0], tuple(public[i][1])),
        write=lambda *a: None, out=tmp_path)
    bank = OracleBank.__new__(OracleBank)
    bank.owner, bank.oracles, bank.queries, bank.eyes = owner, [FakeOracle()], 0, None
    bank.takeover_enabled, bank.takeover_commands = True, None
    bank.takeover_hold_s, bank.takeover_after_s = 2.0, 6.0
    labels, audit = bank.query([command])
    assert labels[0]['takeover'] is True
    assert bank.takeover_commands == [dict(command=command, done=False)]
    assert audit['teacher_actions_executed'] == 1
    assert audit['takeover']['hold_s'] == 2.0
    assert audit['takeover']['commands_emitted'] == 1
    assert audit['integration_and_actor_inputs_unchanged'] is True


def test_visible_oracle_takeover_glue_verifies_owner_step_execution(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import cv2
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import scripts.act16w_oracle as oracle_module
    frame = np.zeros((8, 8, 3), np.uint8)
    ok, jpeg = cv2.imencode('.jpg', frame)
    assert ok
    command = _command(t=.5)
    teacher = SimpleNamespace(phase='fold', holding=False, result=None)
    takeover = SimpleNamespace(teacher=teacher, hold_s=2.0,
        step=lambda now, **kw: (dict(command, t=now), False))
    created = {}
    def fake_takeover_teacher(plan, last, **kwargs):
        created.update(plan=plan, last=last, **kwargs)
        return takeover
    monkeypatch.setattr(oracle_module, 'takeover_teacher', fake_takeover_teacher)
    monkeypatch.setattr(oracle_module, 'TakeoverRgb',
        lambda kind, **kwargs: SimpleNamespace(
            before_step=lambda *a, **k: 'unknown',
            after_step=lambda *a, **k: None))
    observation = {'sample_id': 'ep:0:r1', 't': .4}
    owner = SimpleNamespace(origin=0., out=tmp_path,
        previous=[_command(t=.3)], active=[True])
    verifier = SimpleNamespace(active=[True], read_actor=lambda i: (
        {'sample_id': 'ep:0:r1', 't': .4, 'issued': [_command(t=.3)]},
        (jpeg.tobytes(),)))
    owner.read_actor = verifier.read_actor
    created['plan'] = {'kind': 'cyan', 'role': 'west'}
    instance = oracle_module.VisibleOracle.__new__(oracle_module.VisibleOracle)
    instance.owner, instance.i = owner, 0
    instance.plan, instance.ctx = created['plan'], {'gids': [1]}
    instance.audit = SimpleNamespace(
        invisible_measurements=0, held_world_reads=0,
        measure=lambda *a, **k: None)
    instance.route_rejections, instance.takeover_ticks = [], 0
    instance.takeover_enabled, instance.takeover_hold_s = True, 2.0
    instance.takeover, instance.takeover_rgb = None, None
    instance.takeover_command = instance.last_takeover_command = None
    instance._relative = lambda teacher: None
    instance._refresh_obstacles = lambda eyes: None
    instance.ops, instance.route = object(), object()
    instance._start_takeover(.4)
    assert created['last'] == _command(t=.3)  # last APPLIED student command
    assert created['hold_s'] == 2.0
    eyes = SimpleNamespace(region_visible=lambda i, gids: (1, 1))
    row = instance._takeover_query(eyes, _command(t=.4), observation,
                                   (jpeg.tobytes(),), .4)
    assert row['takeover'] is True and row['teacher_command']['t'] == .4
    assert row['done'] is False and instance.takeover_command == row['teacher_command']
    owner.previous[0] = row['teacher_command']
    instance._takeover_query(eyes, _command(t=.5), observation,
                             (jpeg.tobytes(),), .5)  # previous command verified
    owner.previous[0] = _command(t=.45)
    with pytest.raises(RuntimeError, match='owner.step'):
        instance._takeover_query(eyes, _command(t=.6), observation,
                                 (jpeg.tobytes(),), .6)
    owner.active = [False]  # terminated takeover world emits no extra command
    inactive = instance.query(eyes, _command(t=.7))
    assert inactive['label_valid'] is False and instance.takeover_command is None


# --------------------------------------------------------------- label gate

class FakeContract:
    CHUNK, ACTION_DIM = 8, 14

    @staticmethod
    def validate_observation(obs):
        if 'sample_id' not in obs:
            raise ValueError('observation')

    @staticmethod
    def command(value):
        return dict(value)

    @staticmethod
    def encode_action(command, done=False):
        return np.full(14, float(command['value']), dtype=np.float32)


def _admission_fixture():
    obs = [dict(sample_id=f'episode:{i}:r1', t=i*.1) for i in range(4)]
    labels = []
    for i, o in enumerate(obs):
        labels.append(dict(sample_id=o['sample_id'], t=o['t'], teacher_phase='align',
                           phase_after='align', label_valid=True,
                           teacher_command=dict(t=o['t'], value=i+1), done=False))
    audit = dict(invisible_measurements=0, held_world_reads=0,
                 teacher_actions_executed=0,
                 integration_and_actor_inputs_unchanged=True)
    return obs, labels, audit


def _takeover_rows(obs, labels):
    for i in (2, 3):
        labels[i].update(teacher_phase='hold', phase_after='lower', label_valid=True,
                         teacher_command=dict(t=obs[i]['t'], value=i+1),
                         done=False, takeover=True, hold_s=2.0, rgb_holding='yes',
                         query_blocked_by_hold_boundary=True)
    return labels


def test_takeover_path_bypasses_pre_hover_and_close_gate():
    obs, labels, audit = _admission_fixture()
    _takeover_rows(obs, labels)
    audit['teacher_actions_executed'] = 2
    label_only, _ = prepare_single_step(obs, labels, contract=FakeContract, audit={**audit,
        'teacher_actions_executed': 0})
    assert len(label_only) == 2  # unchanged gate still rejects both takeover rows
    accepted, report = prepare_takeover_step(obs, labels, contract=FakeContract, audit=audit)
    assert len(accepted) == 4
    assert [row['takeover'] for row in accepted] == [False, False, True, True]
    assert report['takeover_rows'] == 2 and report['label_only_rows'] == 2
    assert report['teacher_actions_executed'] == 2
    assert np.all(accepted[3]['action'][0] == 4)
    assert accepted[3]['action_is_pad'].tolist() == [False]+[True]*7


def test_label_only_default_keeps_its_signature_and_rejections():
    assert 'takeover' not in inspect.signature(prepare_single_step).parameters
    obs, labels, audit = _admission_fixture()
    labels[2].update(teacher_phase='hold', phase_after='lower')
    labels[3]['phase_after'] = 'failed'
    accepted, report = prepare_single_step(obs, labels, contract=FakeContract, audit=audit)
    assert len(accepted) == 2
    assert sum(row['count'] for row in report['rejections']) == 2
    assert report['teacher_actions_executed'] == 0
    with pytest.raises(ValueError):
        prepare_single_step(obs, labels, contract=FakeContract,
                            audit={**audit, 'teacher_actions_executed': 1})


def test_takeover_rows_must_be_a_final_contiguous_suffix():
    obs, labels, audit = _admission_fixture()
    _takeover_rows(obs, labels)
    labels[3]['takeover'] = False
    with pytest.raises(ValueError, match='final contiguous suffix'):
        prepare_takeover_step(obs, labels, contract=FakeContract,
                              audit={**audit, 'teacher_actions_executed': 1})


def test_takeover_execution_count_must_match_rows():
    obs, labels, audit = _admission_fixture()
    _takeover_rows(obs, labels)
    with pytest.raises(ValueError, match='execution count'):
        prepare_takeover_step(obs, labels, contract=FakeContract, audit=audit)


def test_takeover_completion_is_evidence_not_a_done_target():
    obs, labels, audit = _admission_fixture()
    _takeover_rows(obs, labels)
    labels[3]['done'] = True
    accepted, report = prepare_takeover_step(obs, labels, contract=FakeContract,
                                             audit={**audit, 'teacher_actions_executed': 2})
    assert len(accepted) == 4
    assert np.all(accepted[3]['action'][1:] == 0)  # done target never injected
    assert report['valid_horizons_per_sample'] == 1


# ------------------------------------------- frozen teacher (optional host)
#
# The frozen snapshot ships its own ``scripts`` package while this worktree's
# module lives in ``scripts/act18_takeover.py``; importing both in one process
# would bind ``scripts`` to one of them.  Run the pure-Python teacher check in a
# child with the snapshot first on PYTHONPATH (the production import order) and
# keep the assertions here.

_FROZEN_RUNNER = r"""
import copy
import json
from act18_takeover import takeover_teacher
from sim.grasp_act_solo_teacher import cargo, primitives


def run(hold_s, offset=False):
    ops = primitives()
    ops.gaze = lambda target, previous, **_: dict(previous)
    spec = cargo('cyan')
    pwm = {1: 1502, 3: 1600, 4: 1900, 5: 2000, 6: 1200}
    command = dict(t=0., wheels=[0.]*4, duration_s=[0.]*4,
                   pwm={str(k): v for k, v in pwm.items()})
    takeover = takeover_teacher({'kind': 'cyan', 'role': 'west'}, command, now=0.,
                                hold_s=hold_s, ops=ops)
    phases, drove, ticks, done = set(), False, 0, False
    for i in range(900):
        now = i*.1
        x = ops.station + (.20 if offset and i < 25 else 0.)
        measurement = None if takeover.teacher.holding else {
            'xyz': [x, 0., spec.grip_z_m], 'yaw': 0.}
        value, done = takeover.step(now, measurement=copy.deepcopy(measurement),
                                    rgb_holding='yes')
        drove |= any(abs(w) > 1e-9 for w in value['wheels'])
        phases.add(takeover.teacher.phase)
        ticks = i+1
        if done:
            break
    return dict(hold_s=hold_s, offset=offset, done=done,
                result=takeover.teacher.result, ticks=ticks,
                hold_ticks=takeover.hold_ticks, phases=sorted(phases),
                drove=drove, shift=takeover.phase_t_shift_s)


print(json.dumps({'runs': [run(3.0), run(2.0), run(2.0, True)]}))
"""


@pytest.fixture(scope='module')
def frozen_runs(tmp_path_factory):
    if SOLO_SOURCE is None:
        pytest.skip('frozen solo-teacher source snapshot not available on this host')
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([SOLO_SOURCE, str(ROOT/'scripts')])
    proc = subprocess.run([sys.executable, '-c', _FROZEN_RUNNER],
                          cwd=str(tmp_path_factory.mktemp('takeover')),
                          env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-6000:]
    return json.loads(proc.stdout)['runs']


@requires_teacher
def test_frozen_teacher_takeover_from_nonzero_pose_reaches_command_complete(frozen_runs):
    run = frozen_runs[0]
    assert run['done'] is True and run['result'] == 'command_complete'
    assert {'close', 'lift', 'hold', 'lower', 'open', 'complete'} <= set(run['phases'])
    assert run['hold_ticks'] == 30
    assert run['ticks'] > 30


@requires_teacher
def test_frozen_teacher_hold_two_seconds_completes_ten_ticks_earlier(frozen_runs):
    run3, run2 = frozen_runs[0], frozen_runs[1]
    assert run3['done'] is True and run2['done'] is True
    assert run2['result'] == 'command_complete'
    assert run2['hold_ticks'] == 20
    assert run3['ticks']-run2['ticks'] == 10
    assert run2['shift'] == 1.0
    assert {'close', 'lift', 'hold', 'lower', 'open', 'complete'} <= set(run2['phases'])


@requires_teacher
def test_frozen_teacher_takeover_with_offset_target_drives_and_completes(frozen_runs):
    run = frozen_runs[2]
    assert run['drove'] is True, 'teacher never drove toward the 0.20 m offset target'
    assert run['done'] is True and run['result'] == 'command_complete'
    assert {'close', 'lift', 'hold', 'lower', 'open'} <= set(run['phases'])
