"""Independent PR #364 checks using synthetic data and the actual base source."""
import copy
import subprocess
import types

import pytest

from scripts import validate_consumer_criterion_b_v91 as new
from tests.test_consumer_criterion_b import synthetic
from tests.test_consumer_criterion_b_v91_yaw import (
    MAPS, get, serialized, yaw_case, yaw_templates,
)

b = new.frozen
BASE = '89ea80d536b3d2406848ba6e85ead4150ac06bd6'


@pytest.fixture(scope='module')
def previous():
    blob = subprocess.check_output([
        'git', 'show', BASE + ':scripts/validate_consumer_criterion_b_v91.py',
    ], cwd=new.ROOT)
    module = types.ModuleType('review_364_previous')
    module.__file__ = new.__file__
    exec(compile(blob, 'base_89ea80d5_validator', 'exec'), module.__dict__)
    return module


def original_B(report):
    return {k: v for k, v in report.items()
            if k not in ('rotation_addendum', 'with_rotation_addendum')}


@pytest.mark.parametrize('axis', [0, 1])
@pytest.mark.parametrize('state', ['pass', 'fail', 'unsupported', 'prior', 'training'])
def test_translation_report_exact_base_bytes(previous, axis, state):
    data, candidate, _ = synthetic(axis)
    if state == 'fail':
        data['pose'][:, axis] *= 10
    elif state == 'unsupported':
        data['segments'][b.AXES[axis]]['prbs'] = []
    elif state == 'prior':
        candidate['previously_seen_pose_sha256'] = [data['pose_sha256']]
    elif state == 'training':
        data['training'] = True
    args = ([data], candidate, b.criterion())
    assert serialized(previous.score(*args, chronology_verified=True)) == serialized(
        new.score(*args, chronology_verified=True))


@pytest.mark.parametrize('excluded', [(), (0,), (1,), (0, 1)])
def test_full_original_report_exact_base_bytes(previous, yaw_templates, monkeypatch, excluded):
    # Inject only synthetic pose hashes into the yaw prior set in both versions.
    prior = {b.sha((yaw_templates[i]/MAPS[i]/'eval_only/r1/pose.jsonl').read_bytes())
             for i in excluded}
    for module in (previous, new):
        prepare = module.prepare_rotation
        def with_prior(*args, _prepare=prepare, **kwargs):
            result = _prepare(*args, **kwargs)
            result['prior'].update(prior)
            return result
        monkeypatch.setattr(module, 'prepare_rotation', with_prior)
    baseline = previous.validate(yaw_templates)
    for module in (previous, new):
        for enabled in (False, True):
            report = module.validate(yaw_templates, rotation_addendum=enabled)
            assert serialized(original_B(report)) == serialized(baseline)


def test_frozen_B_and_yaw_have_same_prior_validation_exclusion():
    data, profile = yaw_case()
    candidate = get(new.ROTATION_CANDIDATE)
    candidate['previously_seen_pose_sha256'] = [data['pose_sha256']]
    old_axis = b.score([data], candidate, b.criterion())['cases'][0]['axes']['rotate']
    yaw = new.score_rotation([data], profile, {data['pose_sha256']}, b.criterion())['cases'][0]
    assert old_axis['pass'] is yaw['pass'] is None
    assert old_axis['reason'] == 'previously seen raw pose bytes'
    assert yaw['reason'] == 'PREVIOUSLY_SEEN_POSE_BYTES'
    # Diagnostic computation differs intentionally; eligibility does not.
    assert old_axis['metrics'] is not None
    assert yaw['metrics'] is None and 'numerical_pass' not in yaw


def test_excluded_cases_need_no_numeric_payload_and_cannot_select_by_error():
    data, profile = yaw_case()
    fresh = copy.deepcopy(data)
    fresh.update(map_id=MAPS[0], pose_sha256='fresh')
    fresh['pose'][:, 2] *= 10  # A fresh failing case must remain a scored failure.
    seen = dict(map_id=MAPS[1], folder='synthetic-excluded', pose_sha256='seen',
                training=False, dt=.05)  # No pose/u/segments to evaluate.
    report = new.score_rotation([seen, fresh], profile, {'seen'}, b.criterion())
    assert report['pass'] is False
    assert report['scope'] == 'PARTIAL_MAPS'
    assert report['maps_scored'] == [MAPS[0]]
    assert report['maps_not_scored'] == [MAPS[1]]
    assert report['cases'][0]['reason'] == 'PREVIOUSLY_SEEN_POSE_BYTES'
    assert report['cases'][1]['pass'] is False
