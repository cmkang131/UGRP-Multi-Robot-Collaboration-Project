import copy
import io

import numpy as np
import pytest
from PIL import Image

from harness import grasp_act_contract as c
from harness.grasp_act_data import INPUT_KEYS, fit_stats, history_image
from harness.grasp_act_policy import ChunkExecutor, observation_batch
from harness.grasp_act_rollout import OwnHistory, LiftScore, InputAudit, SoloSequence, SoloScore


def inputs():
    command = {'t': 1., 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
               'pwm': {str(s): 1500 for s in c.SERVOS}}
    image = io.BytesIO(); Image.new('RGB', (640, 480), 'red').save(image, 'JPEG')
    h = OwnHistory('r2', 'ep', command)
    obs, jpgs, _ = h.observe(1., image.getvalue(), skill='grasp', object_kind='heavy_crate', role='east')
    return h, obs, jpgs


def test_inference_same_preprocessing_and_no_ids():
    _, obs, jpgs = inputs()
    stats = fit_stats([c.context(obs)], [c.encode_action(obs['issued'][-1])], [1])
    batch = observation_batch(obs, jpgs, stats)
    assert set(batch) == INPUT_KEYS
    assert batch['observation.state'].shape == (c.CONTEXT_DIM,)
    altered = copy.deepcopy(obs); altered['sample_id'] = 'different:999:r2'
    again = observation_batch(altered, jpgs, stats)
    assert all(np.array_equal(v, again[k]) for k, v in batch.items())
    with pytest.raises(ValueError, match='hash'):
        observation_batch(obs, [b'bad'] * 4, stats)


def test_history_order_has_distinct_spatial_positions():
    frames = [np.full((3, 240, 320), i * 60, np.uint8) for i in range(4)]
    image = history_image(frames)
    assert image.shape == (3, 480, 640)
    assert image[0, 0, 0] < image[0, 0, 320] < image[0, 240, 0] < image[0, 240, 320]
    assert not np.array_equal(image, history_image(frames[::-1]))
    assert np.array_equal(history_image(frames, blank=True), history_image(frames[::-1], blank=True))


def test_executor_chunk_clock_and_task_reset():
    history, obs, jpgs = inputs()
    calls = []
    def predict(o, j):
        calls.append(o['skill'])
        return [[.35] * 4 + [.5] * 4 + [0.] * 5 + [0.]] * 8
    executor = ChunkExecutor(predict)
    for i in range(9):
        obs['t'] = 1. + i*.1
        for ref in obs['rgb']:
            ref['t'] = obs['t']
        action, done = executor.step(obs, jpgs)
        assert not done and action['wheels'] == [.35] * 4
        assert action['duration_s'] == [.075] * 4
    assert len(calls) == 2
    obs['skill'] = 'release'; obs['destination_zone'] = 'B'; obs['t'] += .1
    executor.step(obs, jpgs)
    assert calls[-1] == 'release' and len(calls) == 3
    action, _ = executor.step(obs, jpgs, interrupt=True)
    assert action['wheels'] == [0.] * 4 and len(calls) == 3


def test_executor_refuses_future_truth_before_prediction():
    _, obs, jpgs = inputs()
    executor = ChunkExecutor(lambda *args: pytest.fail('must not call model'))
    obs['contact'] = True
    with pytest.raises(ValueError, match='whitelist'):
        executor.step(obs, jpgs)
    audit = InputAudit()
    with pytest.raises(ValueError):
        audit.accept(obs)
    assert audit.record['forbidden_input_fields'] == 1


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_output_fails_without_fallback(bad):
    _, obs, jpgs = inputs()
    executor = ChunkExecutor(lambda *args: [[bad] * 14] * 8)
    with pytest.raises(ValueError, match='invalid action'):
        executor.step(obs, jpgs)


def test_done_drops_remaining_chunk_and_holds():
    _, obs, jpgs = inputs()
    calls = []
    def predict(*args):
        calls.append(1)
        return [[.4] * 4 + [1.] * 4 + [.1] * 5 + [.9]] * 8
    executor = ChunkExecutor(predict)
    action, done = executor.step(obs, jpgs)
    assert done and action['wheels'] == [0.] * 4 and not executor.pending
    obs['issued'][-1] = action; obs['t'] += .1
    action2, done2 = executor.step(obs, jpgs)
    assert done2 and action2['pwm'] == action['pwm'] and len(calls) == 1


def test_history_is_self_issued_and_score_is_evaluation_only():
    history, obs, jpgs = inputs()
    command = dict(obs['issued'][-1], t=1.05)
    history.issue(command)
    next_obs, _, _ = history.observe(1.1, jpgs[0], skill='grasp', object_kind='heavy_crate', role='east')
    assert next_obs['issued'][-1]['t'] == 1.05
    score = LiftScore()
    for i in range(31):
        score.add(i*.1, clearance=.02, tilt=1., forces=[1., 1.], weld=False)
    assert score.record()['lift_success']
    assert 'lift_success' not in next_obs
    with pytest.raises(ValueError, match='WELD'):
        score.add(3.1, clearance=.02, tilt=1., forces=[1., 1.], weld=True)


def test_solo_sequence_switches_on_student_done_and_clock_only():
    sequence = SoloSequence(with_release=True)
    assert not sequence.update(10., False) and sequence.skill == 'grasp'
    assert not sequence.update(10.1, True)
    assert not sequence.update(13.1, True) and sequence.skill == 'grasp'
    assert not sequence.update(13.2, True) and sequence.skill == 'release'
    assert not sequence.update(20., False)
    assert not sequence.update(20.1, True)
    assert sequence.update(23.2, True)
    assert sequence.done_times == {'grasp': 10.1, 'release': 20.1}


@pytest.mark.parametrize('bad_release', ['airborne', 'finger_loaded', 'moving', 'tilted', None])
def test_solo_score_requires_lift_then_stable_released_setdown(bad_release):
    score = SoloScore()
    for i in range(32):
        score.add(i*.1, skill='grasp', clearance=.02, tilt=1., forces=[1., 1.], linear_speed=0., weld=False)
    release = dict(clearance=0., tilt=1., forces=[0., 0.], linear_speed=0., weld=False)
    if bad_release == 'airborne': release['clearance'] = .02
    if bad_release == 'finger_loaded': release['forces'] = [1., 0.]
    if bad_release == 'moving': release['linear_speed'] = .1
    if bad_release == 'tilted': release['tilt'] = 20.
    for i in range(32, 64):
        score.add(i*.1, skill='release', **release)
    result = score.record({'grasp': 0., 'release': 3.2}, with_release=True)
    assert result['lift_success']
    assert result['physical_success'] == (bad_release is None)
    expected = None if bad_release is None else 'drop_detected' if bad_release == 'airborne' else 'release_not_stable'
    assert result['failure_reason'] == expected


def test_observed_airborne_drop_cannot_be_cleared_by_later_stable_grounding():
    score = SoloScore()
    for i in range(32):
        score.add(i*.1, skill='grasp', clearance=.02, tilt=1., forces=[1., 1.], linear_speed=0., weld=False)
    score.add(3.2, skill='release', clearance=.02, tilt=1., forces=[0., 0.], linear_speed=.1, weld=False)
    for i in range(33, 66):
        score.add(i*.1, skill='release', clearance=0., tilt=1., forces=[0., 0.], linear_speed=0., weld=False)
    result = score.record({'grasp': 0., 'release': 3.2}, with_release=True)
    assert not result['physical_success'] and result['failure_reason'] == 'drop_detected'


def test_grounded_without_lift_and_lift_during_release_are_not_success():
    score = SoloScore()
    for i in range(32):
        score.add(i*.1, skill='grasp', clearance=0., tilt=1., forces=[0., 0.], linear_speed=0., weld=False)
    for i in range(32, 64):
        score.add(i*.1, skill='release', clearance=.02, tilt=1., forces=[1., 1.], linear_speed=0., weld=False)
    for i in range(64, 96):
        score.add(i*.1, skill='release', clearance=0., tilt=1., forces=[0., 0.], linear_speed=0., weld=False)
    result = score.record({'grasp': 0., 'release': 3.2}, with_release=True)
    assert not result['physical_success'] and not result['release_success']
    assert result['failure_reason'] == 'lift_not_stable'
