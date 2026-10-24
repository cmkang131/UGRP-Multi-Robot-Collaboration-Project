"""Solo student controller and isolated worker with fakes (derived, unverified; no checkpoint, no physics)."""
import base64
import json

import pytest

from harness import grasp_act_contract as c
from harness import pairact_solo_student as student
from harness import solo_carry_contract as sc
from scripts import pairact_solo_student_worker as worker

PWM = {'1': 1500, '3': 1200, '4': 1800, '5': 1500, '6': 1500}
INITIAL = {'t': 0., 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': PWM}


class FakeExecutor:
    stage = 'approach'

    def __init__(self, predict):
        self.seen, self.discarded = [], 0
        self.done_from = None
        self.cut = None

    def step(self, observation, jpegs):
        self.seen.append((observation, list(jpegs)))
        done = self.done_from is not None and observation['t'] >= self.done_from
        if self.cut is not None and observation['skill'] == 'release':
            done = observation['t'] >= self.cut
        return {'t': observation['t'], 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': dict(PWM)}, done

    def discard_pending(self):
        self.discarded += 1


class FakeBarrier:
    def __init__(self):
        self.pending, self.ready, self.blocked, self.events = None, False, False, []

    def propose(self, value, done, previous, *, stage=None):
        pass

    def issue(self, now, previous, proposal, done, permit):
        return dict(proposal, t=now), done


def make(done_from=None, pending_until=0.):
    ex, bar = FakeExecutor(None), FakeBarrier()
    ex.done_from = done_from
    bar.pending = object() if pending_until else None
    controller = student.SoloStudentController(None, 'ep', INITIAL, executor_factory=lambda p: ex,
                                               barrier_factory=lambda: bar)
    return controller, ex, bar


def tick(controller, i, permit=True):
    now = round(i*.1, 6)
    proposed = controller.propose(now, {'r1': {'jpeg': f'j{i}'.encode(), 'issued': INITIAL}})
    issued = controller.issue(now, {'r1': permit})
    return proposed['r1']['observation'], issued['r1']


def test_instruction_sequence_wait_grasp_release_and_finish():
    controller, ex, bar = make(done_from=2.)
    bar.pending = object()
    tuples = []
    for i in range(160):
        if i == 5:
            bar.pending = None
        obs, issued = tick(controller, i, permit=i >= 5)
        tuples.append(sc.row_tuple(obs))
        if controller.finished:
            break
    assert tuples[0] == ('wait', 'cyan', 'west', 'none') and tuples[5] == ('grasp', 'cyan', 'west', 'none')
    assert tuples[-1] == ('release', 'cyan', 'west', 'B')
    # release instruction after the own done flag has been continuously true for 3 s
    assert controller.switch_t == pytest.approx(2. + student.RELEASE_AFTER_S, abs=.11)
    assert controller.finished and controller.summary()['truth_inputs'] == 0 and controller.summary()['teacher_actions'] == 0
    assert controller.summary()['status'] == sc.STATUS
    for observation, jpegs in ex.seen:
        sc.validate_solo_observation(observation)
        assert len(jpegs) == c.RGB_HISTORY and all(isinstance(j, bytes) for j in jpegs)
        assert set(observation) == c.FIELDS


def test_done_flag_must_be_continuous():
    controller, ex, _ = make()
    ex.done_from = 0.
    for i in range(20):
        ex.done_from = 0. if i < 20 else None
        tick(controller, i)
    assert controller.segment == 'grasp'                                   # only 2 s of done so far
    ex.done_from = None                                                     # done flag drops
    tick(controller, 20)
    assert controller.done_since is None
    ex.done_from = 0.
    for i in range(21, 21 + 28):
        tick(controller, i)
    assert controller.segment == 'grasp'                                   # the 3 s clock restarted at the drop


def test_request_allowlist_is_jpeg_and_issued_only():
    controller, _, _ = make()
    for bad in ({'jpeg': b'x'}, {'jpeg': b'x', 'issued': INITIAL, 'gt_pose': [0, 0, 0]},
                {'jpeg': b'x', 'issued': INITIAL, 'teacher_phase': 'pick'}):
        with pytest.raises(ValueError, match='own camera'):
            controller.propose(0., {'r1': bad})
    with pytest.raises(ValueError):
        controller.propose(0., {'r2': {'jpeg': b'x', 'issued': INITIAL}})
    controller.propose(0., {'r1': {'jpeg': b'x', 'issued': INITIAL}})
    with pytest.raises(ValueError, match='protocol permits'):
        controller.issue(0., {'r1': 1})
    with pytest.raises(ValueError):
        student.OwnInputs('r2', 'ep', INITIAL)


def run_worker(lines, **kw):
    out = []
    ex, bar = FakeExecutor(None), FakeBarrier()
    worker.serve(None, [json.dumps(x) for x in lines], out.append, config={'issued_clock_deadband': 2},
                 executor_factory=lambda p: ex, barrier_factory=lambda: bar, **kw)
    return [json.loads(x) for x in out]


def test_worker_round_trip():
    jpeg = base64.b64encode(b'jpeg-0').decode()
    out = run_worker([
        {'op': 'reset', 'robot_id': 'r1', 'episode_id': 'ep', 'initial': INITIAL},
        {'op': 'propose', 't': 0., 'robots': {'r1': {'jpeg': jpeg, 'issued': INITIAL}}},
        {'op': 'issue', 't': 0., 'permits': {'r1': True}},
        {'op': 'summary'}])
    assert out[0] == {'ok': True}
    assert sc.row_tuple(out[1]['robots']['r1']['observation']) == ('grasp', 'cyan', 'west', 'none')
    assert out[2]['finished'] is False and out[2]['robots']['r1']['segment'] == 'grasp'
    assert out[3]['mode'] == student.MODE


@pytest.mark.parametrize('lines', [
    [{'op': 'launch'}],
    [{'op': 'reset', 'robot_id': 'r1', 'episode_id': 'ep', 'initial': INITIAL, 'truth': {}}],
    [{'op': 'reset', 'robot_id': 'r1', 'episode_id': 'ep'}],
    [{'op': 'propose', 't': 0., 'robots': {}}],
    [{'op': 'reset', 'robot_id': 'r2', 'episode_id': 'ep', 'initial': INITIAL}],
    [{'op': 'reset', 'robot_id': 'r1', 'episode_id': 'ep', 'initial': INITIAL},
     {'op': 'propose', 't': 0., 'robots': {'r1': {'jpeg': 'eA==', 'issued': INITIAL, 'gt': [0, 0]}}}],
    [{'op': 'reset', 'robot_id': 'r1', 'episode_id': 'ep', 'initial': INITIAL},
     {'op': 'propose', 't': 0., 'robots': {'r1': {'jpeg': 'eA=='}}}],
    [{'op': 'reset', 'robot_id': 'r1', 'episode_id': 'ep', 'initial': INITIAL},
     {'op': 'issue', 't': 0., 'permits': {'r1': True}}],
])
def test_worker_rejects_anything_outside_the_allowlist(lines):
    with pytest.raises((ValueError, KeyError, AttributeError, TypeError)):
        run_worker(lines)


def test_worker_and_student_import_no_simulator_or_teacher():
    import ast
    import harness.pairact_solo_student as module
    for path in (module.__file__, worker.__file__):
        imported = set()
        for node in ast.walk(ast.parse(open(path).read())):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        for name in imported:
            assert not name.startswith(('sim', 'mujoco', 'scripts.run_', 'harness.solo_carry_teacher',
                                        'harness.solo_carry_eval', 'harness.solo_carry_visible',
                                        'harness.grasp_act_teacher', 'harness.pair_carry_teacher')), name
