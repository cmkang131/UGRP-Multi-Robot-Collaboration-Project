import copy
import io

import numpy as np
import pytest
from PIL import Image

from harness import grasp_act_contract as c
from harness.grasp_act_data import INPUT_KEYS, fit_stats, history_image
from harness.grasp_act_policy import ChunkExecutor, observation_batch
from harness.grasp_act_rollout import OwnHistory, LiftScore, InputAudit


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
