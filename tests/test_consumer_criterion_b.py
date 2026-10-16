"""Synthetic raw-data acceptance and minimum-noise checks; no physics/inference."""
import ast
import copy
import json
import math
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import fit_consumer_criterion_b as f
from scripts import validate_consumer_criterion_b as b


def synthetic(axis=0, *, gain=1.2, run=.4, stop=.08):
    gate = b.criterion()
    plan = {'control_period_s': .05, 'eval_pose_period_s': .05, 'initial_hold_s': .5,
            'check': 'calibration-unloaded', 'map_id': 'zone_wide_corridor_final_v3', 'segments': []}
    name = b.COMMAND_AXES[axis]
    for value in (.01, -.01, .03, -.03):
        plan['segments'] += [{'axis': name, 'phase': 'step', 'duration_s': 4., 'value': value},
                             {'axis': name, 'phase': 'coast', 'duration_s': 1., 'value': 0.}]
    for value in (.02, .02, -.02, .02, -.02, -.02, .02, -.02):
        plan['segments'].append({'axis': name, 'phase': 'prbs', 'duration_s': .5, 'value': value})
    plan['segments'].append({'axis': name, 'phase': 'coast', 'duration_s': 2.5, 'value': 0.})
    n = round((.5+sum(s['duration_s'] for s in plan['segments']))/.05)
    u, segments = b.plan_arrays(plan, n, .05)
    # Generate via the actual consumer method extracted without its imports.
    tree = ast.parse((b.ROOT/'harness/owncam_localizer.py').read_text())
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'OwnCamLocalizer')
    fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == 'predict_to')
    env = {'np': np, 'math': math, 'STEP_S': .05}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'consumer_method_only', 'exec'), env)
    profile = f.profile(axis, [gain, run, stop], gate)
    pf = SimpleNamespace(t=0., vel=np.zeros(3), initialized=False, cmd_partner=None,
                         _motion_params=lambda: profile)
    poses = [np.zeros(3)]
    for j, command in enumerate(u):
        pf.cmd, pf.cmd_expires = command, (j+1)*.05
        env['predict_to'](pf, (j+1)*.05)
        x, y, yaw = poses[-1]
        vx, vy, w = pf.vel
        poses.append(np.array([x+(math.cos(yaw)*vx-math.sin(yaw)*vy)*.05,
                               y+(math.sin(yaw)*vx+math.cos(yaw)*vy)*.05, yaw+w*.05]))
    data = {'u': u, 'pose': np.array(poses), 'dt': .05, 'segments': segments,
            'map_id': plan['map_id'], 'folder': 'synthetic', 'training': False,
            'pose_sha256': 'synthetic', 'inputs': []}
    candidate = {'criterion_sha256': b.CRITERION_SHA256, 'status': 'CANDIDATE_UNVALIDATED',
                 'candidate_axes': {a: None for a in b.AXES}, 'previously_seen_pose_sha256': []}
    candidate['candidate_axes'][b.AXES[axis]] = {'consumer_fields': profile}
    return data, candidate, plan


def raw_case(tmp_path, axis=0):
    data, candidate, plan = synthetic(axis)
    folder = tmp_path/'case'
    (folder/'eval_only/r1').mkdir(parents=True)
    (folder/'robots/r1').mkdir(parents=True)
    bundle = {'execution_bundle_id': 'zone-final-pair-v88', 'check': 'calibration-unloaded',
              'measurement': plan, 'map_id': plan['map_id'], 'source_sha': '1'*40,
              'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
              'weld': 'off', 'contact_profile': 'cargo_noslip_v1'}
    result = {'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True, 'check_sim_s': len(data['u'])*.05,
              'check': bundle['check'], 'case': {'map_id': plan['map_id']}}
    (folder/'bundle.json').write_text(json.dumps(bundle))
    (folder/'result.json').write_text(json.dumps(result))
    poses = []
    for j, (x, y, yaw) in enumerate(data['pose']):
        co, si = math.cos(yaw), math.sin(yaw)
        poses.append({'t': 1.3+j*.05, 'sample_index': j, 'base_position_m': [x, y, .03],
                      'requested_check': bundle['check'],
                      'base_rotation': [[co, -si, 0.], [si, co, 0.], [0., 0., 1.]]})
    commands = [{'t': 1.3+j*.05, 'kind': 'mecanum', 'duration_s': .05,
                 **dict(zip(b.COMMAND_AXES, command))} for j, command in enumerate(data['u'])]
    for path, records in ((folder/'eval_only/r1/pose.jsonl', poses), (folder/'robots/r1/commands.jsonl', commands)):
        path.write_text(''.join(json.dumps(row)+'\n' for row in records))
    (tmp_path/'result.json').write_text(json.dumps({'status': 'COLLECTED_UNQUALIFIED',
        'denominator': 1, 'unattempted': [], 'source_unchanged': True, 'cases': [result]}))
    return folder, candidate


@pytest.mark.parametrize('axis', [0, 1])
def test_three_parameter_fit_recovers_actual_consumer_method(axis):
    data, _, _ = synthetic(axis)
    fit = f.fit_mean(data, axis, b.criterion())
    np.testing.assert_allclose(list(fit['parameters'].values()), [1.2, .4, .08], rtol=1e-5)
    assert fit['optimizer']['rank'] == 3


@pytest.mark.parametrize('axis', [0, 1, 2])
def test_new_raw_path_scores_signed_axis_without_claiming_acquisition_proof(tmp_path, axis):
    folder, candidate = raw_case(tmp_path, axis)
    cases = b.load_collection(folder, b.criterion())
    report = b.score(cases, candidate, b.criterion())
    assert report['axis_pass'] == dict.fromkeys(b.AXES)
    assert report['cases'][0]['axes'][b.AXES[axis]]['numerical_pass'] is True
    assert report['pass'] is None
    assert report['cases'][0]['scope'] == 'INELIGIBLE'
    assert 'unverified acquisition chronology' in report['cases'][0]['eligibility_reason']
    b.verify_inputs(cases)


def test_cli_synthetic_raw_outputs_null_overall_until_other_axes_validated(tmp_path):
    folder, _ = raw_case(tmp_path)
    output = tmp_path/'result_B.json'
    completed = subprocess.run([sys.executable, '-m', 'scripts.validate_consumer_criterion_b',
                                '--raw', str(folder), '--output', str(output)],
                               cwd=b.ROOT, capture_output=True, text=True)
    assert completed.returncode == 2, completed.stderr
    result = json.loads(output.read_text())
    assert result['axis_pass'] == dict.fromkeys(b.AXES)
    assert result['cases'][0]['axes']['forward']['numerical_pass'] is True
    assert str(tmp_path/'result.json') in {item['path'] for item in result['input_files']}
    assert result['pass'] is None
    assert result['candidate_status'] == 'CANDIDATE_UNVALIDATED'


def test_frozen_noise_floor_matches_the_actual_m1_file():
    gate = b.criterion()
    path = gate['noise']['floor_source'].split(':')[0]
    mp = json.loads((b.ROOT/path).read_bytes())['params']['motion']
    assert gate['noise']['floor_noise_rel'] == mp['noise_rel']
    assert gate['noise']['floor_noise_abs'] == mp['noise_abs']


@pytest.mark.parametrize('corruption', ['missing_pose', 'bad_rotation', 'nonfinite', 'lease', 'missing_command',
                                       'duplicate_command', 'clock', 'incomplete', 'loaded', 'source'])
def test_raw_corruption_fails_closed(tmp_path, corruption):
    folder, _ = raw_case(tmp_path)
    pose_path, command_path = folder/'eval_only/r1/pose.jsonl', folder/'robots/r1/commands.jsonl'
    poses, commands = b.rows(pose_path.read_bytes()), b.rows(command_path.read_bytes())
    if corruption == 'missing_pose':
        poses.pop(25)
    elif corruption == 'bad_rotation':
        poses[25]['base_rotation'][0][0] = 2.
    elif corruption == 'nonfinite':
        poses[25]['base_position_m'][0] = float('nan')
    elif corruption == 'lease':
        commands[25]['duration_s'] = .1
    elif corruption == 'missing_command':
        commands.pop(25)
    elif corruption == 'duplicate_command':
        commands.append(commands[25])
    elif corruption == 'clock':
        commands[25]['t'] += .01
    elif corruption == 'incomplete':
        result = json.loads((folder/'result.json').read_text())
        result['protocol_complete'] = False
        (folder/'result.json').write_text(json.dumps(result))
    else:
        bundle = json.loads((folder/'bundle.json').read_text())
        bundle['check' if corruption == 'loaded' else 'source_sha'] = 'calibration-loaded' if corruption == 'loaded' else None
        (folder/'bundle.json').write_text(json.dumps(bundle))
    pose_path.write_text(''.join(json.dumps(r)+'\n' for r in poses))
    command_path.write_text(''.join(json.dumps(r)+'\n' for r in commands))
    with pytest.raises(ValueError):
        b.load_collection(folder, b.criterion())


@pytest.mark.parametrize('reason', ['v89', 'same_map', 'same_bytes', 'missing_prbs', 'no_candidate', 'short_prbs'])
def test_no_false_heldout_pass(reason):
    data, candidate, _ = synthetic()
    if reason == 'v89':
        data['training'] = True
    elif reason == 'same_map':
        data['map_id'] = b.criterion()['held_out']['training_map']
    elif reason == 'same_bytes':
        candidate['previously_seen_pose_sha256'] = [data['pose_sha256']]
    elif reason == 'missing_prbs':
        data['segments']['forward']['prbs'] = []
    elif reason == 'no_candidate':
        candidate['candidate_axes']['forward'] = None
    else:
        data['segments']['forward']['prbs'] = [(410, 430)]
    report = b.score([data], candidate, b.criterion())
    assert report['axis_pass']['forward'] is None
    assert report['pass'] is None


def test_failed_case_is_not_hidden_by_success_on_another_map():
    data, candidate, _ = synthetic()
    bad = copy.deepcopy(data)
    bad['map_id'] = 'zone_wide_door_geometry_v3'
    bad['pose'][:, 0] *= 10
    report = b.score([data, bad], candidate, b.criterion())
    assert report['cases'][0]['axes']['forward']['numerical_pass'] is True
    assert report['cases'][1]['axes']['forward']['numerical_pass'] is False
    assert report['axis_pass'] == dict.fromkeys(b.AXES) and report['pass'] is None


@pytest.mark.parametrize('decisions, expected', [([True, False], False), ([True, None], None),
                                                ([None, False], False), ([True, True], True)])
def test_decision_aggregation_preserves_failures_and_missing_axes(decisions, expected):
    assert b.combine(decisions) is expected


def test_coverage_nees_and_normalized_p95_rejects_comparing_marginal_quantiles():
    gate = b.criterion()
    sigma = np.r_[np.full(90, .1), np.full(10, 10.)]
    error = np.full((100, 3), .5)
    cov = sigma[:, None, None]**2*np.eye(3)
    result = b.metrics(error, cov, gate)
    assert result['p95_abs_error'][0] < 2*np.percentile(sigma, 95)
    assert result['normalized_abs_error_p95'][0] == 5
    assert result['coverage_2sigma'][0] == .1
    assert not result['numerical_pass']
    assert result['mean_joint_NEES'] > 60


def test_high_coverage_and_small_nees_are_information_only():
    result = b.metrics(np.zeros((50, 3)), np.tile(np.eye(3), (50, 1, 1)), b.criterion())
    assert result['numerical_pass'] and result['coverage_2sigma'] == [1., 1., 1.]
    assert result['mean_joint_NEES'] == 0.


@pytest.mark.parametrize('axis', [0, 1])
def test_quadratic_budget_matches_full_heading_covariance(axis):
    data, candidate, _ = synthetic(axis)
    gate = b.criterion()
    groups = f.noise_groups(data, candidate['candidate_axes'], gate)
    model = candidate['candidate_axes'][b.AXES[axis]]['consumer_fields']
    rel, ab = np.array(model['noise_rel']), np.array([.017, .023, .02])
    model['noise_abs'] = ab.tolist()
    increments = b.c.legacy_increments(data, model)
    for group in groups:
        starts, k = b.c.windows(data['segments'][b.AXES[axis]][group['split']], group['horizon'], data['dt'])
        _, covariance = b.c.legacy_windows(increments, starts, k, data['dt'], model, scale=False)
        expected = data['dt']**2*(rel**2*group['sum_v2']+2*rel*ab*group['sum_v']+k*ab**2)
        expected += group['heading']*ab[2]**2
        np.testing.assert_allclose(expected, np.diagonal(covariance, axis1=1, axis2=2), rtol=1e-11, atol=1e-18)


def test_minimum_noise_is_feasible_and_a_lower_absolute_coefficient_fails():
    data, candidate, _ = synthetic(1)
    data['pose'][:, 1] *= 2.5
    gate = b.criterion()
    result = f.minimum_noise(data, candidate['candidate_axes'], gate)
    np.testing.assert_array_equal(result['noise_rel'], gate['noise']['floor_noise_rel'])
    assert result['noise_abs'][1] > gate['noise']['floor_noise_abs'][1]
    profile = candidate['candidate_axes']['left']['consumer_fields']
    profile['noise_abs'] = result['noise_abs'].copy()
    summary = b.evaluate_axis(data, 1, profile, gate)
    assert min(min(r['coverage_2sigma']) for r in b.all_rows(summary)) >= .95
    profile['noise_abs'][1] = result['certificate']['1']['minimum_without_roundoff_slack']-1e-8
    summary = b.evaluate_axis(data, 1, profile, gate)
    assert min(min(r['coverage_2sigma']) for r in b.all_rows(summary)) < .95


def test_inputs_are_rechecked_after_scoring(tmp_path):
    folder, _ = raw_case(tmp_path)
    cases = b.load_collection(folder, b.criterion())
    (folder/'result.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        b.verify_inputs(cases)


def test_completed_root_cannot_hide_an_unattempted_case(tmp_path):
    raw_case(tmp_path)
    (tmp_path/'result.json').write_text(json.dumps({'status': 'COLLECTED_UNQUALIFIED', 'denominator': 2}))
    with pytest.raises(ValueError, match='denominator'):
        b.load_collection(tmp_path, b.criterion())


@pytest.mark.parametrize('entry', ['root', 'case'])
@pytest.mark.parametrize('corruption', ['missing_root', 'missing_source', 'changed_source',
    'status', 'unattempted', 'missing_cases', 'mismatched_case', 'denominator'])
def test_collection_completion_is_required_even_for_case_selection(tmp_path, entry, corruption):
    folder, _ = raw_case(tmp_path)
    path = tmp_path/'result.json'
    result = json.loads(path.read_text())
    if corruption == 'missing_root':
        path.unlink()
    else:
        if corruption == 'missing_source':
            result.pop('source_unchanged')
        elif corruption == 'changed_source':
            result['source_unchanged'] = False
        elif corruption == 'status':
            result['status'] = 'RUNNING'
        elif corruption == 'unattempted':
            result['unattempted'] = ['missing-case']
        elif corruption == 'missing_cases':
            result.pop('cases')
        elif corruption == 'mismatched_case':
            result['cases'][0]['check_sim_s'] += 1
        else:
            result['denominator'] = 2
        path.write_text(json.dumps(result))
    with pytest.raises(ValueError):
        b.load_collection(folder if entry == 'case' else tmp_path, b.criterion())


@pytest.mark.parametrize('corruption', ['measurement_check', 'measurement_map', 'measurement_load',
    'bundle_case_map', 'result_check', 'result_case_map', 'result_map', 'pose_check', 'pose_map', 'pose_load'])
def test_case_identity_is_checked_independently_of_root_summary(tmp_path, corruption):
    folder, _ = raw_case(tmp_path)
    if corruption.startswith(('measurement', 'bundle')):
        path = folder/'bundle.json'
        data = json.loads(path.read_text())
        if corruption == 'measurement_check':
            data['measurement']['check'] = 'calibration-loaded'
        elif corruption == 'measurement_map':
            data['measurement']['map_id'] = 'wrong-map'
        elif corruption == 'measurement_load':
            data['measurement']['load_state'] = 'loaded'
        else:
            data['case'] = {'map_id': 'wrong-map'}
        path.write_text(json.dumps(data))
    elif corruption.startswith('result'):
        path = folder/'result.json'
        data = json.loads(path.read_text())
        if corruption == 'result_check':
            data['check'] = 'calibration-loaded'
        elif corruption == 'result_case_map':
            data['case']['map_id'] = 'wrong-map'
        else:
            data['map_id'] = 'wrong-map'
        path.write_text(json.dumps(data))
    else:
        path = folder/'eval_only/r1/pose.jsonl'
        data = b.rows(path.read_bytes())
        if corruption == 'pose_check':
            data[25].pop('requested_check')
        elif corruption == 'pose_map':
            data[25]['map_id'] = 'wrong-map'
        else:
            data[25]['load_state'] = 'loaded'
        path.write_text(''.join(json.dumps(row)+'\n' for row in data))
    with pytest.raises(ValueError, match='identity|condition'):
        b.load_case(folder, b.criterion())


def test_uncommanded_initial_hold_is_allowed_but_first_coast_tick_is_required(tmp_path):
    folder, _ = raw_case(tmp_path)
    path = folder/'robots/r1/commands.jsonl'
    commands = b.rows(path.read_bytes())[10:]
    path.write_text(''.join(json.dumps(row)+'\n' for row in commands))
    b.load_collection(folder, b.criterion())
    assert commands[80]['forward'] == 0.
    commands.pop(80)
    path.write_text(''.join(json.dumps(row)+'\n' for row in commands))
    with pytest.raises(ValueError, match='missing scheduled command ticks'):
        b.load_collection(folder, b.criterion())


@pytest.mark.parametrize('entry', ['root', 'case'])
@pytest.mark.parametrize('change', ['modify', 'delete'])
def test_root_completion_is_in_manifest_and_rechecked(tmp_path, entry, change):
    folder, _ = raw_case(tmp_path)
    cases = b.load_collection(folder if entry == 'case' else tmp_path, b.criterion())
    path = tmp_path/'result.json'
    items = {item['path']: item for case in cases for item in case['inputs']}
    assert items[str(path)]['sha256'] == b.sha(path.read_bytes())
    if change == 'delete':
        path.unlink()
    else:
        path.write_text('{}')
    with pytest.raises(ValueError, match='input (changed|missing)'):
        b.verify_inputs(cases)


def test_review_counterexamples_are_in_ci_collection():
    from scripts import run_ci_tests as runner
    assert 'tests/test_review_346.py' in runner.collect_test_files(runner.ROOT, runner.TEST_PATTERNS)


def test_published_freeze_candidate_and_criterion_a_are_preserved():
    b.criterion()
    candidate = json.loads(b.CANDIDATE.read_bytes())
    report = json.loads((b.FOLDER/'consumer_report_r4.json').read_bytes())
    assert b.sha(b.CANDIDATE.read_bytes()) == report['candidate_sha256']
    assert candidate['status'] == 'CANDIDATE_UNVALIDATED'
    assert candidate['params']['motion'] is None
    assert candidate['candidate_axes']['rotate'] is None
    assert candidate['axis_validation'] == dict.fromkeys(b.AXES)
    assert report['axis_pass'] == dict.fromkeys(b.AXES)
    assert report['cases'][0]['scope'] == 'TRAINING_SMOKE'
    for path in ('calibration_partial.json', 'calibration_partial_r2.json', 'calibration_partial_r3.json',
                 'consumer_criterion_r3.json', 'consumer_report_r3.json'):
        frozen = subprocess.check_output(['git', 'show', f'bedcc99d:{b.RECORD}/{path}'], cwd=b.ROOT)
        assert frozen == (b.FOLDER/path).read_bytes()
    for model in candidate['candidate_axes'].values():
        if model is not None:
            assert model['minimum_training_2sigma_coverage'] >= .95
            assert model['validation'] is None


def test_current_loader_rejects_candidate_status():
    from harness.zone_final_environment import measured_calibration
    with pytest.raises(ValueError, match='combination mismatch'):
        measured_calibration(b.CANDIDATE, b.sha(b.CANDIDATE.read_bytes()), 'zone_wide_corridor_final_v3')
