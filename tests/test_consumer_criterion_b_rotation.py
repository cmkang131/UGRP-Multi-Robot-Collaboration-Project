"""Synthetic yaw fit/lexicographic coverage; never reads physical raw."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import fit_consumer_criterion_b as r4
from scripts import fit_consumer_criterion_b_rotation as f
from scripts import validate_consumer_criterion_b as b
from tests.test_consumer_criterion_b import raw_case, synthetic


@pytest.mark.parametrize('parameters', [(1.2, .4, .08), (.7, 1.1, .11)])
def test_recovers_yaw_from_actual_consumer_method_and_matches_r4(parameters):
    data, _, _ = synthetic(2, gain=parameters[0], run=parameters[1], stop=parameters[2])
    model, audit = f.fit_training([data], b.criterion())
    np.testing.assert_allclose(list(model['parameters'].values()), parameters, rtol=1e-5)
    assert model['parameters'] == r4.fit_mean(data, 2, b.criterion())['parameters']
    assert model['optimizer']['rank'] == 3
    assert model['optimizer']['boundary'] == []
    assert audit['minimum_training_2sigma_coverage'] == 1.
    assert model['consumer_fields']['noise_abs'] == b.criterion()['noise']['floor_noise_abs']
    assert model['consumer_fields']['noise_rel'] == b.criterion()['noise']['floor_noise_rel']


def test_pooled_cases_and_no_excitation_do_not_change_mean():
    data, _, _ = synthetic(2)
    unexcited, _, _ = synthetic(0)
    fit, audit = f.fit_training([unexcited, data, copy.deepcopy(data)], b.criterion())
    np.testing.assert_allclose(list(fit['parameters'].values()), [1.2, .4, .08], rtol=1e-5)
    assert audit['cases'][0]['turn_nonzero_ticks'] == 0
    assert len(audit['training']) == 2


@pytest.mark.parametrize('reason', ['no_excitation', 'missing_prbs', 'one_sign', 'short', 'not_identifiable'])
def test_unsupported_or_unidentifiable_yaw_remains_null(reason):
    data, _, _ = synthetic(2)
    if reason == 'no_excitation':
        data['u'][:] = 0
    elif reason == 'missing_prbs':
        data['segments']['rotate']['prbs'] = []
    elif reason == 'one_sign':
        data['u'] = np.abs(data['u'])
    elif reason == 'short':
        data['segments']['rotate']['prbs'] = [(410, 430)]
    else:
        data['pose'][:] = 0  # nonzero commands cannot identify an interior gain
    model, audit = f.fit_training([data], b.criterion())
    assert model is None and audit['reason']


def test_yaw_variance_coefficients_match_full_euler_covariance():
    data, candidate, _ = synthetic(2)
    model = candidate['candidate_axes']['rotate']
    mp = copy.deepcopy(model['consumer_fields'])
    mp['noise_abs'] = [.045, .032, .077]
    increments = b.c.legacy_increments(data, mp)
    groups = f.noise_groups([data], model, b.criterion())
    for g in groups:
        starts, k = b.c.windows(data['segments']['rotate'][g['split']], g['horizon'], data['dt'])
        _, cov = b.c.legacy_windows(increments, starts, k, data['dt'], mp, scale=False)
        x, y, yaw = mp['noise_abs']
        rel = mp['noise_rel'][2]
        diagonal = np.column_stack((g['cc']*x*x+g['ss']*y*y,
                                    g['ss']*x*x+g['cc']*y*y,
                                    g['kdt2']*yaw*yaw+2*rel*g['sv']*yaw+rel*rel*g['sv2']))
        np.testing.assert_allclose(diagonal, np.diagonal(cov, axis1=1, axis2=2), rtol=1e-13, atol=1e-18)


def test_inflated_yaw_minimum_and_lower_counterexample():
    data, candidate, _ = synthetic(2)
    # Known under-modelled yaw drift with signed input: fit fixed mean, choose noise.
    data['pose'][:, 2] += np.arange(len(data['pose']))*.05*.05
    model = candidate['candidate_axes']['rotate']
    noise = f.minimum_noise(f.noise_groups([data], model, b.criterion()), b.criterion())
    mp = copy.deepcopy(model['consumer_fields'])
    mp['noise_abs'] = noise['noise_abs']
    assert mp['noise_abs'][2] > b.criterion()['noise']['floor_noise_abs'][2]
    assert min(min(r['coverage_2sigma']) for r in b.all_rows(b.evaluate_axis(data, 2, mp, b.criterion()))) >= .95
    mp['noise_abs'][2] -= 1e-6
    assert min(min(r['coverage_2sigma']) for r in b.all_rows(b.evaluate_axis(data, 2, mp, b.criterion()))) < .95


def group(error, cc, ss):
    n = len(error)
    return {'error': np.asarray(error), 'cc': np.full(n, cc), 'ss': np.full(n, ss),
            'sv': np.zeros(n), 'sv2': np.zeros(n), 'kdt2': 1.,
            'case': 'synthetic', 'split': 'steps', 'horizon': 3.2}


def test_rotation_mixing_keeps_earlier_forward_at_floor_and_inflates_later_left():
    # Both position components can be covered by left. Minimizing forward with
    # left fixed at floor would violate B's lexicographic order.
    g = group([[.2, .1, 0.]]*20, .8, .2)
    gate = b.criterion()
    noise = f.minimum_noise([g], gate)
    x, y, _ = noise['noise_abs']
    assert x == gate['noise']['floor_noise_abs'][0]
    expected = np.sqrt((.2**2/4-.8*x*x)/.2)
    assert y == pytest.approx(expected+1e-12, abs=1e-15)
    assert .8*x*x+.2*(y-1e-6)**2 < .2**2/4


def test_zero_heading_windows_constrain_forward_and_order_statistic_is_ceil95():
    g = group([[.2, .1, 0.]]*19+[[100., 100., 100.]], 1., 0.)
    noise = f.minimum_noise([g], b.criterion())
    np.testing.assert_allclose(noise['noise_abs'], [.1+1e-12, .05+1e-12, .01406], rtol=0, atol=1e-15)
    assert noise['certificate']['0']['limiting_group']['required_covered'] == 19


def test_yaw_training_profile_preserves_frozen_translation_and_null_admission():
    previous = json.loads(b.CANDIDATE.read_bytes())
    data, _, _ = synthetic(2)
    model, _ = f.fit_training([data], b.criterion())
    candidate = f.make_candidate(previous, model, [data])
    assert b.sha(b.CANDIDATE.read_bytes()) == f.R4_SHA
    assert candidate['candidate_axes']['forward'] == previous['candidate_axes']['forward']
    assert candidate['candidate_axes']['left'] == previous['candidate_axes']['left']
    assert previous['candidate_axes']['rotate'] is None
    assert candidate['axis_validation'] == dict.fromkeys(b.AXES)
    assert candidate['params']['motion'] is None
    assert candidate['status'] == 'CANDIDATE_UNVALIDATED'
    assert 'synthetic' in candidate['previously_seen_pose_sha256']


@pytest.mark.parametrize('path', ['/not-training/raw',
    '/Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-DO-NOT-OPEN/calibration-unloaded'])
def test_nontraining_paths_are_rejected_before_any_filesystem_read(monkeypatch, path):
    def forbidden(*args, **kwargs):
        pytest.fail('must reject path before read/resolve/glob')
    for name in ('read_bytes', 'read_text', 'resolve', 'glob', 'rglob', 'iterdir'):
        monkeypatch.setattr(Path, name, forbidden)
    with pytest.raises(ValueError, match='authorized training'):
        f.training_path(path)


def test_symlink_to_other_raw_is_rejected_without_reading(tmp_path, monkeypatch):
    root = tmp_path/'training'
    root.mkdir()
    link = root/'pose.jsonl'
    link.symlink_to(tmp_path/'unseen')
    monkeypatch.setattr(f, 'V88', root)
    with pytest.raises(ValueError, match='symlink'):
        f.training_path(link)


def test_real_pose_command_schema_does_not_depend_on_frame_clock(tmp_path):
    folder, _ = raw_case(tmp_path, 2)
    # Frames have sim_time and no t; this yaw-only loader must not read them.
    frame_path = folder/'robots/r1/frames.jsonl'
    frame_path.write_text(json.dumps({'sim_time': 1.3, 'frame_id': 1})+'\n')
    loaded = b.load_case(folder, b.criterion())
    assert b.axis_supported(loaded, 2, b.criterion())
    assert str(frame_path) not in [r['path'] for r in loaded['inputs']]


def test_cli_exposes_only_output_not_arbitrary_raw():
    with pytest.raises(SystemExit) as exc:
        f.main(['--raw', '/unseen'])
    assert exc.value.code == 2
