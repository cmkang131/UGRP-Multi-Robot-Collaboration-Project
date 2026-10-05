"""Independent PR #346 / 65ce28cf offline review; no physics or rendering.

Run with UGRP_REVIEW_346_ROOT pointing to an archive of the reviewed source.
The seven review counterexamples are ordinary regression tests after R1-R4
were fixed. Synthetic data remains diagnostics, never held-out evidence.
"""
from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import socket
import sys

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))


@pytest.fixture
def target(monkeypatch):
    root = Path(os.environ.get('UGRP_REVIEW_346_ROOT', Path(__file__).resolve().parents[1])).resolve()
    if not (root/'scripts/validate_consumer_criterion_b.py').is_file():
        pytest.fail('PR #346 source absent; set UGRP_REVIEW_346_ROOT to its archive')
    monkeypatch.syspath_prepend(str(root))
    module = importlib.import_module('scripts.validate_consumer_criterion_b')
    assert Path(module.__file__).resolve().is_relative_to(root)
    return module


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False)+'\n')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row, allow_nan=False)+'\n' for row in rows))


def raw_case(root, b):
    """Independent Euler trajectory of the published forward candidate.

    This is synthetic data, not new held-out evidence. It deliberately has no
    acquisition-time receipt; the reviewer never promotes it to validation.
    """
    candidate = json.loads(b.CANDIDATE.read_bytes())
    profile = candidate['candidate_axes']['forward']['consumer_fields']
    dt = .05
    segments = []
    for value in (.03, -.03):
        segments += [dict(axis='forward', phase='step', value=value, duration_s=4.),
                     dict(axis='forward', phase='coast', value=0., duration_s=1.)]
    segments += [dict(axis='forward', phase='prbs', value=value, duration_s=.5)
                 for value in (.02, -.02, .02, .02, -.02, -.02, .02, -.02)]
    segments.append(dict(axis='forward', phase='coast', value=0., duration_s=2.5))
    commands = [0.]*10
    for segment in segments:
        commands += [segment['value']]*round(segment['duration_s']/dt)
    folder = root/'case'
    (folder/'eval_only/r1').mkdir(parents=True)
    (folder/'robots/r1').mkdir(parents=True)
    mid = 'zone_wide_corridor_final_v3'
    plan = dict(check='calibration-unloaded', map_id=mid, initial_hold_s=.5,
                control_period_s=dt, eval_pose_period_s=dt, sim_cap_s=len(commands)*dt,
                segments=segments)
    bundle = dict(execution_bundle_id='zone-final-pair-v88', check='calibration-unloaded',
                  measurement=plan, map_id=mid, source_sha='1'*40,
                  robot_model='masterpi_v3', render_profile='floor_light_v1',
                  weld='off', contact_profile='cargo_noslip_v1')
    result = dict(status='COLLECTED_UNQUALIFIED', protocol_complete=True,
                  check='calibration-unloaded', case=dict(map_id=mid),
                  check_sim_s=len(commands)*dt)
    write_json(folder/'bundle.json', bundle)
    write_json(folder/'result.json', result)
    x = v = 0.
    poses = []
    for j in range(len(commands)+1):
        poses.append(dict(t=1.3+j*dt, sample_index=j, base_position_m=[x, 0., .03],
                          base_rotation=np.eye(3).tolist(), requested_check='calibration-unloaded'))
        if j < len(commands):
            u = commands[j]
            tau = profile['tau_s'] if u else profile['tau_stop_s']
            v += (1-math.exp(-dt/tau))*(profile['gain'][0][0]*u-v)
            x += v*dt
    write_rows(folder/'eval_only/r1/pose.jsonl', poses)
    issued = [dict(t=1.3+j*dt, kind='mecanum', duration_s=dt, forward=u, left=0., turn=0.)
              for j,u in enumerate(commands)]
    write_rows(folder/'robots/r1/commands.jsonl', issued)
    write_json(root/'result.json', dict(status='COLLECTED_UNQUALIFIED', denominator=1,
                                      unattempted=[], source_unchanged=True, cases=[result]))
    return folder, candidate


@pytest.mark.parametrize('component', [0, 1, 2])
@pytest.mark.parametrize('value,expected', [(2., True), (2.+1e-10, False)])
def test_all_components_use_inclusive_normalized_p95_boundary(target, component, value, expected):
    error = np.zeros((100, 3))
    error[:, component] = value
    result = target.metrics(error, np.tile(np.eye(3), (100, 1, 1)), target.criterion())
    assert result['component_pass'][component] is expected
    assert result['numerical_pass'] is expected
    assert result['mean_NEES_per_component'][component] == pytest.approx(value**2)


def test_linear_percentile_and_informational_nees(target):
    error = np.zeros((100, 3)); error[-5:] = 40.
    result = target.metrics(error, np.tile(np.eye(3), (100, 1, 1)), target.criterion())
    # NumPy linear interpolation is intentionally part of frozen criterion B.
    assert result['normalized_abs_error_p95'][0] == pytest.approx(2.)
    assert result['coverage_2sigma'] == [.95]*3
    assert result['mean_joint_NEES'] == 240.
    # Decimal interpolation can round above 2; test the exact result rather
    # than introducing an unregistered tolerance into B.
    assert result['numerical_pass'] == bool(np.percentile(error[:, 0], 95) <= 2.)


@pytest.mark.parametrize('count,expected', [(10, True), (9, False)])
def test_ninety_percent_coverage_boundary_independent_of_p95(target, count, expected):
    error = np.zeros((count, 3)); error[-1] = 3.
    result = target.metrics(error, np.tile(np.eye(3), (count, 1, 1)), target.criterion())
    assert max(result['normalized_abs_error_p95']) < 2.
    assert result['coverage_2sigma'] == [(count-1)/count]*3
    assert result['numerical_pass'] is expected


def test_synthetic_windows_retain_every_horizon_and_null_axes(target, tmp_path):
    folder, candidate = raw_case(tmp_path, target)
    cases = target.load_collection(folder, target.criterion())
    # Numerical smoke only: synthetic rows are never validation evidence.
    cases[0]['training'] = True
    report = target.score(cases, candidate, target.criterion())
    assert report['axis_pass'] == dict.fromkeys(('forward', 'left', 'rotate'))
    assert report['pass'] is None
    assert report['cases'][0]['axes']['forward']['numerical_pass'] is True
    for split in ('steps', 'prbs'):
        metrics = report['cases'][0]['axes']['forward']['metrics'][split]
        assert set(metrics) == {'0.2', '0.5', '1.0', '2.0', '3.0', '3.2'}
        assert all(row['n'] > 0 and row['component_pass'] == [True]*3 for row in metrics.values())
    assert report['cases'][0]['scope'] == 'TRAINING_SMOKE'


def test_unverified_acquisition_chronology_cannot_validate(target, tmp_path):
    folder, candidate = raw_case(tmp_path, target)
    report = target.score(target.load_collection(folder, target.criterion()), candidate, target.criterion())
    assert report['cases'][0]['axes']['forward']['numerical_pass'] is True
    assert 'unverified acquisition chronology' in report['cases'][0]['eligibility_reason']
    assert report['axis_pass']['forward'] is None
    assert report['cases'][0]['scope'] != 'HELD_OUT'


@pytest.mark.parametrize('contradiction', ['result_check', 'result_map', 'pose_check'])
def test_contradictory_raw_identity_is_rejected(target, tmp_path, contradiction):
    folder, _ = raw_case(tmp_path, target)
    if contradiction == 'pose_check':
        path = folder/'eval_only/r1/pose.jsonl'
        rows = target.rows(path.read_bytes())
        for row in rows:
            row['requested_check'] = 'calibration-loaded'
        write_rows(path, rows)
    else:
        path = folder/'result.json'
        result = json.loads(path.read_bytes())
        if contradiction == 'result_check':
            result['check'] = 'calibration-loaded'
        else:
            result['case']['map_id'] = 'zone_wide_two_doors_final_v3'
        write_json(path, result)
    with pytest.raises(ValueError):
        target.load_collection(folder, target.criterion())


def test_case_path_cannot_bypass_failed_collection_root(target, tmp_path):
    folder, _ = raw_case(tmp_path, target)
    write_json(tmp_path/'result.json', dict(status='HOST_ERROR', source_unchanged=False, denominator=1))
    with pytest.raises(ValueError):
        target.load_collection(tmp_path, target.criterion())
    with pytest.raises(ValueError):
        target.load_collection(folder, target.criterion())


def test_missing_scheduled_zero_commands_are_not_invented(target, tmp_path):
    folder, _ = raw_case(tmp_path, target)
    path = folder/'robots/r1/commands.jsonl'
    rows = target.rows(path.read_bytes())
    # Keep the initial hold; remove the commands explicitly scheduled as coast.
    kept = [row for j,row in enumerate(rows) if j < 10 or row['forward'] != 0.]
    assert len(rows)-len(kept) == 90
    write_rows(path, kept)
    with pytest.raises(ValueError):
        target.load_collection(folder, target.criterion())


def test_collection_completion_change_is_detected(target, tmp_path):
    raw_case(tmp_path, target)
    cases = target.load_collection(tmp_path, target.criterion())
    write_json(tmp_path/'result.json', dict(status='HOST_ERROR', source_unchanged=False, denominator=1))
    with pytest.raises(ValueError):
        target.verify_inputs(cases)
