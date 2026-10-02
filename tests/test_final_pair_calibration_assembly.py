"""Synthetic v88 raw and fail-closed loader tests, no physics/render/model."""
import copy
import hashlib
import io
import json
import math
import os
import socket
import sys

import numpy as np
from PIL import Image
import pytest

from harness import zone_final_pair_contract as contract
from harness.zone_final_pair_calibration import schedule
from harness.zone_final_pair_camera import measurement_label
from harness.zone_final_pair_excitation import MAP_ID
from scripts import assemble_final_pair_calibration as a
from scripts import final_pair_calibration_camera as camera
from scripts import final_pair_calibration_io as raw
from scripts import final_pair_calibration_motion as motion
from scripts import validate_consumer_criterion_b as b


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('network forbidden'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))


def rows(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in value))


def refresh_manifest(folder):
    write(folder/'artifacts.sha256.json', {str(p.relative_to(folder)): raw.file_sha(p)
        for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})


def rz(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


def synthetic_data(profile='fine', *, loaded=False):
    from harness.zone_final_pair_excitation import design
    u, segments, _ = raw.plan_arrays(design('calibration-'+profile))
    fields = {'gain': np.diag([1.2, .85, 1.4]).tolist(), 'tau_s': .4, 'tau_axis_s': [.4, .7, .2],
              'tau_stop_s': .08, 'noise_rel': b.criterion()['noise']['floor_noise_rel'],
              'noise_abs': b.criterion()['noise']['floor_noise_abs'], 'scale_std': 0., 'scale_walk': 0.,
              'use_scale': False, 'rest_noise': True}
    if loaded:
        fields['deadband'] = {'c0': [.01]*3, 'u1': [.032]*3}
    data = {'u': u, 'dt': .05, 'segments': segments}
    data['pose'] = motion.path_of(motion.increments(data, fields))
    return data, fields


def synthetic_collection(tmp_path, profile):
    """Same paths, command order, shapes and sample clocks as v88 backend.

    JPEGs are synthetic bytes; hardlinks keep the full 1851x2 raw fixture
    small. No simulation or rendering is used to make the numerical arrays.
    """
    root = tmp_path/('calibration-'+profile)
    folder = root/MAP_ID
    data, fields = synthetic_data(profile, loaded=profile == 'loaded')
    bundle = {**contract.bundle(MAP_ID, 'calibration-'+profile),
              'source_sha': 'a'*40, 'case': contract.cases('calibration-'+profile)[0]}
    result = {'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True, 'check_sim_s': 370.,
        'check': bundle['check'], 'case': bundle['case'], 'collection_data_status': 'UNQUALIFIED',
        'partial_data_retained': False, 'physical_success': None, 'research_result': False,
        'student_control': False, 'failure': None, 'timing': bundle['timing'],
        'reset_sim_s': 1.3, 'reset_sim_cap_s': 5., 'check_sim_cap_s': 370.}
    write(root/'result.json', {'status': 'COLLECTED_UNQUALIFIED', 'denominator': 1,
        'source_unchanged': True, 'unattempted': [], 'cases': [result], 'physical_success': None, 'research_result': False})
    write(folder/'result.json', result)
    write(folder/'bundle.json', bundle)
    write(root/'plan.json', {'execution_bundle_id': contract.BUNDLE_ID, 'check': bundle['check'],
        'status': 'DRAFT_UNSEALED', 'execution_started': False, 'cases': [bundle['case']], 'denominator': 1,
        'runnable': True, 'blocked_on': [], 'source_sha': bundle['source_sha'], 'seed': 911,
        'bundles_sha256': [contract.base.digest(bundle)], 'physical_success': None,
        'clearance_preflight': [bundle['clearance_preflight']]})
    write(folder/'inputs/static_map.json', contract.resolve(MAP_ID)[0])
    events = schedule(bundle['check'])
    write(folder/'inputs/schedule.json', events)
    # Record the beam box's body-local offset, as real cargo XML does.
    (folder/'scene.xml').write_text('<mujoco><worldbody><body name="cargo_beam"><geom name="cargo_beam_bar" type="box" size=".3 .02 .02" pos="0 0 .02"/></body></worldbody></mujoco>')
    jpeg = io.BytesIO()
    Image.fromarray(np.full((480, 640, 3), 200, np.uint8)).save(jpeg, format='JPEG')
    image_bytes = jpeg.getvalue()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    for rid in contract.ROBOTS:
        u = data['u'].copy() if rid == 'r1' else (-data['u'] if profile == 'loaded' else np.zeros_like(data['u']))
        pose = motion.path_of(motion.increments({**data, 'u': u}, fields))
        if rid == 'r2':
            pose[:, :2] *= -1
            pose[:, 2] += np.pi
        pose[:, :2] += [3.25 if rid == 'r1' else 3.95, -.85]
        poses = [{'t': round(1.3+j*.05, 8), 'sample_index': j, 'base_position_m': [x, y, .033],
                  'base_rotation': rz(yaw).tolist(), 'requested_check': bundle['check'],
                  'wall_clearance_lower_bound_m': .8, 'qualification': 'synthetic eval_only'}
                 for j, (x, y, yaw) in enumerate(pose)]
        rows(folder/f'eval_only/{rid}/pose.jsonl', poses)
        initial = {1: 2000, 2: 1500, 3: 740, 4: 2320, 5: 1320, 6: 1500}
        commands = [{'t': 1.3, 'kind': 'initial_servo_command', 'pulses': initial}]
        commands += [{'t': round(1.3+e['t'], 8), **e['action']} for e in events if e['robot_id'] == rid]
        rows(folder/f'robots/{rid}/commands.jsonl', commands)
        frames, labels, ci, servo = [], [], 1, dict(initial)
        first_image = None
        for j in range(1851):
            t = round(1.3+j*.2, 8)
            while ci < len(commands) and commands[ci]['t'] < t-1e-7:
                cmd = commands[ci]
                if cmd['kind'] == 'arm': servo[cmd['servo_id']] = cmd['pulse']
                if cmd['kind'] == 'look': servo[6] = cmd['pan_pulse']
                ci += 1
            path = f'robots/{rid}/rgb/{j:05d}.jpg'
            image_path = folder/path
            image_path.parent.mkdir(parents=True, exist_ok=True)
            if first_image is None:
                image_path.write_bytes(image_bytes)
                first_image = image_path
            else:
                os.link(first_image, image_path)
            commanded = {str(k): v for k, v in servo.items()}
            frame = {'t': t, 'frame_id': f'{rid}:{j}', 'sha256': image_hash, 'path': path,
                     'commanded_servo': commanded, 'width': 640, 'height': 480}
            base = poses[j*4]
            rb = np.asarray(base['base_rotation'])
            pc = np.asarray(base['base_position_m'])+rb @ np.array([.15, 0., .2])
            label = measurement_label(base['base_position_m'], rb, pc, rb @ np.diag([1., -1., -1.]))
            frames.append(frame)
            labels.append({'t': t, 'frame_id': frame['frame_id'], 'sha256': image_hash,
                'commanded_servo': commanded, **label, **{k:base[k] for k in ('base_position_m', 'base_rotation')},
                'requested_check': bundle['check'], 'load_validity': 'UNCLASSIFIED; synthetic test only'})
        rows(folder/f'robots/{rid}/frames.jsonl', frames)
        rows(folder/f'eval_only/{rid}/camera_labels.jsonl', labels)
    contacts = [{'geom1': 'cargo_beam_bar', 'geom2': f'{rid}__{side}_finger', 'dist_m': -.001}
                for rid in contract.ROBOTS for side in ('left', 'right')]
    rows(folder/'eval_only/contacts.jsonl', [{'t': round(1.3+j*.05, 8), 'contacts': contacts,
        'active_weld_ids': []} for j in range(7401)])
    rows(folder/'eval_only/trajectory.jsonl', [{'t': round(1.3+j*.05, 8), 'beam_xyz_m': [3.55, -.85, .1],
        'beam_rotation': np.eye(3).ravel().tolist(), 'qpos': [], 'qvel': [], 'physical_success': None} for j in range(7401)])
    refresh_manifest(folder)
    return root


@pytest.fixture(scope='module')
def unloaded_raw(tmp_path_factory):
    return synthetic_collection(tmp_path_factory.mktemp('v88-synthetic-raw'), 'unloaded')


def test_frozen_prime_contains_exact_B_and_predeclared_split():
    assert raw.file_sha(a.CRITERION) == a.CRITERION_SHA256
    prime = json.loads(a.CRITERION.read_text())
    assert prime['parent_text'] == b.criterion()
    assert prime['split']['fit'].startswith('Every signed step')
    assert prime['split']['validate'].startswith('Continuous PRBS')
    assert a.CRITERION_SHA256 in (a.RECORD/'README.md').read_text()


def test_full_runner_shaped_raw_audit_and_frozen_unloaded_gate(unloaded_raw):
    inputs = raw.Inputs()
    data = raw.load_collection(unloaded_raw, 'unloaded', inputs)
    assert len(data['robots']['r1']['pose']) == 7401
    assert len(data['robots']['r2']['frames']) == 1851
    candidate = json.loads(b.CANDIDATE.read_text())
    score = b.score(b.load_collection(unloaded_raw, b.criterion()), candidate, b.criterion())
    assert score['pass'] is None
    assert score['cases'][0]['scope'] == 'INELIGIBLE'
    assert score['axis_pass']['rotate'] is None
    inputs.verify()


def test_unfinished_collection_is_not_read(tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail('unfinished raw must not be read')
    monkeypatch.setattr(raw.Inputs, 'read', forbidden)
    with pytest.raises(ValueError, match='completion record'):
        raw.load_collection(tmp_path, 'fine', raw.Inputs())


def test_input_changes_fail_closed(tmp_path):
    p = tmp_path/'input'
    p.write_bytes(b'one')
    inputs = raw.Inputs()
    inputs.read(p)
    p.write_bytes(b'two')
    with pytest.raises(ValueError, match='changed'):
        inputs.verify()


@pytest.mark.parametrize('kind', ['collection', 'case', 'file'])
@pytest.mark.parametrize('relation', ['same', 'child', 'parent'])
def test_all_resolved_input_paths_reject_overlapping_outputs(tmp_path, kind, relation):
    target = tmp_path/'external'/kind
    target.parent.mkdir()
    if kind == 'file':
        target.write_text('input bytes')
    else:
        target.mkdir()
    alias = tmp_path/'link'
    alias.symlink_to(target, target_is_directory=kind != 'file')
    inputs = raw.Inputs()
    if kind == 'file':
        inputs.read(alias)
    else:
        inputs.protect(alias)
    output = {'same': target, 'child': target/'new', 'parent': target.parent}[relation]
    with pytest.raises(ValueError, match='separate from every input'):
        inputs.reject_output_overlap(output)
    inputs.reject_output_overlap(tmp_path/'unrelated-new-output')


def test_output_check_resolves_retargeted_input_alias(tmp_path):
    original, moved = tmp_path/'original', tmp_path/'moved'
    original.mkdir()
    moved.mkdir()
    alias = tmp_path/'alias'
    alias.symlink_to(original, target_is_directory=True)
    inputs = raw.Inputs()
    inputs.protect(alias)
    alias.unlink()
    alias.symlink_to(moved, target_is_directory=True)
    for target in (original, moved):
        with pytest.raises(ValueError, match='overlaps'):
            inputs.reject_output_overlap(target/'new')


def test_incomplete_collection_and_case_links_are_protected_before_output(tmp_path):
    root, target = tmp_path/'collection', tmp_path/'external-case'
    root.mkdir()
    target.mkdir()
    (root/MAP_ID).symlink_to(target, target_is_directory=True)
    inputs = raw.Inputs()
    with pytest.raises(ValueError, match='completion record'):
        raw.load_collection(root, 'loaded', inputs)
    for output in (root/'new', target/'new'):
        with pytest.raises(ValueError, match='overlaps'):
            inputs.reject_output_overlap(output)
        assert not output.exists()


def test_b_prime_motion_fit_and_heldout_independence():
    data, actual = synthetic_data()
    profile, report = motion.fit_profile([data], b.criterion())
    assert report['accepted']
    for key in ('gain', 'tau_axis_s', 'tau_stop_s'):
        np.testing.assert_allclose(profile[key], actual[key], atol=2e-6)
    contaminated = copy.deepcopy(data)
    for split in data['segments'].values():
        for start, end in split['prbs']:
            contaminated['pose'][start:end+1, 0] += np.linspace(0, 1., end-start+1)
    fitted, optimizer = motion.fit_shared([contaminated], b.criterion())
    for key in ('gain', 'tau_axis_s', 'tau_stop_s'):
        np.testing.assert_allclose(fitted[key], actual[key], atol=2e-6)
    result = motion.evaluate(contaminated, profile, b.criterion(), 'prbs')
    assert not all(row['numerical_pass'] for axis in result.values() for row in b.all_rows(axis))


def test_rotation_covariance_polynomial_matches_existing_consumer():
    data, profile = synthetic_data()
    # Nonzero cross error and rotating mean stress covariance propagation.
    sample_gate = {**b.criterion(), 'horizons_s': [.2, 3.2]}
    groups = list(motion.budget_groups(motion.split_data(data, 'prbs'), profile, sample_gate))
    delta = motion.increments(data, profile)
    for group in groups:
        spans = data['segments'][group['axis']]['prbs']
        starts, k = b.c.windows(spans, group['horizon'], .05)
        predicted, cov = b.c.legacy_windows(delta, starts, k, .05, profile, scale=False)
        ab = np.asarray(profile['noise_abs'])
        variance = group['fixed']+np.sum(group['quad']*ab**2+group['linear']*ab, axis=2)
        np.testing.assert_allclose(variance, np.diagonal(cov, axis1=1, axis2=2), rtol=1e-10, atol=1e-15)
        np.testing.assert_allclose(group['error'], predicted-b.c.endpoint_targets(data['pose'], starts, k), atol=1e-12)


def test_loaded_ramp_fit_recovers_measured_parameters():
    data, actual = synthetic_data('loaded', loaded=True)
    profile, report = motion.fit_shared([data], b.criterion(), deadband=True)
    assert report['success']
    assert len(report['deadband_support']) == 1
    for key in ('gain', 'tau_axis_s', 'tau_stop_s', 'deadband'):
        if key == 'deadband':
            for sub in ('c0', 'u1'):
                np.testing.assert_allclose(profile[key][sub], actual[key][sub], atol=2e-6)
        else:
            np.testing.assert_allclose(profile[key], actual[key], atol=2e-6)


@pytest.mark.parametrize('axis', range(3))
@pytest.mark.parametrize('command', [-.006, .006, -.015, .015, -.025, .025, -.04, .04])
def test_loaded_fit_rejects_each_missing_signed_level_after_load_selection(axis, command):
    data, _ = synthetic_data('loaded', loaded=True)
    valid = np.ones(len(data['pose']), bool)
    for start, end in data['segments'][b.AXES[axis]]['steps']:
        removed = np.flatnonzero(data['u'][start:end, axis] == command) + start
        valid[removed] = False
    data['segments'] = raw.selected_segments(data['segments'], valid)
    # Other magnitudes/signs and PRBS survive; neither rank nor coast is support.
    with pytest.raises(ValueError, match='loaded deadband support missing signed'):
        motion.fit_shared([data], b.criterion(), deadband=True)


def test_loaded_support_requires_real_fit_windows_and_each_robot():
    data, _ = synthetic_data('loaded', loaded=True)
    damaged = copy.deepcopy(data)
    valid = np.ones(len(data['pose']), bool)
    for start, end in damaged['segments']['forward']['steps']:
        if damaged['u'][start, 0] == .006:
            valid[start+1:end] = False
    damaged['segments'] = raw.selected_segments(damaged['segments'], valid)
    with pytest.raises(ValueError, match='forward: loaded deadband support'):
        motion.fit_shared([data, damaged], b.criterion(), deadband=True)


@pytest.mark.parametrize('record', ['trajectory.jsonl', 'contacts.jsonl'])
@pytest.mark.parametrize('time', [float('nan'), float('inf'), -float('inf'), '1.3', None, True])
def test_loaded_clock_requires_finite_numbers(unloaded_raw, record, time):
    data = raw.load_collection(unloaded_raw, 'unloaded', raw.Inputs())
    class InvalidTime(raw.Inputs):
        def rows(self, path):
            rows = super().rows(path)
            if path.name == record:
                rows[0]['t'] = time
            return rows
    with pytest.raises(ValueError, match='finite numeric time'):
        raw.loaded_mask(data, InvalidTime(), json.loads(a.CRITERION.read_text())['loaded_selection'])


def test_review_351_regressions_are_in_ci_once():
    from scripts import run_ci_tests as runner
    files = runner.collect_test_files(runner.ROOT, runner.TEST_PATTERNS)
    assert files.count('tests/test_review_351.py') == 1


def test_noise_inflation_covers_training_and_lower_value_fails():
    data, profile = synthetic_data()
    data['pose'][:, 1] += np.arange(7401)*.05*.004
    gate = b.criterion()
    groups = list(motion.budget_groups(motion.split_data(data, 'steps'), profile, gate))
    absolute, certificate = motion.minimum_noise(groups, gate)
    assert absolute[1] > profile['noise_abs'][1]
    profile['noise_abs'] = absolute
    report = motion.evaluate(data, profile, gate, 'steps')
    assert all(min(row['coverage_2sigma']) >= .95 for axis in report.values() for row in b.all_rows(axis))
    smaller = np.asarray(absolute).copy()
    smaller[1] -= 1e-5
    coverage = []
    for group in groups:
        variance = group['fixed']+np.sum(group['quad']*smaller**2+group['linear']*smaller, axis=2)
        coverage.extend(np.mean(group['error']**2 <= 4*variance, axis=0))
    assert min(coverage) < .95


def test_loaded_spread_recovers_constant_yaw_rate_bias():
    data, profile = synthetic_data('loaded', loaded=True)
    data['pose'][:, 2] += np.arange(7401)*.05*.001
    spread, report = motion.fit_spread([data], profile, b.criterion())
    assert report['accepted']
    assert spread['yaw_bias_std_rad_s'] == pytest.approx(.001, abs=1e-9)
    assert len(spread['load_transition']['scale_std']) == 3
    assert np.isfinite(spread['drift_ratio_std'])


def test_loaded_contact_height_and_weld_selection(unloaded_raw, tmp_path):
    inputs = raw.Inputs()
    data = raw.load_collection(unloaded_raw, 'unloaded', inputs)
    gate = json.loads(a.CRITERION.read_text())['loaded_selection']
    valid, counts = raw.loaded_mask(data, inputs, gate)
    assert valid.all() and counts == {'lifted': 7401}
    # Change only in-memory read results, preserving fixture bytes.
    class Modified(raw.Inputs):
        def rows(self, path):
            rs = super().rows(path)
            if path.name == 'trajectory.jsonl': rs[10]['beam_xyz_m'][2] = 0.
            if path.name == 'contacts.jsonl': rs[20]['contacts'] = rs[20]['contacts'][:-1]
            return rs
    valid, counts = raw.loaded_mask(data, Modified(), gate)
    assert not valid[10] and not valid[20] and valid[9]
    selected = raw.selected_segments({'forward': {'steps': [(0, 30)], 'prbs': []}}, valid)
    assert selected['forward']['steps'] == [(0, 9), (11, 19), (21, 30)]
    class Weld(raw.Inputs):
        def rows(self, path):
            rs = super().rows(path)
            if path.name == 'contacts.jsonl': rs[30]['active_weld_ids'] = [0]
            return rs
    with pytest.raises(ValueError, match='weld'):
        raw.loaded_mask(data, Weld(), gate)


def complete_sections():
    _, p = synthetic_data()
    rec = {'frame': 'optical_to_actual_chassis', 'origin_m': [.15, 0., .2], 'rotation': np.eye(3).tolist(),
           'chassis_to_floor': {'origin_m': [0., 0., .033], 'rotation': np.eye(3).tolist()}}
    sections = {prefix: {'value': copy.deepcopy(p), 'accepted': True} for prefix in a.MOTION.values()}
    loaded = sections[a.MOTION['loaded']]['value']
    loaded.update(deadband={'c0': [.01]*3, 'u1': [.03]*3}, load_transition={'scale_std': [.01, .02, 0.],
        'unloaded_scale_std': 0.}, drift_ratio_std=.01, yaw_bias_std_rad_s=.02)
    sections[('pair_model',)] = {'accepted': True, 'value': {'slope_to_yaw_ratio': 1.,
        'b_rad_s': dict.fromkeys(('', 'pm', 'edge', 'pm+edge'), .01)}}
    for state, poses in a.required_camera_poses().items():
        for pose in poses:
            sections[('camera_models', state, a.camera_key(pose))] = {'accepted': True, 'value': copy.deepcopy(rec)}
        sections[('pan_base_yaw', state)] = {'accepted': True, 'value': 0.}
    metadata = {'source_sha': 'a'*40, 'measurement_manifest_sha256': 'b'*64,
        'contract_sha256': contract.base.sha(a.ROOT/contract.CALIBRATION_CONTRACT),
        'maps': contract.resolve(MAP_ID)[2]['maps'], 'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1'}
    return metadata, sections


def test_complete_synthetic_assembly_accepted_by_all_three_loader_maps(tmp_path):
    metadata, sections = complete_sections()
    cal = a.assemble(metadata, sections)
    assert cal['status'] == 'MEASURED_SIM' and not cal['missing']
    path = tmp_path/'SYNTHETIC-TEST-ONLY.json'
    write(path, cal)
    for mid in metadata['maps']:
        assert contract.measured_calibration(path, raw.file_sha(path), mid) == cal


@pytest.mark.parametrize('path', a.required_fields(), ids=a.label)
def test_every_required_field_missing_fails_closed(path):
    metadata, sections = complete_sections()
    sections[path] = {'value': None, 'accepted': False, 'reason': 'synthetic missing measurement'}
    cal = a.assemble(metadata, sections)
    assert cal['status'] == 'PARTIAL'
    assert cal['missing'] == [{'field': a.label(path), 'reason': 'synthetic missing measurement'}]


def test_unaccepted_and_nonfinite_fields_never_promote():
    metadata, sections = complete_sections()
    sections[a.MOTION['fine']]['accepted'] = False
    assert a.assemble(metadata, sections)['status'] == 'PARTIAL'
    metadata, sections = complete_sections()
    sections[('pair_model',)]['value']['slope_to_yaw_ratio'] = float('nan')
    cal = a.assemble(metadata, sections)
    assert cal['status'] == 'PARTIAL'
    assert cal['missing'][0]['field'] == 'pair_model.slope_to_yaw_ratio'
    json.dumps(cal, allow_nan=False)


def test_pair_four_variants_recovery_and_unexcited_rejection():
    gate = json.loads(a.CRITERION.read_text())['pair_model']
    data = [{'split': split, 'cell': str(i), 'T': 10., 'g': .03, 'ms': .01, 'mp': -.01,
             'd_rel_gt': .005*(i+1), 'd_slope_total': .005*(i+1)*1.2}
            for split in ('steps', 'prbs') for i in range(4)]
    fit, report = camera.fit_pair(data, gate)
    assert report['accepted'] and fit['slope_to_yaw_ratio'] == pytest.approx(1.2)
    assert set(fit['b_rad_s']) == {'', 'pm', 'edge', 'pm+edge'}
    for row in data: row['d_rel_gt'] = 0.
    with pytest.raises(ValueError, match='unexcited'):
        camera.fit_pair(data, gate)


def test_partial_cli_missing_collections_and_original_preservation(tmp_path):
    raw_root = tmp_path/'not-collected'
    output = tmp_path/'result'
    assert a.main(['--raw-root', str(raw_root), '--output', str(output)]) == 2
    cal = json.loads((output/'calibration.json').read_text())
    assert cal['status'] == 'PARTIAL' and not raw_root.exists()
    assert raw.file_sha(output/'input_manifest.json') == cal['measurement_manifest_sha256']
    with pytest.raises(FileExistsError): a.run(raw_root, output)
    with pytest.raises(ValueError, match='separate'): a.run(raw_root, raw_root/'fit')


def test_r1_camera_frames_floor_contract_and_missing_required_pose(unloaded_raw):
    inputs = raw.Inputs()
    data = raw.load_collection(unloaded_raw, 'unloaded', inputs)
    models, pan, report, missing = camera.fit_cameras({'unloaded': [(data, np.ones(7401, bool))]},
        json.loads(a.CRITERION.read_text())['camera'])
    assert models['unloaded'] and pan['unloaded'] == 0.
    for record in models['unloaded'].values():
        assert record['frame'] == 'optical_to_actual_chassis'
        assert record['chassis_to_floor']['origin_m'] == [0., 0., .033]
    assert any(k.startswith('camera_models.loaded.') for k in missing)
    assert 'pan_base_yaw.loaded' in missing


def test_pipeline_reads_complete_unloaded_and_lists_remaining_fields(unloaded_raw, tmp_path):
    output = tmp_path/'assembled'
    cal = a.run(unloaded_raw.parent, output)
    assert cal['status'] == 'PARTIAL'
    report = json.loads((output/'fit_report.json').read_text())
    assert report['unloaded']['collection_audit'] == 'PASS'
    assert report['unloaded']['criterion_B']['axis_pass'] == dict.fromkeys(b.AXES)
    assert report['fine']['collection_audit'] == 'FAIL'
    assert cal['pan_base_yaw']['unloaded'] == 0.
    assert any(row['field'].startswith('params.motion.') and 'frozen criterion B' in row['reason'] for row in cal['missing'])
    manifest = json.loads((output/'input_manifest.json').read_text())
    assert any(row['path'].endswith('.jpg') for row in manifest['files'])
    assert raw.file_sha(output/'input_manifest.json') == cal['measurement_manifest_sha256']
    with pytest.raises(ValueError):
        contract.measured_calibration(output/'calibration.json', raw.file_sha(output/'calibration.json'), MAP_ID)


def test_loaded_runner_format_and_no_false_grip_from_requested_state(tmp_path):
    root = synthetic_collection(tmp_path, 'loaded')
    inputs = raw.Inputs()
    data = raw.load_collection(root, 'loaded', inputs)
    assert np.max(data['robots']['r1']['u']) == .04
    np.testing.assert_array_equal(data['robots']['r2']['u'], -data['robots']['r1']['u'])
    gate = json.loads(a.CRITERION.read_text())['loaded_selection']
    valid, _ = raw.loaded_mask(data, inputs, gate)
    assert valid.all()
    # Entire loaded request can complete while the beam was never lifted.
    class OnFloor(raw.Inputs):
        def rows(self, path):
            rs = super().rows(path)
            if path.name == 'trajectory.jsonl':
                for row in rs: row['beam_xyz_m'][2] = 0.
            return rs
    valid, counts = raw.loaded_mask(data, OnFloor(), gate)
    assert not valid.any() and counts == {'not_lifted': 7401}
    for robot in data['robots'].values():
        robot['segments'] = raw.selected_segments(robot['segments'], valid)
    with pytest.raises(ValueError, match='signed'):
        motion.fit_shared(list(data['robots'].values()), b.criterion(), deadband=True)


@pytest.mark.parametrize('mutation', ['missing_coast', 'bad_image_hash', 'source_changed', 'bad_schedule'])
def test_raw_audit_rejects_tampering(unloaded_raw, monkeypatch, mutation):
    class Tampered(raw.Inputs):
        def json(self, path):
            value = super().json(path)
            if mutation == 'source_changed' and path == unloaded_raw/'result.json':
                value['source_unchanged'] = False
            if mutation == 'bad_image_hash' and path.name == 'artifacts.sha256.json':
                key = next(k for k in value if k.endswith('.jpg'))
                value[key] = '0'*64
            if mutation == 'bad_schedule' and path.name == 'schedule.json':
                value[-1]['t'] += .05
            return value
        def rows(self, path):
            value = super().rows(path)
            if mutation == 'missing_coast' and path.name == 'commands.jsonl':
                i = next(i for i, row in enumerate(value) if row['kind'] == 'mecanum' and not any(row[k] for k in b.COMMAND_AXES))
                del value[i]
            return value
    with pytest.raises(ValueError):
        raw.load_collection(unloaded_raw, 'unloaded', Tampered())
