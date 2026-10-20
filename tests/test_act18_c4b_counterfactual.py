"""Unit tests for the ACT18 C4b counterfactual replay helpers (CPU only, no model)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from harness import grasp_act_contract as c  # noqa: E402
from harness.grasp_act_policy import ChunkExecutor  # noqa: E402
from scripts import act18_c4b_counterfactual as c4b  # noqa: E402


def command(t, pwm1=1500):
    return {'t': t, 'wheels': [0., 0., 0., 0.], 'duration_s': [0., 0., 0., 0.],
            'pwm': {str(s): (pwm1 if s == 1 else 1500) for s in c.SERVOS}}


def observation(t=10., skill='release'):
    issued = [command(round(t - 0.1 * (15 - index), 6)) for index in range(c.HISTORY)]
    refs = [{'path': 'rgb/r1/%06d.jpg' % index, 'sha256': '%064x' % index,
             't': t - lag, 'robot_id': 'r1'} for index, lag in enumerate(c.RGB_LAGS_S)]
    return {'schema': c.SCHEMA, 'robot_id': 'r1', 'sample_id': 'warp3-88668-0-g0:0:r1',
            't': t, 'skill': skill, 'object_kind': 'cyan', 'role': 'west',
            'destination_zone': 'B', 'rgb': refs, 'issued': issued,
            'skill_elapsed_s': 0.5, 'pwm_elapsed_s': 2.5}


def test_release_window_uses_release_entry():
    rows = [dict(observation=dict(observation(t=9.0 + 0.1 * index, skill='grasp')))
            for index in range(3)]
    rows += [dict(observation=dict(observation(t=9.3 + 0.1 * index)))
             for index in range(100)]
    t0, window = c4b.release_window(rows)
    assert t0 == pytest.approx(9.3)
    assert len(window) == 80
    assert window[-1]['observation']['t'] == pytest.approx(9.3 + 7.9)


def test_replace_clocks_changes_only_the_named_clock():
    base = observation()
    pe = c4b.replace_clocks(base, pe=14.5)
    assert pe['pwm_elapsed_s'] == 14.5
    assert pe['skill_elapsed_s'] == base['skill_elapsed_s']
    assert {key: pe[key] for key in ('rgb', 'issued')} == {key: base[key] for key in ('rgb', 'issued')}
    se = c4b.replace_clocks(base, se=4.45)
    assert se['skill_elapsed_s'] == 4.45
    assert se['pwm_elapsed_s'] == base['pwm_elapsed_s']
    assert base['skill_elapsed_s'] == 0.5 and base['pwm_elapsed_s'] == 2.5


def test_replace_images_keeps_reference_bytes_and_shifts_times():
    target = observation(t=20.)
    source = dict(observation=observation(t=12.))
    changed = c4b.replace_images(target, source)
    assert changed['rgb'][-1]['t'] == pytest.approx(target['t'])
    assert changed['rgb'][0]['t'] == pytest.approx(target['t'] - c.RGB_LAGS_S[0])
    assert [ref['sha256'] for ref in changed['rgb']] == \
        [ref['sha256'] for ref in source['observation']['rgb']]
    c.validate_observation(changed)
    # The other fields are recorded and unchanged.
    for key in ('issued', 'skill_elapsed_s', 'pwm_elapsed_s', 't'):
        assert changed[key] == target[key]


def test_replace_history_keeps_target_timestamps():
    target = observation(t=20.)
    other = observation(t=12.)
    other['issued'] = [dict(row, pwm={str(s): 1700 for s in c.SERVOS}) for row in other['issued']]
    changed = c4b.replace_history(target, dict(observation=other))
    assert [row['t'] for row in changed['issued']] == [row['t'] for row in target['issued']]
    assert all(row['pwm']['1'] == 1700 for row in changed['issued'])
    c.validate_observation(changed)
    assert changed['rgb'] == target['rgb']


def test_apply_variant_rejects_unknown_arm():
    base = observation()
    with pytest.raises(ValueError):
        c4b.apply_variant('V-nope', base, same_row=dict(observation=base),
                          cross_row=dict(observation=base))


def test_temporal_ensemble_matches_chunk_executor():
    rng = np.random.default_rng(20261020)
    predictions = [rng.normal(0., .3, size=(c.CHUNK, c.ACTION_DIM)).tolist()
                   for _ in range(6)]
    counter = {'index': 0}

    def predict(obs, jpegs):
        value = predictions[counter['index']]
        counter['index'] += 1
        return value

    executor = ChunkExecutor(predict, n_action_steps=1, temporal_ensemble_coeff=.01)
    ensemble = c4b.TemporalEnsemble()
    for tick in range(len(predictions)):
        obs = observation(t=10. + 0.1 * tick)
        value, done = executor.step(obs, [b''] * c.RGB_HISTORY)
        action, _ = ensemble.step(predictions[tick])
        assert value['pwm'] == action['pwm']
        assert value['wheels'] == action['wheels']
        assert done == action['done']


def test_temporal_ensemble_freezes_after_done():
    values = np.zeros((c.CHUNK, c.ACTION_DIM))
    values[:, 8] = .5
    values[0, -1] = .9  # done at the first tick
    ensemble = c4b.TemporalEnsemble()
    action, _ = ensemble.step(values.tolist())
    assert action['done'] is True
    assert ensemble.done_requested is True
    held = c4b.held_command(observation())
    assert held['wheels'] == [0., 0., 0., 0.]
    assert held['pwm']['1'] == 1500


def test_open_tau_uses_first_threshold_crossing():
    assert c4b.open_tau([(0., 1500), (3.4, 1899), (3.5, 1900), (4.0, 2000)]) == 3.5
    assert c4b.open_tau([(0., 1500), (7.9, 1800)]) is None


def test_decide_rules():
    zero = {arm: 0 for arm in c4b.CONTROL_ARMS}
    assert c4b.decide(zero)['verdict'] == 'no_recovery'
    one = dict(zero, **{'V-pe': 6})
    assert c4b.decide(one) == dict(verdict='single_input_cause', arms=['V-pe'],
                                   text='단일 입력 원인: V-pe')
    cross = dict(zero, **{'V-img-cross': 7})
    assert c4b.decide(cross)['verdict'] == 'kind_specific_visual'
    both = dict(zero, **{'V-pe': 6, 'V-hist': 6})
    assert c4b.decide(both)['verdict'] == 'multiple_inputs'
    assert c4b.decide(both)['arms'] == ['V-pe', 'V-hist']


def test_reference_map_is_deterministic_and_never_self_for_failures():
    successes = [
        dict(label='a/g/world-000', kind='cyan'),
        dict(label='b/g/world-000', kind='red'),
        dict(label='c/g/world-000', kind='red'),
        dict(label='d/g/world-000', kind='yellow'),
        dict(label='e/g/world-000', kind='green'),
    ]
    failures = [dict(label='f/g/world-000', kind='red')]
    base, same, cross = c4b.reference_map(successes, successes + failures)
    assert base['cyan'] == 'a/g/world-000'
    assert same['f/g/world-000'] == 'b/g/world-000'
    assert same['b/g/world-000'] == 'c/g/world-000'
    assert same['a/g/world-000'] == 'a/g/world-000'  # only cyan success
    assert cross['a/g/world-000'] == 'e/g/world-000'  # cyan -> green
    assert cross['e/g/world-000'] == 'b/g/world-000'  # green -> red
    assert cross['b/g/world-000'] == 'd/g/world-000'  # red -> yellow
    assert cross['d/g/world-000'] == 'a/g/world-000'  # yellow -> cyan


def test_kind_of_rejects_unknown_item():
    assert c4b.kind_of('cyan_1') == 'cyan'
    assert c4b.kind_of('yellow_2') == 'yellow'
    with pytest.raises(ValueError):
        c4b.kind_of('long_beam_1')


def test_recorded_open_tau_none_and_value():
    def issued(rows):
        return [dict(skill='release', t=t, action=dict(command=command(t, pwm1)))
                for t, pwm1 in rows]
    assert c4b.recorded_open_tau(issued([(1.0, 1500), (1.1, 1900)])) == pytest.approx(.1)
    assert c4b.recorded_open_tau(issued([(1.0, 1500), (1.1, 1899)])) is None


def test_write_json_round_trip(tmp_path):
    path = tmp_path / 'x.json'
    c4b.write_json(path, {'b': 1, 'a': 2})
    assert json.loads(path.read_text()) == {'a': 2, 'b': 1}


def test_exploratory_hist_failure_arm_requires_reference():
    base = observation()
    with pytest.raises(ValueError):
        c4b.apply_variant('V-hist-fail', base, same_row=dict(observation=base),
                          cross_row=dict(observation=base))
    other = observation(t=12.)
    other['issued'] = [dict(row, pwm={str(s): 1650 for s in c.SERVOS}) for row in other['issued']]
    changed = c4b.apply_variant('V-hist-fail', base, same_row=dict(observation=base),
                                cross_row=dict(observation=base),
                                fail_row=dict(observation=other))
    assert all(row['pwm']['1'] == 1650 for row in changed['issued'])
    assert c4b.EXTRA_ARMS == ('V-hist-fail',)
    assert 'V-hist-fail' not in c4b.CONTROL_ARMS


# --- C4b-GPU addendum (C4_COUNTERFACTUAL_PREREG_ADDENDUM_GPU.json) -----------------

ADDENDUM = ROOT / 'experiments/2026-10-17-act18/C4_COUNTERFACTUAL_PREREG_ADDENDUM_GPU.json'
PREREG = ROOT / 'experiments/2026-10-17-act18/C4_COUNTERFACTUAL_PREREG.json'


def chunk_row(pwm1, done=False):
    values = np.zeros(c.ACTION_DIM)
    values[8] = (pwm1 - 1500) / 1000.
    values[-1] = .9 if done else .1
    return values


def series_from(predictions, held=1500):
    series = []
    for tick, prediction in enumerate(predictions):
        rows = [c.decode_action(values) for values in prediction]
        series.append(dict(tau=round(.1 * tick, 6), te_pwm1=0, raw_pwm1=rows[0]['pwm']['1'],
                           chunk_pwm1=[row['pwm']['1'] for row in rows],
                           chunk_done=[bool(row['done']) for row in rows],
                           held_pwm1=held, te_done=None))
    return series


def test_device_defaults_to_cpu_and_guard_fails_closed():
    base = ['--c2c-root', 'c', '--recovered-root', 'r', '--checkpoint', 'k', '--out', 'o']
    assert c4b.parse_arguments(base).device == 'cpu'
    assert c4b.parse_arguments(base + ['--device', 'cuda']).device == 'cuda'
    with pytest.raises(SystemExit):
        c4b.parse_arguments(base + ['--device', 'mps'])
    assert c4b.device_guard('cpu', False) == 'cpu'
    assert c4b.device_guard('cuda', True) == 'cuda'
    with pytest.raises(SystemExit):
        c4b.device_guard('cuda', False)
    with pytest.raises(ValueError):
        c4b.device_guard('mps', True)


def test_chunk_open_finds_first_tick_and_row_and_skips_frozen_ticks():
    flat = [chunk_row(1500)] * c.CHUNK
    later = [chunk_row(1500)] * 5 + [chunk_row(2009)] + [chunk_row(1500)] * 2
    series = series_from([flat, flat, later, later])
    assert c4b.chunk_open(series) == (pytest.approx(.2), 5)
    series[2]['chunk_pwm1'] = None  # no forward on that tick
    assert c4b.chunk_open(series) == (pytest.approx(.3), 5)
    assert c4b.chunk_open(series_from([flat] * 4)) == (None, None)


@pytest.mark.parametrize('steps', [4, 8])
def test_chunk_executor_series_matches_harness_chunk_executor(steps):
    rng = np.random.default_rng(20261020 + steps)
    predictions = []
    for tick in range(20):
        rows = [chunk_row(int(rng.integers(1400, 2100))) for _ in range(c.CHUNK)]
        predictions.append(rows)
    predictions[8][2] = chunk_row(1990, done=True)  # done row executed by both n=4 and n=8
    counter = {'index': 0}

    def predict(obs, jpegs):
        value = predictions[counter['index']]
        return [list(row) for row in value]

    executor = ChunkExecutor(predict, n_action_steps=steps, temporal_ensemble_coeff=None)
    expected = []
    for tick in range(len(predictions)):
        counter['index'] = tick
        obs = observation(t=10. + 0.1 * tick)
        value, done = executor.step(obs, [b''] * c.RGB_HISTORY)
        expected.append(value['pwm']['1'])
    series = series_from(predictions)
    result = c4b.chunk_executor_series(series, steps)
    first = next((round(.1 * i, 6) for i, v in enumerate(expected) if v >= c4b.OPEN_PWM1), None)
    assert result['open_tau'] == first
    assert result['pwm1_max'] == max(expected)
    assert result['truncated_at_tau'] is None
    assert result['ticks'] == len(predictions)


def test_chunk_executor_series_latest4_recovers_a_te_diluted_open():
    # One new chunk per tick predicts the open step only from row 0 of tick 3 on;
    # the TE average stays below 1900 for the first ticks, latest4 opens at once.
    closed = [chunk_row(1520)] * c.CHUNK
    opened = [chunk_row(2009)] * c.CHUNK
    predictions = [closed] * 4 + [opened] * 4
    series = series_from(predictions)
    ensemble = c4b.TemporalEnsemble()
    te = [ensemble.step([list(row) for row in p])[0]['pwm']['1'] for p in predictions]
    assert te[4] < c4b.OPEN_PWM1  # diluted on the first open tick
    assert c4b.chunk_executor_series(series, 4)['open_tau'] == pytest.approx(.4)
    assert c4b.chunk_executor_series(series, 8)['open_tau'] is None  # still executing tick-0 chunk


def test_chunk_executor_series_truncates_when_forward_missing():
    closed = [chunk_row(1520)] * c.CHUNK
    series = series_from([closed] * 6)
    series[4]['chunk_pwm1'] = None
    result = c4b.chunk_executor_series(series, 4)
    assert result['truncated_at_tau'] == pytest.approx(.4)
    assert result['ticks'] == 4
    with pytest.raises(ValueError):
        c4b.chunk_executor_series(series, 9)


def test_chunk_executor_series_holds_after_done():
    rows = [chunk_row(1600, done=True)] + [chunk_row(2000)] * (c.CHUNK - 1)
    series = series_from([rows] * 4, held=1515)
    result = c4b.chunk_executor_series(series, 4)
    assert result['done_tau'] == 0.
    assert result['open_tau'] is None and result['pwm1_max'] == 1600


def _world(label, outcome, v0_open, hist, hist_fail, chunk, latest4):
    def arm(open_tau, chunk_tau=None, l4=None):
        return dict(open_tau=open_tau, raw_open_tau=None, done_tau=None, te_pwm1_max=1500,
                    chunk_open_tau=chunk_tau, chunk_open_row=None,
                    executors=dict(latest4=dict(open_tau=l4, truncated_at_tau=None),
                                   latest8=dict(open_tau=None, truncated_at_tau=None)))
    arms = {name: arm(None) for name in c4b.ARMS}
    arms['V0'] = arm(v0_open, chunk, latest4)
    arms['V-hist'] = arm(hist)
    if outcome == 'failure':
        arms['V-hist-fail'] = arm(hist_fail)
    return dict(label=label, outcome=outcome, arms=arms)


def test_summarize_addendum_masked_rate_and_decisions():
    failures = [_world('f%d' % i, 'failure', None, 3.4 if i < 7 else None,
                       3.0 if i < 2 else None, 2.0 if i < 8 else None,
                       2.5 if i < 6 else None) for i in range(10)]
    successes = [_world('s%d' % i, 'success', 3.0, 3.0, None, 2.0, 2.0) for i in range(9)]
    summary = c4b.summarize(failures + successes, 'x', c4b.ADDENDUM_ARMS, addendum=True)
    assert summary['table']['V-hist-fail']['failure_n'] == 10
    assert summary['table']['V-hist-fail']['success_n'] == 0
    add = summary['addendum']
    assert add['hist_fail_recovered'] == 2
    assert add['executor_recovered'] == {'latest4': 6, 'latest8': 0}
    assert add['h_a2_masked_by_te'] == dict(arm='V0', n=8, N=10, rate=.8)
    assert add['decision']['h_a1']['verdict'] == 'supported'
    assert add['decision']['h_a2'] == dict(verdict='supported', executors=['latest4'],
                                           text='대체 실행기 회복 -> H-A2 지지')
    # The original decision over the five registered control arms is unchanged.
    assert summary['decision']['verdict'] == 'single_input_cause'
    assert summary['decision']['arms'] == ['V-hist']


def test_decide_addendum_refutations():
    rec = {'V-hist': 7}
    assert c4b.decide_addendum(rec, 6, {}, 3)['h_a1']['verdict'] == 'refuted_any_history'
    assert c4b.decide_addendum({'V-hist': 5}, 0, {}, 3)['h_a1']['verdict'] == 'not_supported'
    assert c4b.decide_addendum(rec, None, {}, 3)['h_a1']['verdict'] == 'incomplete'
    assert c4b.decide_addendum(rec, 0, {'latest4': 5, 'latest8': 0}, 0)['h_a2']['verdict'] == 'refuted'
    assert c4b.decide_addendum(rec, 0, {'latest4': 5, 'latest8': 0}, 4)['h_a2']['verdict'] == 'not_supported'


def test_hist_fail_reference_is_same_kind_failure_never_self():
    registration = json.loads(PREREG.read_text())
    labels = [item['label'] for item in registration['targets']['failure']]
    for item in registration['targets']['failure']:
        reference = c4b.hist_fail_reference(registration, item['label'], item['kind'])
        assert reference in labels and reference != item['label']
        kinds = {x['label']: x['kind'] for x in registration['targets']['failure']}
        assert kinds[reference] == item['kind']
    # green has no failure world: no reference exists for green success worlds.
    assert c4b.hist_fail_reference(registration, 'x', 'green') is None


def test_addendum_file_matches_code_and_base_prereg(tmp_path):
    value = c4b.load_addendum(ADDENDUM, PREREG)
    registration = json.loads(PREREG.read_text())
    assert value['device'] == 'cuda'
    assert value['arms'] == list(c4b.ADDENDUM_ARMS)
    assert value['offline_aggregates']['alternative_executors']['executors'] == \
        {name: dict(n_action_steps=steps, temporal_ensemble_coeff=None)
         for name, steps in c4b.ALT_EXECUTORS.items()}
    failures = registration['targets']['failure']
    assert value['hist_fail_reference'] == {
        item['label']: c4b.hist_fail_reference(registration, item['label'], item['kind'])
        for item in failures}
    assert value['decision']['minimum_recovered'] == c4b.DECISION_MIN
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps(dict(value, base_prereg=dict(value['base_prereg'], sha256='0' * 64))))
    with pytest.raises(SystemExit):
        c4b.load_addendum(bad, PREREG)
