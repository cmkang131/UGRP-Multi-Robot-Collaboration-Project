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
