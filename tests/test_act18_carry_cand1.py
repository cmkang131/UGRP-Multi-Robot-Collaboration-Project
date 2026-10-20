"""carry-cand-1 (A-c1): issued-command deadband 10, evaluation side, default off."""
import io
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import act18_evaluate as e
from harness import grasp_act_contract as c
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_rollout import OwnHistory


def jpeg():
    stream = io.BytesIO()
    Image.new('RGB', (64, 48), 'red').save(stream, 'JPEG')
    return stream.getvalue()


def row(pwm1, *, others=None, wheel=0.):
    """One raw ACT output row decoding to the given PWMs (and an optional wheel)."""
    values = np.zeros(c.ACTION_DIM)
    values[0] = wheel
    values[4] = .5 if wheel else 0.
    pwms = dict({1: pwm1}, **(others or {}))
    for index, servo in enumerate(c.SERVOS):
        values[8 + index] = (pwms.get(servo, 1500) - 1500) / 1000.
    values[-1] = .0
    return values


def rollout(executor_class, targets, *, wheel=0.):
    """Owner simulation: the sent command is appended to the own issued history."""
    initial = {'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
               'pwm': {str(s): 1500 for s in c.SERVOS}}
    history = OwnHistory('r1', 'synthetic-cand1', initial)
    state = {'tick': 0}
    executor = executor_class(lambda obs, jpgs: [row(targets[state['tick']], wheel=wheel)] * c.CHUNK)
    sent, seen = [], []
    for tick in range(len(targets)):
        state['tick'] = tick
        now = round(.1 * (tick + 1), 6)
        obs, jpgs, _ = history.observe(now, jpeg(), skill='release', object_kind='cyan',
                                       role='west', destination_zone='B')
        seen.append(obs)
        value, _ = executor.step(obs, jpgs)
        history.issue(value)
        sent.append(value)
    return sent, seen


def test_command_deadband_holds_small_moves_per_servo_only():
    previous = {'1': 1500, '3': 700, '4': 1800, '5': 2200, '6': 1500}
    value = {'t': 1., 'wheels': [.35, 0., 0., 0.], 'duration_s': [.1, 0., 0., 0.],
             'pwm': {'1': 1506, '3': 690, '4': 1791, '5': 2220, '6': 1500}}
    held = e.command_deadband(value, previous, 10)
    # |Δ| 6 and 9 held; |Δ| 10 and 20 pass (strict < band).
    assert held['pwm'] == {'1': 1500, '3': 690, '4': 1800, '5': 2220, '6': 1500}
    assert held['wheels'] == value['wheels'] and held['duration_s'] == value['duration_s']
    assert held['t'] == value['t']
    assert value['pwm']['1'] == 1506  # input not mutated
    assert e.command_deadband(value, previous, 0) is value
    c.command(held)


def test_flag_off_is_the_unchanged_te1_executor():
    targets = [1500, 1503, 1497, 1506, 1530, 1534, 2009, 2005]
    base = e.candidate_executor(ChunkExecutor)
    sent_off, _ = rollout(base, targets)

    class Legacy(ChunkExecutor):
        def __init__(self, predict):
            super().__init__(predict, n_action_steps=1, temporal_ensemble_coeff=.01)
    sent_legacy, _ = rollout(Legacy, targets)
    assert sent_off == sent_legacy


def test_deadband_reaches_issued_command_and_observed_history():
    # predict ignores the observation, so the TE output is the same with and without
    # the deadband; the deadband must then be the only difference in what is sent.
    targets = [1503, 1497, 1506, 1501, 1530, 1534] + [2009, 2005, 2013, 2009, 2011] * 3
    off, _ = rollout(e.candidate_executor(ChunkExecutor), targets, wheel=.35)
    executor = e.candidate_executor(ChunkExecutor, command_deadband_pwm=10)
    sent, seen = rollout(executor, targets, wheel=.35)
    previous, expected = 1500, []
    for value in off:
        new = value['pwm']['1']
        previous = previous if abs(new - previous) < 10 else new
        expected.append(previous)
    pwm1 = [value['pwm']['1'] for value in sent]
    assert pwm1 == expected
    raw = [value['pwm']['1'] for value in off]
    assert raw[:4] != [1500] * 4 and pwm1[:4] == [1500] * 4   # ±1–6 dither never issued
    assert max(pwm1) >= 1900                                   # the open step still passes
    assert len(set(pwm1)) < len(set(raw))
    # The owner-side history the policy sees next tick carries the same values.
    for tick in range(1, len(targets)):
        assert seen[tick]['issued'][-1]['pwm'] == sent[tick - 1]['pwm']
        assert seen[tick]['issued'][-2]['pwm'] == (sent[tick - 2]['pwm'] if tick >= 2 else
                                                   {str(s): 1500 for s in c.SERVOS})
    # Wheels are not a deadband target.
    assert [value['wheels'] for value in off] == [value['wheels'] for value in sent]
    assert all(value['wheels'][0] != 0. for value in sent)


def test_only_registered_band_is_accepted():
    with pytest.raises(ValueError):
        e.candidate_executor(ChunkExecutor, command_deadband_pwm=5)
    receipt = e.command_deadband_receipt(0)
    assert receipt['candidate'] is None and receipt['flag'] == '--issued-command-deadband 0'
