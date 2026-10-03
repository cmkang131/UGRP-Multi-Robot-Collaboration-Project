"""Independent PR #362 review checks; synthetic data only, no held-out reads.

Run from the repository root with pytest. The comparison implementation is
loaded from the actual #356 merge commit, not from the candidate's option-off
path. No production files are modified.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import types

import numpy as np
import pytest

from scripts import validate_consumer_criterion_b_v91 as v
from tests.test_consumer_criterion_b import synthetic
from tests.test_consumer_criterion_b_v91 import MAPS, get, offline_only
from tests.test_consumer_criterion_b_v91_yaw import yaw_templates

BASE = '36a7dfceb767437f29f469fc860fc02f8a349654'
HEAD = 'edcb4d3c0a001b4c5fa7bf5c61a7ae6be3177bb2'
b = v.frozen


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


@pytest.fixture(scope='module')
def merged_356():
    path = 'scripts/validate_consumer_criterion_b_v91.py'
    blob = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=v.ROOT)
    module = types.ModuleType('merged_356_validator')
    module.__file__ = str(v.ROOT / path)
    exec(compile(blob, f'{BASE}:{path}', 'exec'), module.__dict__)
    return module


@pytest.mark.parametrize('axis', [0, 1])
@pytest.mark.parametrize('condition', ['pass', 'fail', 'unsupported', 'training'])
def test_score_byte_parity_with_actual_356(merged_356, axis, condition):
    data, candidate, _ = synthetic(axis)
    if condition == 'fail':
        data['pose'][:, axis] *= 10
    elif condition == 'unsupported':
        data['segments'][b.AXES[axis]]['prbs'] = []
    elif condition == 'training':
        data['training'] = True
    old = merged_356.score([data], candidate, b.criterion(), chronology_verified=True)
    new = v.score([data], candidate, b.criterion(), chronology_verified=True)
    assert encoded(new) == encoded(old)
    expected = {'pass': True, 'fail': False, 'unsupported': None, 'training': None}[condition]
    assert new['axis_pass'][b.AXES[axis]] is expected


def test_full_validator_byte_parity_with_actual_356(merged_356, yaw_templates):
    # These fixtures contain synthetic commands/poses, even though the source
    # acquisition identities deliberately match the frozen contract.
    reference = merged_356.validate(yaw_templates)
    option_off = v.validate(yaw_templates)
    option_on = v.validate(yaw_templates, rotation_addendum=True)
    option_on.pop('rotation_addendum')
    option_on.pop('with_rotation_addendum')
    assert encoded(reference) == encoded(option_off) == encoded(option_on)


def independent_yaw():
    """Generate the pose mean without calling the frozen mean implementation."""
    profile = get(v.ROTATION_CANDIDATE)['candidate_axes']['rotate']['consumer_fields']
    data, _, _ = synthetic(2)
    velocity = 0.
    angles = [0.]
    increments = []
    for command in data['u'][:, 2]:
        tau = profile['tau_s'] if command else profile['tau_stop_s']
        velocity += (1 - math.exp(-.05 / tau)) * (profile['gain'][2][2] * command - velocity)
        increments.append(velocity * .05)
        angles.append(angles[-1] + velocity * .05)
    data['pose'] = np.column_stack((np.zeros((len(angles), 2)), angles))
    return data, profile, np.asarray(increments)


def independent_peak(data, profile, increments):
    # Pure-turn yaw variance is the sum of per-tick white process variances.
    # This computes every complete window without legacy_windows/evaluate_axis.
    peaks = []
    for spans in data['segments']['rotate'].values():
        for horizon in b.criterion()['horizons_s']:
            k = round(horizon / .05)
            normalized = []
            for start, end in spans:
                for index in range(start, end-k+1):
                    delta = increments[index:index+k]
                    sigma = np.sqrt(np.sum((profile['noise_rel'][2]*np.abs(delta/.05)
                                            + profile['noise_abs'][2])**2 * .05**2))
                    error = delta.sum() - (data['pose'][index+k, 2] - data['pose'][index, 2])
                    normalized.append(abs(math.atan2(math.sin(error), math.cos(error))) / sigma)
            peaks.append(float(np.percentile(normalized, 95)))
    return max(peaks)


@pytest.mark.parametrize('sign', [-1, 1])
def test_independent_yaw_just_pass_fail(sign):
    data, profile, increments = independent_yaw()
    times = np.arange(len(data['pose'])) * .05
    probe = copy.deepcopy(data)
    probe['pose'][:, 2] += times * .001
    rate = .001 * 2 / independent_peak(probe, profile, increments)
    data['pose'][:, 2] += times * rate * (1 + sign * 1e-7)
    cases = [copy.deepcopy(data) for _ in MAPS]
    for case, map_id in zip(cases, MAPS):
        case['map_id'] = map_id
    result = v.score_rotation(cases, profile, set(), b.criterion())
    assert result['pass'] is (sign < 0)
    peak = independent_peak(data, profile, increments)
    actual = max(row['normalized_abs_error_p95'][2]
                 for row in b.all_rows(result['cases'][0]['metrics']))
    assert actual == pytest.approx(peak, rel=0, abs=2e-12)
    assert actual == pytest.approx(2 * (1 + sign * 1e-7), abs=2e-12)
    for case, row in zip(cases, result['cases']):
        assert encoded(row['metrics']) == encoded(b.evaluate_axis(case, 2, profile, b.criterion()))
    print(f'\nyaw sign={sign}: peak={actual:.15f}, pass={result["pass"]}')


@pytest.mark.parametrize('outliers', [0, 5, 9, 10, 11])
def test_independent_two_sigma_and_p95_conjunction(outliers):
    # Exact 2-sigma is inclusive. At 90% coverage, p95 still vetoes the group.
    errors = np.zeros((100, 3))
    errors[:, 2] = 2.
    errors[:outliers, 2] = 2.000001
    result = b.metrics(errors, np.repeat(np.eye(3)[None], 100, axis=0), b.criterion())
    assert result['coverage_2sigma'][2] == (100-outliers)/100
    assert result['numerical_pass'] is (outliers == 0)


def test_preserved_files_match_both_main_and_candidate_git_blobs():
    receipt = get(v.ROOT / 'experiments/2026-10-03-critb-v91-yaw/preservation.json')
    assert len(receipt['files_sha256']) == 64
    for path, expected in receipt['files_sha256'].items():
        live = (v.ROOT / path).read_bytes()
        for revision in (BASE, HEAD):
            blob = subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=v.ROOT)
            assert blob == live, (revision, path)
        assert hashlib.sha256(live).hexdigest() == expected, path
