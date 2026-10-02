"""Independent synthetic-only review of PR #356 at 1dd9f0e7.

Set UGRP_REVIEW_356_ROOT to the git archive of the reviewed source.
No real held-out paths are inputs. Threshold isolation uses metric/axis seams;
the separate trajectory tests exercise integration and the full scoring path.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sys

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))


@pytest.fixture(scope='module')
def target():
    root = Path(os.environ['UGRP_REVIEW_356_ROOT']).resolve()
    sys.path.insert(0, str(root))
    new = importlib.import_module('scripts.validate_consumer_criterion_b_v91')
    assert Path(new.__file__).resolve().is_relative_to(root)
    spec = importlib.util.spec_from_file_location('review356_fixture', root/'tests/test_consumer_criterion_b_v91.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    yield new, new.frozen, fixtures
    sys.path.remove(str(root))


@pytest.mark.parametrize('axis', [0, 1])
@pytest.mark.parametrize('split', ['steps', 'prbs'])
@pytest.mark.parametrize('horizon', [.2, .5, 1., 2., 3., 3.2])
@pytest.mark.parametrize('component', [0, 1, 2])
@pytest.mark.parametrize('boundary', ['p95_below', 'p95_above', 'coverage_equal', 'coverage_below'])
def test_each_group_preserves_threshold_decision(target, monkeypatch, axis, split, horizon, component, boundary):
    new, old, fixtures = target
    data, candidate, _ = fixtures.synthetic(axis)
    gate = old.criterion()
    if boundary.startswith('p95'):
        errors = np.zeros((100, 3))
        errors[:, component] = 2. + (-1e-10 if boundary == 'p95_below' else 1e-10)
    else:
        errors = np.zeros((10 if boundary == 'coverage_equal' else 9, 3))
        errors[-1, component] = 3.
    row = old.metrics(errors, np.tile(np.eye(3), (len(errors), 1, 1)), gate)
    expected = boundary in ('p95_below', 'coverage_equal')
    assert row['numerical_pass'] is expected
    if boundary.startswith('coverage'):
        assert row['normalized_abs_error_p95'][component] < 2.
        assert row['coverage_2sigma'][component] == (len(errors)-1)/len(errors)
    good = old.metrics(np.zeros((10, 3)), np.tile(np.eye(3), (10, 1, 1)), gate)
    groups = {s: {str(h): copy.deepcopy(good) for h in gate['horizons_s']} for s in ('steps', 'prbs')}
    groups[split][str(horizon)] = row
    monkeypatch.setattr(old, 'evaluate_axis', lambda *args: copy.deepcopy(groups))
    frozen = old.score([data], candidate, gate)
    adapted = new.score([data], candidate, gate, chronology_verified=True)
    name = old.AXES[axis]
    assert frozen['cases'][0]['axes'][name]['metrics'] == adapted['cases'][0]['axes'][name]['metrics']
    assert frozen['cases'][0]['axes'][name]['numerical_pass'] is expected
    assert adapted['axis_pass'][name] is expected
    assert frozen['axis_pass'][name] is None  # original chronology veto remains frozen
    assert adapted['axis_pass']['rotate'] is None
    assert adapted['pass'] is (None if expected else False)


@pytest.mark.parametrize('axis', [0, 1])
def test_independent_euler_noise_and_full_trajectory_parity(target, axis):
    new, old, fixtures = target
    data, _, _ = fixtures.synthetic(axis)
    candidate = json.loads(old.CANDIDATE.read_bytes())
    profile = candidate['candidate_axes'][old.AXES[axis]]['consumer_fields']
    velocity = np.zeros(3)
    increments = []
    for command in data['u']:
        tau = np.asarray(profile.get('tau_axis_s', profile['tau_s']) if np.any(command)
                         else profile.get('tau_stop_s', profile['tau_s']))
        velocity += (1 - np.exp(-.05/tau)) * (np.asarray(profile['gain']) @ command - velocity)
        increments.append(velocity.copy()*.05)
    increments = np.asarray(increments)
    np.testing.assert_allclose(old.c.legacy_increments(data, profile), increments, atol=1e-17, rtol=1e-13)
    data['pose'] = np.vstack([np.zeros(3), np.cumsum(increments, axis=0)])
    for horizon in old.criterion()['horizons_s']:
        k = round(horizon/.05)
        mean, covariance = np.zeros(3), np.zeros((3, 3))
        for delta in increments[10:10+k]:
            co, si = math.cos(mean[2]), math.sin(mean[2])
            rotation = np.array([[co, -si, 0.], [si, co, 0.], [0., 0., 1.]])
            world = rotation @ delta
            jacobian = np.eye(3)
            jacobian[0, 2], jacobian[1, 2] = -world[1], world[0]
            sigma = np.asarray(profile['noise_rel'])*np.abs(delta/.05) + profile['noise_abs']
            covariance = jacobian @ covariance @ jacobian.T + rotation @ np.diag((sigma*.05)**2) @ rotation.T
            mean += world
        actual_mean, actual_covariance = old.c.legacy_windows(increments, np.array([10]), k, .05, profile, scale=False)
        np.testing.assert_allclose(actual_mean[0], mean, atol=1e-17, rtol=1e-13)
        np.testing.assert_allclose(actual_covariance[0], covariance, atol=1e-17, rtol=1e-13)
    doubled = copy.deepcopy(data)
    doubled['pose'][:, axis] *= 2.
    rows = old.all_rows(old.evaluate_axis(doubled, axis, profile, old.criterion()))
    boundary_delta = 2./max(max(row['normalized_abs_error_p95']) for row in rows)
    for magnitude, expected in ((1., True), (10., False),
                                (1.+boundary_delta*(1.-1e-8), True),
                                (1.+boundary_delta*(1.+1e-8), False)):
        altered = copy.deepcopy(data)
        altered['pose'][:, axis] *= magnitude
        frozen = old.score([altered], candidate, old.criterion())
        adapted = new.score([altered], candidate, old.criterion(), chronology_verified=True)
        for name in old.AXES:
            a, b = frozen['cases'][0]['axes'][name], adapted['cases'][0]['axes'][name]
            assert a['metrics'] == b['metrics']
            if a['metrics'] is not None:
                assert b['pass'] is a['numerical_pass']
        assert adapted['axis_pass'][old.AXES[axis]] is expected
        assert adapted['axis_pass']['rotate'] is None


@pytest.mark.parametrize('missing', ['unexcited', 'negative_sign', 'long_horizon', 'rotation_candidate'])
def test_axis_null_rules_survive_chronology_clearance(target, missing):
    new, old, fixtures = target
    data, candidate, _ = fixtures.synthetic()
    if missing == 'unexcited':
        data['u'][:, 0] = 0.
    elif missing == 'negative_sign':
        data['u'][:, 0] = np.abs(data['u'][:, 0])
    elif missing == 'long_horizon':
        data['segments']['forward']['prbs'] = [(410, 460)]
    else:
        candidate = json.loads(old.CANDIDATE.read_bytes())
        data, _, _ = fixtures.synthetic(2)
    report = new.score([data], candidate, old.criterion(), chronology_verified=True)
    assert report['axis_pass'] == dict.fromkeys(old.AXES)
    assert report['pass'] is None


@pytest.fixture(scope='module')
def template(target, tmp_path_factory):
    _, _, fixtures = target
    return fixtures.make_raw(tmp_path_factory.mktemp('review356-synthetic')/'collection', fixtures.MAPS[0])


@pytest.fixture
def raw(template, tmp_path):
    return Path(shutil.copytree(template, tmp_path/'synthetic'))


def test_real_writer_keys_without_optional_pose_labels_and_initial_servo(target, raw):
    new, _, fixtures = target
    folder = raw/fixtures.MAPS[0]
    path = folder/'eval_only/r1/pose.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        row.pop('map_id')
        row.pop('load_state')
        row.update(qualification='synthetic', wall_clearance_lower_bound_m=1.)
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    path = folder/'robots/r1/commands.jsonl'
    path.write_text(json.dumps({'t': .5, 'kind': 'initial_servo_command', 'pulses': {}})+'\n'+path.read_text())
    fixtures.receipts(raw)
    report = new.validate([raw])
    assert report['scope'] == 'HELD_OUT_VALIDATION', report.get('eligibility_reason')
    assert report['axis_pass'] == {'forward': True, 'left': True, 'rotate': None}


def test_detached_case_cannot_skip_parent(target, raw, tmp_path):
    new, _, fixtures = target
    detached = Path(shutil.copytree(raw/fixtures.MAPS[0], tmp_path/'detached'))
    fixtures.assert_ineligible(new.validate([detached]))


@pytest.mark.parametrize('corruption', ['pose_tamper', 'command_tamper', 'missing_manifest', 'missing_parent', 'duplicate_map'])
def test_additional_raw_fail_closed(target, raw, corruption):
    new, _, fixtures = target
    folder = raw/fixtures.MAPS[0]
    if corruption in ('pose_tamper', 'command_tamper'):
        name = 'eval_only/r1/pose.jsonl' if corruption == 'pose_tamper' else 'robots/r1/commands.jsonl'
        path = folder/name
        path.write_text(path.read_text()+'\n')  # parse-equivalent bytes, stale receipt
    elif corruption == 'missing_manifest':
        (folder/'artifacts.sha256.json').unlink()
    elif corruption == 'missing_parent':
        (raw/'result.json').unlink()
    fixtures.assert_ineligible(new.validate([raw, raw] if corruption == 'duplicate_map' else [raw]))


@pytest.mark.parametrize('delta,eligible', [(-1e-3, False), (0., False), (1e-3, True)])
def test_one_millisecond_chronology_boundary(target, raw, delta, eligible):
    new, _, fixtures = target
    path = raw/'plan.json'
    plan = fixtures.get(path)
    plan['host_start']['physics_holder']['acquired_unix'] = fixtures.COMMITTED+delta
    fixtures.put(path, plan)
    report = new.validate([raw])
    if eligible:
        assert report['scope'] == 'HELD_OUT_VALIDATION'
        assert report['axis_pass']['forward'] is True
    else:
        fixtures.assert_ineligible(report)
