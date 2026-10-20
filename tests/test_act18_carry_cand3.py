"""carry-cand-3 (A-c3): release-only latest4 executor, grasp stays te1, default off."""
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


def chunk(base):
    rows = []
    for index in range(c.CHUNK):
        values = np.zeros(c.ACTION_DIM)
        values[8] = (base + 10 * index - 1500) / 1000.
        rows.append(values)
    return rows


def rollout(executor_class, grasp_ticks=12, release_ticks=12, open_from=None):
    initial = {'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
               'pwm': {str(s): 1500 for s in c.SERVOS}}
    history = OwnHistory('r1', 'synthetic-cand3', initial)
    state = {'tick': 0, 'calls': []}

    def predict(obs, jpgs):
        state['calls'].append(state['tick'])
        tick = state['tick']
        base = 2009 if open_from is not None and tick >= open_from else 1500 + 3 * tick
        return chunk(base)
    executor = executor_class(predict)
    sent = []
    for tick in range(grasp_ticks + release_ticks):
        state['tick'] = tick
        skill = 'grasp' if tick < grasp_ticks else 'release'
        if tick == grasp_ticks:
            executor.reset()
        obs, jpgs, _ = history.observe(round(.1 * (tick + 1), 6), jpeg(), skill=skill,
                                       object_kind='cyan', role='west', destination_zone='B')
        value, _ = executor.step(obs, jpgs)
        history.issue(value)
        sent.append(value['pwm']['1'])
    return sent, state['calls']


class Legacy(ChunkExecutor):
    def __init__(self, predict):
        super().__init__(predict, n_action_steps=1, temporal_ensemble_coeff=.01)


def test_flag_off_is_the_unchanged_te1_executor():
    assert rollout(e.candidate_executor(ChunkExecutor)) == rollout(Legacy)


def test_latest4_only_in_release_grasp_stays_te1():
    sent, calls = rollout(e.candidate_executor(ChunkExecutor, release_executor='latest4'))
    legacy, legacy_calls = rollout(Legacy)
    assert sent[:12] == legacy[:12]              # grasp identical to te1
    assert calls[:12] == list(range(12))         # te1 predicts every tick
    assert calls[12:] == [12, 16, 20]            # release: new chunk every 4 ticks
    # Release commands are the latest chunk's rows in order, unweighted.
    for tick in range(12, 24):
        start = 12 + 4 * ((tick - 12) // 4)
        assert sent[tick] == 1500 + 3 * start + 10 * (tick - start)


def test_latest4_issues_open_without_ensemble_dilution():
    te, _ = rollout(Legacy, open_from=14)
    l4, _ = rollout(e.candidate_executor(ChunkExecutor, release_executor='latest4'), open_from=14)
    assert l4[16] >= 1900                         # first chunk taken after the open prediction
    assert te[16] < 1900                          # te1 still averaging older chunks
    first = lambda xs: next(i for i, v in enumerate(xs) if v >= 1900)
    assert first(l4) < first(te)


def test_registered_modes_only():
    assert e.executor_params('grasp', 'latest4') == (1, .01)
    assert e.executor_params('release', 'latest4') == (4, None)
    assert e.executor_params('release', 'te1') == (1, .01)
    with pytest.raises(ValueError):
        e.candidate_executor(ChunkExecutor, release_executor='latest8')
    receipt = e.release_executor_receipt('te1')
    assert receipt['candidate'] is None and receipt['flag'] == '--release-executor te1'
