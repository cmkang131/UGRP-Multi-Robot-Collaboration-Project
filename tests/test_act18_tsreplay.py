"""E1 teacher-state TE replay: parity with ChunkExecutor, clock whitelist, gate."""
from pathlib import Path
from types import SimpleNamespace
import io
import json
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_teacher_state_replay import (TemporalEnsemble, mutate_observation,
                                        require_enabled, window_bounds, world_metrics)
from harness import grasp_act_contract as c
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_rollout import OwnHistory


def observation(now=0.0):
    stream = io.BytesIO()
    Image.new('RGB', (640, 480), 'red').save(stream, 'JPEG')
    initial = {'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
               'pwm': {str(s): 1500 for s in c.SERVOS}}
    history = OwnHistory('r1', 'synthetic-tsreplay', initial)
    obs, jpgs, _ = history.observe(now, stream.getvalue(), skill='grasp',
                                   object_kind='cyan', role='west')
    return obs, jpgs


def chunks(count, *, done_value=0.0):
    rng = np.random.default_rng(20261019)
    out = []
    for _ in range(count):
        chunk = rng.uniform(-.9, .9, size=(c.CHUNK, c.ACTION_DIM))
        chunk[:, -1] = done_value
        out.append(chunk)
    return out


def advance(obs, now):
    obs['t'] = now
    for ref in obs['rgb']:
        ref['t'] = now


def test_temporal_ensemble_matches_chunk_executor_before_done():
    stream = chunks(30)
    cursor = {'i': 0}

    def predict(observation, jpegs):
        chunk = stream[cursor['i']]
        cursor['i'] += 1
        return chunk

    executor = ChunkExecutor(predict, n_action_steps=1, temporal_ensemble_coeff=.01)
    ensemble = TemporalEnsemble(.01)
    obs, jpegs = observation()
    for tick in range(30):
        advance(obs, tick * c.PERIOD_S)
        value, done = executor.step(obs, jpegs)
        action = ensemble.step(stream[tick])
        assert done == action['done']
        assert value['wheels'] == action['wheels']
        assert value['duration_s'] == action['duration_s']
        assert value['pwm'] == action['pwm']
        assert value['t'] == obs['t']
    assert cursor['i'] == 30 and ensemble.ticks == 30


def test_temporal_ensemble_parity_includes_a_done_fire():
    stream = chunks(30)
    for chunk in stream[10:]:
        chunk[:, -1] = 3.0                       # encoded done >.65 -> fires once old zero chunks age out
    cursor = {'i': 0}

    def predict(observation, jpegs):
        chunk = stream[cursor['i']]
        cursor['i'] += 1
        return chunk

    executor = ChunkExecutor(predict, n_action_steps=1, temporal_ensemble_coeff=.01)
    ensemble = TemporalEnsemble(.01)
    obs, jpegs = observation()
    fired = None
    for tick in range(30):
        advance(obs, tick * c.PERIOD_S)
        value, done = executor.step(obs, jpegs)
        action = ensemble.step(stream[tick])
        if done and fired is None:
            fired = tick
            assert action['done'] and value['wheels'] == action['wheels']
        if fired is None:
            assert done == action['done']
            assert value['wheels'] == action['wheels']
            assert value['duration_s'] == action['duration_s']
            assert value['pwm'] == action['pwm']
        else:
            break
    assert fired is not None, 'ensemble did not reproduce the done fire'
    assert fired == 11
    assert ensemble.done_tick == fired
    # Divergence is documented: ChunkExecutor returns zero commands after done,
    # the replay keeps measuring TE outputs for post-fire metrics.
    assert ensemble.step(stream[-1])['done_score'] is not None


def test_temporal_ensemble_rejects_bad_chunk():
    ensemble = TemporalEnsemble()
    with pytest.raises(ValueError, match='invalid 8x14 chunk'):
        ensemble.step(np.zeros((7, c.ACTION_DIM)))
    with pytest.raises(ValueError, match='invalid 8x14 chunk'):
        ensemble.step(np.full((c.CHUNK, c.ACTION_DIM), np.nan))


def test_clock_variants_change_only_whitelisted_fields():
    obs, _ = observation(now=1.7)
    recorded = dict(obs, pwm_elapsed_s=.9, skill_elapsed_s=5.0)
    c.validate_observation(recorded)
    expected = {
        'V0': (.9, 5.0),
        'V1': (.3, 5.0),
        'V2': (.9, 45.0),
        'V3': (.3, 45.0),
    }
    for variant, (pwm, skill) in expected.items():
        mutated = mutate_observation(recorded, variant)
        assert mutated['pwm_elapsed_s'] == pwm
        assert mutated['skill_elapsed_s'] == skill
        # Every other whitelisted field is carried over unchanged.
        left = {k: v for k, v in mutated.items() if k not in ('pwm_elapsed_s', 'skill_elapsed_s')}
        right = {k: v for k, v in recorded.items() if k not in ('pwm_elapsed_s', 'skill_elapsed_s')}
        assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
        c.validate_observation(mutated)
    assert recorded['pwm_elapsed_s'] == .9 and recorded['skill_elapsed_s'] == 5.0
    with pytest.raises(ValueError, match='unknown variant'):
        mutate_observation(recorded, 'V9')


def test_done_low_scores_do_not_fire():
    ensemble = TemporalEnsemble()
    chunk = np.zeros((c.CHUNK, c.ACTION_DIM))
    for _ in range(8):
        action = ensemble.step(chunk)
        assert not action['done']
        # Actor.predict already decoded the chunk into action space, so an
        # encoded zero completion value is zero probability, not a raw logit.
        assert action['done_score'] == 0.0


def test_default_off_gate_and_cli_exit():
    with pytest.raises(SystemExit):
        require_enabled(SimpleNamespace(enabled=False))
    assert require_enabled(SimpleNamespace(enabled=True)) is None
    from act18_teacher_state_replay import main
    with pytest.raises(SystemExit):
        main([])


def teacher_rows():
    phases = ['fold'] * 5 + ['close'] * 5 + ['lift'] * 2 + ['lift_settle'] * 3 + \
             ['lookback_pose'] * 5 + ['hold'] * 5 + ['lookback'] + ['lookback'] * 4 + \
             ['lookback_return'] * 5 + ['lower'] * 5
    return [{'teacher_phase': phase, 'phase_after': phase, 't': index * c.PERIOD_S}
            for index, phase in enumerate(phases)]


def test_window_bounds_follow_preregistered_definition():
    rows = teacher_rows()
    bounds = window_bounds(rows)
    assert bounds['close_tick'] == 5
    assert bounds['lookback_tick'] == 25
    assert bounds['hold_end_tick'] == 24
    lbr = next(i for i, row in enumerate(rows) if row['teacher_phase'] == 'lookback_return')
    end = max(i for i, row in enumerate(rows) if row['t'] <= rows[lbr]['t'] + 1.0 + 1e-9)
    assert bounds['end_tick'] == end
    assert bounds['ticks'] == end - 5 + 1
    assert bounds['lift_settle_ticks'] == [12, 13, 14]


def test_world_metrics_onset_done_and_jitter():
    bounds = {'close_tick': 5, 'end_tick': 40, 'lookback_tick': 20,
              'hold_end_tick': 24, 'lift_settle_ticks': [12, 13, 14], 'ticks': 36}
    rows = []
    for index in range(5, 41):
        pwm = {str(s): 1500 for s in c.SERVOS}
        if index in (12, 13, 14):
            pwm = {str(s): 1500 + (2 * (index - 12)) for s in c.SERVOS}
        done_score = .7 if index == 24 else .1
        rows.append({'index': index, 'teacher_phase': ('lift_settle' if index in (12, 13, 14)
                                                       else 'close'),
                     'te': {'wheels': [-.35] * 4 if index == 25 else [0.] * 4,
                            'duration_s': [.1] * 4, 'pwm': pwm,
                            'done': done_score >= .65, 'done_score': done_score},
                     'onset': index == 25})
    metrics = world_metrics(rows, bounds, 20)
    assert metrics['onset_tick'] == 25
    assert metrics['delta_vs_lookback_ticks'] == 5
    assert metrics['capability_hit'] is True
    assert metrics['done_max_hold_pm10'] == .7
    assert metrics['done_ge_065'] is True
    assert metrics['jitter_pairs_1to3'] == 10   # 2 tick pairs x 5 servos, each step 0 or 2
    assert metrics['jitter_ticks_1to3'] == 2    # both consecutive pairs change by 2
    assert metrics['lift_settle_ticks'] == 3
