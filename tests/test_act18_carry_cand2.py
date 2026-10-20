"""carry-cand-2 (A-c2): one-shot own-history reset at release entry, default off."""
import copy
import io
from pathlib import Path
import sys

import numpy as np
from PIL import Image

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


def row(pwm1):
    values = np.zeros(c.ACTION_DIM)
    values[8] = (pwm1 - 1500) / 1000.
    return values


def rollout(executor_class, grasp_ticks=20, release_ticks=20):
    """Owner simulation with grasp dither then release; records policy-visible inputs."""
    initial = {'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
               'pwm': {str(s): 1500 for s in c.SERVOS}}
    history = OwnHistory('r1', 'synthetic-cand2', initial)
    seen_by_policy, owner_obs, sent = [], [], []
    dither = [1503, 1497, 1506, 1501, 1499, 1504]

    def predict(obs, jpgs):
        seen_by_policy.append(copy.deepcopy(obs))
        return [row(dither[len(seen_by_policy) % len(dither)])] * c.CHUNK
    executor = executor_class(predict)
    for tick in range(grasp_ticks + release_ticks):
        skill = 'grasp' if tick < grasp_ticks else 'release'
        if tick == grasp_ticks:
            executor.reset()  # evaluate_act16w resets the executor on instruct
        now = round(.1 * (tick + 1), 6)
        obs, jpgs, _ = history.observe(now, jpeg(), skill=skill, object_kind='cyan',
                                       role='west', destination_zone='B')
        owner_obs.append(copy.deepcopy(obs))
        value, _ = executor.step(obs, jpgs)
        history.issue(value)
        sent.append(value)
    return seen_by_policy, owner_obs, sent


def test_flag_off_is_the_unchanged_te1_executor():
    class Legacy(ChunkExecutor):
        def __init__(self, predict):
            super().__init__(predict, n_action_steps=1, temporal_ensemble_coeff=.01)
    off = rollout(e.candidate_executor(ChunkExecutor))
    legacy = rollout(Legacy)
    assert off == legacy
    assert off[0] == off[1]  # policy saw exactly the owner observation


def test_release_entry_fills_history_once_with_own_last_command():
    seen, owner, _ = rollout(e.candidate_executor(ChunkExecutor, release_history_reset=True))
    entry = 20
    # Grasp ticks are untouched.
    assert seen[:entry] == owner[:entry]
    template = owner[entry]['issued'][-1]
    first = seen[entry]['issued']
    assert [item['t'] for item in first] == [item['t'] for item in owner[entry]['issued']]
    assert all(item['pwm'] == template['pwm'] and item['wheels'] == template['wheels']
               and item['duration_s'] == template['duration_s'] for item in first)
    assert len({item['pwm']['1'] for item in owner[entry]['issued']}) > 1  # dither was there
    # Later ticks: newly issued commands append normally; synthetic part shifts out.
    for k in range(1, c.HISTORY + 2):
        policy, real = seen[entry + k]['issued'], owner[entry + k]['issued']
        synthetic = max(0, c.HISTORY - k)
        assert all(item['pwm'] == template['pwm'] for item in policy[:synthetic])
        assert policy[synthetic:] == real[synthetic:]
    assert seen[entry + c.HISTORY] == owner[entry + c.HISTORY]
    # Every other field is the owner value.
    for a, b in zip(seen[entry:], owner[entry:]):
        assert {k: v for k, v in a.items() if k != 'issued'} == {k: v for k, v in b.items() if k != 'issued'}
        c.validate_observation(a)


def test_reset_uses_only_own_issued_history():
    reset = e.ReleaseHistoryReset()
    initial = {'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
               'pwm': {str(s): 1500 for s in c.SERVOS}}
    history = OwnHistory('r1', 'own-only', initial)
    for tick in range(5):
        history.issue(dict(initial, t=.1 * (tick + 1), pwm={**initial['pwm'], '1': 1500 + tick}))
    obs, _, _ = history.observe(.6, jpeg(), skill='release', object_kind='cyan', role='west',
                                destination_zone='B')
    out = reset.apply(obs)
    # Changing every non-history field leaves the produced history unchanged.
    other = dict(obs, rgb=[dict(r, sha256='f' * 64) for r in obs['rgb']], object_kind='yellow',
                 skill_elapsed_s=99., pwm_elapsed_s=42., sample_id='x:0:r1')
    out_other = e.ReleaseHistoryReset().apply(other)
    assert out_other['issued'] == out['issued']
    # The values come from this robot's own last issued command only.
    produced = {(tuple(i['wheels']), tuple(i['duration_s']), tuple(sorted(i['pwm'].items())))
                for i in out['issued']}
    last = obs['issued'][-1]
    assert produced == {(tuple(last['wheels']), tuple(last['duration_s']),
                         tuple(sorted(last['pwm'].items())))}
    assert obs['issued'][0]['pwm']['1'] == 1500 and obs['issued'][-1]['pwm']['1'] == 1504  # input not mutated
    # Non-release skills pass through unchanged and clear the state.
    grasp = dict(obs, skill='grasp')
    assert reset.apply(grasp) is grasp and reset.template is None
    receipt = e.history_reset_receipt(False)
    assert receipt['candidate'] is None and receipt['flag'] == '--release-history-reset off'
