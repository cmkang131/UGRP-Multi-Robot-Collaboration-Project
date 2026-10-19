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


def test_v4_requires_preregistered_delta_and_moves_only_pwm_clock():
    obs, _ = observation(now=1.7)
    recorded = dict(obs, pwm_elapsed_s=.9, skill_elapsed_s=5.0)
    c.validate_observation(recorded)
    mutated = mutate_observation(recorded, 'V4', 1.05)
    assert abs(mutated['pwm_elapsed_s'] - 1.95) < 1e-12
    assert mutated['skill_elapsed_s'] == 5.0
    left = {k: v for k, v in mutated.items() if k != 'pwm_elapsed_s'}
    right = {k: v for k, v in recorded.items() if k != 'pwm_elapsed_s'}
    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    c.validate_observation(mutated)
    with pytest.raises(ValueError, match='V4 requires'):
        mutate_observation(recorded, 'V4')
    with pytest.raises(ValueError, match='V4 requires'):
        mutate_observation(recorded, 'V4', -1.)
    assert recorded['pwm_elapsed_s'] == .9


def test_parse_sweep_accepts_preregistered_grid_and_rejects_bad_orders():
    from act18_teacher_state_replay import parse_sweep
    assert parse_sweep('9.0,10.0,10.5') == (9.0, 10.0, 10.5)
    assert parse_sweep('off') == ()
    assert parse_sweep(None) == ()
    with pytest.raises(ValueError, match='strictly increasing'):
        parse_sweep('10.0,9.0')
    with pytest.raises(ValueError, match='strictly increasing'):
        parse_sweep('10.0,10.0')
    with pytest.raises(ValueError, match='empty'):
        parse_sweep(',')


def test_sweep_interval_and_half_max_use_the_fixed_grid():
    from act18_teacher_state_replay import sweep_interval, sweep_half_max
    points = [(10.8, .61), (11.0, .82), (11.2, .70), (11.4, .40), (11.6, .1)]
    interval = sweep_interval(points)
    assert interval['pe_min'] == 10.8 and interval['pe_max'] == 11.2
    assert interval['peak_pe'] == 11.0 and interval['peak_raw'] == .82
    assert interval['width_s'] == pytest.approx(.4)
    half = sweep_half_max(points)
    assert half['peak_raw'] == .82 and half['half_max'] == pytest.approx(.41)
    assert half['pe_min'] == 10.8 and half['pe_max'] == 11.2
    assert sweep_interval([(9., .1), (10., .2)]) is None


def _replay_row(index, chunk_value=0., done=0.):
    chunk = np.full((c.CHUNK, c.ACTION_DIM), chunk_value)
    chunk[:, -1] = done
    return {'index': index, 'chunk': chunk.tolist(),
            'te': {'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                   'pwm': {str(s): 1500 for s in c.SERVOS},
                   'done': done >= .65, 'done_score': max(0., min(1., done))}}


def test_compare_replay_rows_is_fail_closed_at_one_microunit():
    from act18_teacher_state_replay import compare_replay_rows
    rows = [_replay_row(10), _replay_row(11)]
    reference = [_replay_row(10), _replay_row(11)]
    result = compare_replay_rows(rows, reference)
    assert result['passed'] and result['max_abs_chunk_diff'] == 0.
    rows[1]['chunk'][0][0] = 1e-3
    result = compare_replay_rows(rows, reference)
    assert not result['passed'] and result['max_abs_chunk_diff'] == pytest.approx(1e-3)
    assert result['max_abs_chunk_diff_tick'] == 11
    with pytest.raises(ValueError, match='row count mismatch'):
        compare_replay_rows(rows, reference[:1])


def _clock_rows(values):
    rows = []
    for index, pwm in enumerate(values):
        rows.append({'observation': {'t': index * c.PERIOD_S,
                                     'issued': [{'pwm': {str(s): pwm[str(s)] for s in c.SERVOS}}]}})
    return rows


def test_reconstruct_clock_deadband_removes_one_pwm_jitter():
    from act18_teacher_state_replay import reconstruct_clock
    base = {str(s): 1500 for s in c.SERVOS}
    base['1'] = 2000
    def with_servo4(value):
        return dict(base, **{'4': value})
    values = [base, base, with_servo4(1501), with_servo4(1502),
              with_servo4(1503), with_servo4(1504), with_servo4(1510)]
    rows = _clock_rows(values)
    any_change = reconstruct_clock(rows, 1)
    deadband = reconstruct_clock(rows, 3)
    assert any_change[round(0.2, 6)] == 0.
    assert any_change[round(0.6, 6)] == 0.
    assert deadband[round(0.2, 6)] == pytest.approx(.2)
    assert deadband[round(0.4, 6)] == pytest.approx(.4)
    assert deadband[round(0.5, 6)] == pytest.approx(.5)
    assert deadband[round(0.6, 6)] == 0.
    with pytest.raises(ValueError, match='deadband'):
        reconstruct_clock(rows, 0)


def test_rollout_anchor_prefers_lift_and_falls_back_to_grasp():
    from act18_teacher_state_replay import rollout_anchor
    truth = [{'t': 1.0, 'min_z': 0., 'finger_forces': [0., 0.]},
             {'t': 1.1, 'min_z': .013, 'finger_forces': [.1, .1]},
             {'t': 1.2, 'min_z': .02, 'finger_forces': [1., 1.]}]
    assert rollout_anchor(truth) == (1.1, 'lift_clearance')
    fallback = [{'t': 2.0, 'min_z': -.001, 'finger_forces': [0., 0.]},
                {'t': 2.1, 'min_z': 0., 'finger_forces': [.6, .7]}]
    assert rollout_anchor(fallback) == (2.1, 'grasp_force_fallback')
    with pytest.raises(ValueError, match='no physical lift'):
        rollout_anchor([{'t': 0., 'min_z': 0., 'finger_forces': [0., 0.]}])


def test_aligned_skill_elapsed_interpolates_and_extrapolates():
    from act18_teacher_state_replay import aligned_skill_elapsed
    teacher = {'t': [0., 1., 2.], 'skill_elapsed_s': [0., 1., 2.5]}
    assert aligned_skill_elapsed(teacher, .5) == pytest.approx(.5)
    assert aligned_skill_elapsed(teacher, 1.5) == pytest.approx(1.75)
    assert aligned_skill_elapsed(teacher, 3.5) == pytest.approx(4.)
    assert aligned_skill_elapsed(teacher, -1.) == 0.


def test_stabilize_history_replaces_only_post_anchor_jitter():
    from act18_teacher_state_replay import stabilize_history, stabilized_commands
    base = {str(s): 1500 for s in c.SERVOS}
    values = [dict(base), dict(base, **{'3': 740}), dict(base, **{'3': 741}),
              dict(base, **{'3': 745})]
    rows = []
    for index, pwm in enumerate(values):
        rows.append({'observation': {
            't': index * c.PERIOD_S,
            'issued': [{'t': index * c.PERIOD_S, 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                        'pwm': {str(s): pwm[str(s)] for s in c.SERVOS}}]}})
    stabilized = stabilized_commands(rows)
    assert stabilized[round(0.1, 6)]['3'] == 740
    assert stabilized[round(0.2, 6)]['3'] == 740
    assert stabilized[round(0.3, 6)]['3'] == 745
    obs, _ = observation(now=0.3)
    obs['pwm_elapsed_s'] = .1
    obs['skill_elapsed_s'] = 1.
    keep = stabilize_history(obs, stabilized, 0.0)
    for entry in keep['issued']:
        reference = stabilized.get(round(float(entry['t']), 6))
        if reference is not None:
            assert entry['pwm']['3'] == reference['3']
    unchanged = stabilize_history(obs, stabilized, 99.)
    assert [entry['pwm'] for entry in unchanged['issued']] == [entry['pwm'] for entry in obs['issued']]


def test_c2a_decision_pass_fail_and_inconclusive():
    from act18_teacher_state_replay import c2a_decision
    names = ['w0', 'w1', 'w2', 'w3']
    pass_rows = {name: {'a1_ge_065': index < 3,
                        'a1_done_max_hold_pm10': .9 if index < 3 else .01,
                        'a3_interval_inside_10_8_11_8': index < 3,
                        'a3_sweep_points': [(11.0, .7)] if index < 3 else [(11.0, .01)]}
                 for index, name in enumerate(names)}
    decision = c2a_decision(names, pass_rows)
    assert decision['verdict'] == 'PASS' and decision['D11_condition_i_met']
    fail_rows = {name: {'a1_ge_065': False, 'a1_done_max_hold_pm10': .01,
                        'a3_interval_inside_10_8_11_8': False,
                        'a3_sweep_points': [(11.0, .01)]} for name in names}
    assert c2a_decision(names, fail_rows)['verdict'] == 'FAIL'
    mixed = dict(pass_rows)
    mixed['w3'] = fail_rows['w3']
    assert c2a_decision(names, mixed)['verdict'] == 'PASS'
    mixed['w2'] = fail_rows['w2']
    assert c2a_decision(names, mixed)['verdict'] == 'INCONCLUSIVE'


def test_c2b_decision_done_path_and_backward_attribution():
    from act18_teacher_state_replay import c2b_decision
    lift = [f'L{index}' for index in range(6)]
    control = ['C0', 'C1']
    per_variant = {variant: {} for variant in ('S0', 'S2', 'S3', 'S4')}
    for variant in per_variant:
        for index, label in enumerate(lift):
            fire = variant == 'S2' and index < 5
            per_variant[variant][label] = {
                'done_fire': fire,
                'fire_pe_in_10_3_12_0': fire,
                'backward_onset': variant == 'S2' and index < 5,
            }
        for label in control:
            per_variant[variant][label] = {'done_fire': False,
                                           'fire_pe_in_10_3_12_0': False,
                                           'backward_onset': False}
    decision = c2b_decision(per_variant, lift, control)
    assert decision['done_path_verdict'] == 'PASS'
    assert decision['b1_S2_lift_fires_pe_in_range'] == 5
    assert decision['b2_single_variant_attribution'] == 'S2'
    assert decision['D11_condition_ii_confirmed'] is True
    for variant in per_variant:
        for label in lift:
            per_variant[variant][label] = {'done_fire': variant == 'S2' and label == 'L0',
                                           'fire_pe_in_10_3_12_0': variant == 'S2' and label == 'L0',
                                           'backward_onset': False}
    decision = c2b_decision(per_variant, lift, control)
    assert decision['done_path_verdict'] == 'FAIL'
    assert decision['D11_condition_ii_confirmed'] is False
    assert decision['b2_single_variant_attribution'] is None
