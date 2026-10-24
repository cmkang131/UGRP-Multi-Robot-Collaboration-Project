"""Train/deploy consistency of the solo task tuple (derived, unverified; CPU only, no physics).

The recorder must record, and the deploy student must build, the identical
``(skill, object_kind, role, destination_zone)`` tuple -- and the identical own clocks --
for the same phase sequence.
"""
import json
from collections import deque

import pytest

from harness import grasp_act_contract as c
from harness import pairact_solo_student as student
from harness import solo_carry_contract as sc
from harness import solo_carry_recorder as rec

EPISODE = 'solo-ep-0'
PWM0 = {'1': 1500, '3': 1200, '4': 1800, '5': 1500, '6': 1500}


def cmd(t, pwm):
    return {'t': float(t), 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': dict(pwm)}


def pwm_at(i):
    """Servo jitter inside the deadband (+-2) early, a real move at tick 30, another at tick 45."""
    pwm = dict(PWM0)
    if 10 <= i < 20:
        pwm['3'] += 2            # |d| <= 2: must not reset pwm_elapsed_s
    elif i >= 20:
        pwm['3'] += 2 if i < 30 else 40 if i < 45 else 90
    return pwm


def instruction_at(i):
    """wait (own READY pending) -> grasp -> release at tick 40."""
    if i < 8:
        return 'wait', sc.GRASP_DESTINATION
    if i < 40:
        return 'grasp', sc.GRASP_DESTINATION
    return sc.CARRY_SKILL, sc.CARRY_DESTINATION


def runner_grasp_row(i, now, images, history, skill):
    """What the UNCHANGED runner writes in the grasp segment (beam-era fields, its own clock)."""
    return {'schema': c.SCHEMA, 'robot_id': 'r1', 'sample_id': f'{EPISODE}:{i}:r1', 't': now,
            'object_kind': 'long_beam', 'skill': skill, 'role': 'teal',
            'rgb': c.image_history(list(images), now), 'issued': list(history),
            'skill_elapsed_s': 123.0, 'pwm_elapsed_s': 456.0, 'destination_zone': 'none'}


def episode(n=70):
    """Run the recorder side and the deploy-student side over the same inputs; yield both rows."""
    initial = cmd(0., PWM0)
    history = deque([c.command(initial)]*c.HISTORY, maxlen=c.HISTORY)
    images = deque(maxlen=max(c.HISTORY + 1, int(c.MEMORY_S/.1) + 3))
    recorder = rec.SoloRecorder('r1', history=history, images=images, episode_id=EPISODE)
    inputs = student.OwnInputs('r1', EPISODE, initial, deadband=2)
    out = []
    for i in range(n):
        now = round(i*.1, 6)
        jpeg = f'jpeg-{i}'.encode()
        skill, dest = instruction_at(i)
        # recorder side
        ref = recorder.add_frame(i, now, jpeg)
        previous_pwm = history[-1]['pwm']
        if dest == sc.CARRY_DESTINATION:
            recorded = recorder.student_row(i, now, previous_pwm)
        else:
            recorded = recorder.rewrite_grasp_row(runner_grasp_row(i, now, images, history, skill))
        # deploy student side
        deployed, jpegs, path = inputs.observe(now, jpeg, skill=skill, destination_zone=dest)
        assert path == ref['path'] and len(jpegs) == c.RGB_HISTORY
        out.append((recorded, deployed))
        applied = cmd(now, pwm_at(i))
        history.append(c.command(applied))
        inputs.issue(applied)
    return out


def test_recorded_tuple_equals_deployed_tuple_for_the_same_phase_sequence():
    rows = episode()
    expected = [sc.instruction(*instruction_at(i)) for i in range(len(rows))]
    for i, (recorded, deployed) in enumerate(rows):
        assert sc.row_tuple(recorded) == sc.row_tuple(deployed) == expected[i], i
    assert {sc.row_tuple(r) for r, _ in rows} == {
        ('wait', 'cyan', 'west', 'none'), ('grasp', 'cyan', 'west', 'none'), ('release', 'cyan', 'west', 'B')}


def test_recorded_rows_equal_deployed_rows_field_for_field_including_own_clocks():
    for i, (recorded, deployed) in enumerate(episode()):
        assert recorded == deployed, (i, {k: (recorded[k], deployed[k]) for k in recorded if recorded[k] != deployed[k]})


def test_clock_semantics_pwm_elapsed_is_recorded_as_is():
    rows = [r for r, _ in episode()]
    by_tick = {int(r['sample_id'].split(':')[1]): r for r in rows}
    # +-2 PWM jitter does not reset the clock; the +40 move at tick 30 does (applied at 30, seen at 31)
    assert by_tick[25]['pwm_elapsed_s'] == pytest.approx(2.5, abs=1e-6)
    assert by_tick[31]['pwm_elapsed_s'] == pytest.approx(0., abs=1e-6)
    assert by_tick[40]['pwm_elapsed_s'] == pytest.approx(.9, abs=1e-6)
    # the tuple change wait -> grasp at tick 8 and grasp -> release at tick 40 resets skill_elapsed_s
    assert by_tick[8]['skill_elapsed_s'] == 0. and by_tick[40]['skill_elapsed_s'] == 0.
    assert by_tick[39]['skill_elapsed_s'] == pytest.approx(3.1, abs=1e-6)


def test_teacher_private_state_never_reaches_a_recorded_row():
    for recorded, deployed in episode():
        text = json.dumps(recorded)
        for private in ('long_beam', 'teal', 'blue', '123.0', '456.0'):
            assert private not in text
        assert set(recorded) == c.FIELDS
        assert recorded['role'] == 'west' and recorded['object_kind'] == 'cyan'


def test_runner_row_clock_is_discarded_not_trusted():
    initial = cmd(0., PWM0)
    history = deque([c.command(initial)]*c.HISTORY, maxlen=c.HISTORY)
    images = deque(maxlen=54)
    recorder = rec.SoloRecorder('r1', history=history, images=images, episode_id=EPISODE)
    recorder.add_frame(0, 0., b'x')
    row = recorder.rewrite_grasp_row(runner_grasp_row(0, 0., images, history, 'grasp'))
    assert (row['skill_elapsed_s'], row['pwm_elapsed_s']) == (0., 0.)


def test_only_grasp_segment_rows_are_rewritten():
    initial = cmd(0., PWM0)
    history = deque([c.command(initial)]*c.HISTORY, maxlen=c.HISTORY)
    images = deque(maxlen=54)
    recorder = rec.SoloRecorder('r1', history=history, images=images, episode_id=EPISODE)
    recorder.add_frame(0, 0., b'x')
    bad = {**runner_grasp_row(0, 0., images, history, 'release'), 'destination_zone': 'B'}
    with pytest.raises(ValueError):
        recorder.rewrite_grasp_row(bad)


def test_instruction_builder_rejects_inconsistent_tuples():
    with pytest.raises(ValueError):
        sc.instruction('release', 'none')
    with pytest.raises(ValueError):
        sc.instruction('grasp', 'B')
    with pytest.raises(ValueError):
        sc.instruction('regrasp', 'none')


def test_every_recorded_and_deployed_row_is_a_plain_v5_observation_the_loader_can_encode():
    """The box role is the v5 one ('west'): rows go through the UNCHANGED v5 validator and the
    loader's context() encoder (harness/grasp_act.py:56 calls grasp_act_contract.context)."""
    assert c.KIND_ROLES[sc.OBJECT_KIND] == ('west',) and sc.ROLE == 'west' and 'solo' not in c.ROLES
    kind_at, role_at = c.HISTORY*14 + len(c.SKILLS), c.HISTORY*14 + len(c.SKILLS) + len(c.KINDS)
    rows = episode()
    seen = set()
    for recorded, deployed in rows:
        for row in (recorded, deployed):
            assert c.validate_observation(row) is row
            vec = c.context(row)
            assert len(vec) == c.CONTEXT_DIM
            assert vec[kind_at:kind_at + len(c.KINDS)] == [float(k == 'cyan') for k in c.KINDS]
            assert vec[role_at:role_at + len(c.ROLES)] == [float(r == 'west') for r in c.ROLES]
            seen.add(row['skill'])
    assert seen == {'wait', 'grasp', 'release'}


def test_solo_validator_adds_only_the_task_kind_and_role_on_top_of_v5():
    row = episode(3)[0][0]
    assert sc.validate_solo_observation(row) is row
    with pytest.raises(ValueError):
        sc.validate_solo_observation({**row, 'role': 'solo'})                 # not a v5 token
    with pytest.raises(ValueError):
        sc.validate_solo_observation({**row, 'role': 'any', 'object_kind': 'can'})   # cargo v6: no can
    with pytest.raises(ValueError):
        sc.validate_solo_observation({**row, 'role': 'teal', 'object_kind': 'long_beam'})
    with pytest.raises(ValueError):
        sc.validate_solo_observation({**row, 'object_kind': 'red'})           # another box is another task
    with pytest.raises(ValueError):
        c.validate_observation({**row, 'role': 'east'})                       # v5 itself: boxes are 'west' only


def test_writer_wrappers_leave_carry_rows_untouched_and_rewrite_grasp_rows():
    initial = cmd(0., PWM0)
    history = deque([c.command(initial)]*c.HISTORY, maxlen=c.HISTORY)
    images = deque(maxlen=54)
    recorder = rec.SoloRecorder('r1', history=history, images=images, episode_id=EPISODE)
    recorder.add_frame(0, 0., b'x')

    class Sink:
        lines = []

        def write(self, text):
            self.lines.append(text)

    sink = Sink()
    writer = rec.SoloStudentWriter(sink, recorder)
    writer.write(json.dumps(runner_grasp_row(0, 0., images, history, 'grasp')) + '\n')
    assert sc.row_tuple(json.loads(sink.lines[0])) == ('grasp', 'cyan', 'west', 'none')
    label_sink = Sink()
    label_sink.lines = []
    rec.SoloLabelWriter(label_sink).write(json.dumps({'object_kind': 'long_beam', 'skill': 'grasp'}) + '\n')
    assert json.loads(label_sink.lines[0])['object_kind'] == 'cyan'


def test_label_row_shape_and_stage_vocabulary():
    label = rec.carry_label('s', clean={}, applied={}, done=True, phase='retreat',
                            outcome='command_sequence_complete', assignment_source='x')
    assert tuple(label) == rec.LABEL_FIELDS and label['terminal_reason'] == 'command_sequence_complete'
    assert label['segment'] == 'solo_carry_gt' and label['destination_zone'] == 'B'
    with pytest.raises(ValueError):
        rec.carry_label('s', clean={}, applied={}, done=False, phase='no_such_phase', outcome=None,
                        assignment_source='x')
