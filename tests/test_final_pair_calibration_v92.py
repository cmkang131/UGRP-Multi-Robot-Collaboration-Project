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
from scripts import assemble_final_pair_calibration_v92 as a
from harness import zone_final_pair_loaded as acquisition
from harness import zone_final_pair_loaded_schedule as schedule92
from harness import zone_final_pair_calibration_v92_contract as contract92
from scripts import final_pair_calibration_v92_camera as camera
from scripts import final_pair_calibration_v92_io as raw
from scripts import final_pair_calibration_motion as motion
from scripts import final_pair_calibration_v92_motion as motion92
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
    if profile == 'loaded':
        both, segments, _ = raw.loaded_arrays(schedule92.design())
        u = both['r1']
    else:
        u, segments, _ = raw.plan_arrays(design('calibration-'+profile))
    fields = {'gain': np.diag([1.2, .85, 1.4]).tolist(), 'tau_s': .4, 'tau_axis_s': [.4, .7, .2],
              'tau_stop_s': .08, 'noise_rel': b.criterion()['noise']['floor_noise_rel'],
              'noise_abs': b.criterion()['noise']['floor_noise_abs'], 'scale_std': 0., 'scale_walk': 0.,
              'use_scale': False, 'rest_noise': True}
    if loaded:
        fields['deadband'] = {'c0': [.003, .005, .01], 'u1': [.032]*3}
    data = {'u': u, 'dt': .05, 'segments': segments}
    data['pose'] = motion.path_of(motion.increments(data, fields))
    return data, fields


def synthetic_collection(tmp_path, profile):
    """Same paths, command order, shapes and sample clocks as v88 backend.

    JPEGs are synthetic bytes; hardlinks keep the full nframesx2 raw fixture
    small. No simulation or rendering is used to make the numerical arrays.
    """
    root = tmp_path/('calibration-'+profile)
    folder = root/MAP_ID
    data, fields = synthetic_data(profile, loaded=profile == 'loaded')
    owner = acquisition if profile == 'loaded' else contract
    cap = 720. if profile == 'loaded' else 370.
    count, nframes = round(cap/.05)+1, round(cap/.2)+1
    bundle = {**owner.bundle(MAP_ID, 'calibration-'+profile),
              'source_sha': {'unloaded':'a','fine':'b','loaded':'c'}[profile]*40,
              'case': owner.cases('calibration-'+profile, MAP_ID)[0]}
    role = acquisition.record(bundle)
    result = {'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True, 'check_sim_s': cap,
        'check': bundle['check'], 'case': bundle['case'], 'collection_data_status': 'UNQUALIFIED',
        'partial_data_retained': False, 'physical_success': None, 'research_result': False,
        'student_control': False, 'failure': None, 'timing': bundle['timing'],
        'reset_sim_s': 1.3, 'reset_sim_cap_s': 5., 'check_sim_cap_s': cap, **role}
    write(root/'result.json', {**role, 'status': 'COLLECTED_UNQUALIFIED', 'denominator': 1,
        'source_unchanged': True, 'unattempted': [], 'cases': [result], 'physical_success': None, 'research_result': False})
    write(folder/'result.json', result)
    write(folder/'bundle.json', bundle)
    write(root/'plan.json', {**role, 'execution_bundle_id': owner.BUNDLE_ID, 'check': bundle['check'],
        'status': 'DRAFT_UNSEALED', 'execution_started': True, 'cases': [bundle['case']], 'denominator': 1,
        'runnable': True, 'blocked_on': [], 'source_sha': bundle['source_sha'], 'seed': 911,
        'bundles_sha256': [contract.base.digest(bundle)], 'physical_success': None,
        'clearance_preflight': [bundle['clearance_preflight']]})
    write(folder/'inputs/static_map.json', contract.resolve(MAP_ID)[0])
    events = schedule92.schedule() if profile == 'loaded' else schedule(bundle['check'])
    (folder/'inputs/schedule.json').write_text(json.dumps(events,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write(folder/'inputs/measurement_design.json', bundle['measurement'])
    # Record the beam box's body-local offset, as real cargo XML does.
    (folder/'scene.xml').write_text('<mujoco><option timestep=".00025" integrator="implicitfast"/>'
        '<worldbody><body name="r1__robot"><freejoint name="r1__base_free"/></body>'
        '<body name="r2__robot"><freejoint name="r2__base_free"/></body>'
        '<body name="cargo_beam"><geom name="cargo_beam_bar" type="box" size=".3 .02 .02" pos="0 0 .02"/></body></worldbody></mujoco>')
    jpeg = io.BytesIO()
    Image.fromarray(np.full((480, 640, 3), 200, np.uint8)).save(jpeg, format='JPEG')
    image_bytes = jpeg.getvalue()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    qpos = np.zeros((count, 14))
    for ri, rid in enumerate(contract.ROBOTS):
        u = (raw.loaded_arrays(schedule92.design())[0][rid] if profile == 'loaded'
             else data['u'].copy() if rid == 'r1' else np.zeros_like(data['u']))
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
        qpos[:, ri*7:ri*7+3] = [[*p[:2], .033] for p in pose]
        qpos[:, ri*7+3] = np.cos(pose[:, 2]/2)
        qpos[:, ri*7+6] = np.sin(pose[:, 2]/2)
        initial = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}  # real writer has no servo 2
        commands = [{'t': 1.3, 'kind': 'initial_servo_command', 'pulses': initial}]
        commands += [{'t': round(1.3+e['t'], 8), **e['action']} for e in events if e['robot_id'] == rid]
        rows(folder/f'robots/{rid}/commands.jsonl', commands)
        frames, labels, ci, servo = [], [], 1, dict(initial)
        first_image = None
        for j in range(nframes):
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
            # Exactly sim/camera_robot_port.capture() minus 'image', plus the
            # path/commanded_servo keys sim/final_pair_v3.capture() appends.
            frame = {'robot_id': rid, 'frame_id': j+1, 'sim_time': t, 'sha256': image_hash,
                     'camera': 'robot_cam', 'actuator_state': {'motor_commands': [0., 0., 0., 0.],
                         'servo_pulses': dict(commanded)},
                     'path': path, 'commanded_servo': commanded}
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
        'active_weld_ids': []} for j in range(count)])
    rows(folder/'eval_only/trajectory.jsonl', [{'t': round(1.3+j*.05, 8), 'beam_xyz_m': [3.55, -.85, .1],
        'beam_rotation': np.eye(3).ravel().tolist(), 'qpos': qpos[j].tolist(),
        'qvel': [0.]*12, 'physical_success': None} for j in range(count)])
    refresh_manifest(folder)
    return root


@pytest.fixture(scope='module')
def loaded_raw(tmp_path_factory):
    return synthetic_collection(tmp_path_factory.mktemp('v92-synthetic-raw'), 'loaded')


@pytest.fixture(scope='module')
def unloaded_raw(tmp_path_factory):
    return synthetic_collection(tmp_path_factory.mktemp('v88-unloaded-real-schema'), 'unloaded')


@pytest.fixture(scope='module')
def fine_raw(tmp_path_factory):
    return synthetic_collection(tmp_path_factory.mktemp('v88-fine-r6-real-schema'), 'fine')


def criterion():
    return json.loads(a.CRITERION.read_text())


def writer_dict_keys(source, relative_marker, function=None):
    """Literal keys of the dict passed to self._append(<path containing marker>, {...})."""
    import ast
    from pathlib import Path
    tree = ast.parse((Path(contract.ROOT)/source).read_text())
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == '_append'
                and len(node.args) == 2 and isinstance(node.args[1], ast.Dict)
                and relative_marker in ast.unparse(node.args[0])):
            found.append(node.args[1])
    assert len(found) == 1, (source, relative_marker, len(found))
    return {k.value for k in found[0].keys if isinstance(k, ast.Constant)}, any(k is None for k in found[0].keys)


def port_capture_keys():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(contract.ROOT)/'sim/camera_robot_port.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'capture':
            returns = [n.value for n in ast.walk(node) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
            assert len(returns) == 1
            return {k.value for k in returns[0].keys}
    raise AssertionError('capture() not found')


def fixture_rows(root, relative):
    return [json.loads(line) for line in (root/MAP_ID/relative).read_text().splitlines()]


def test_fixture_row_keys_equal_the_real_writer_schema(loaded_raw):
    frame_keys, spread = writer_dict_keys('sim/final_pair_v3.py', 'frames.jsonl')
    assert spread  # frame row = port observation (minus image) plus the literal keys
    expected_frame = (port_capture_keys()-{'image'})|frame_keys
    assert 'sim_time' in expected_frame and 't' not in expected_frame
    for rid in contract.ROBOTS:
        for row in fixture_rows(loaded_raw, f'robots/{rid}/frames.jsonl'):
            assert set(row) == expected_frame
    label_keys, spread = writer_dict_keys('sim/final_pair_v3.py', 'camera_labels.jsonl')
    label_fields = set(measurement_label([0, 0, 0], np.eye(3), [0, 0, 0], np.eye(3)))
    for rid in contract.ROBOTS:
        for row in fixture_rows(loaded_raw, f'eval_only/{rid}/camera_labels.jsonl'):
            assert set(row) == label_keys|label_fields
    pose_keys, _ = writer_dict_keys('sim/final_pair_v3.py', 'pose.jsonl')
    beam_keys, _ = writer_dict_keys('sim/final_pair_v3.py', 'trajectory.jsonl')
    contact_keys, _ = writer_dict_keys('sim/final_environment_checks.py', 'contacts.jsonl')
    for rid in contract.ROBOTS:
        assert all(set(r) == pose_keys for r in fixture_rows(loaded_raw, f'eval_only/{rid}/pose.jsonl'))
    assert all(set(r) == beam_keys for r in fixture_rows(loaded_raw, 'eval_only/trajectory.jsonl'))
    assert all(set(r) == contact_keys for r in fixture_rows(loaded_raw, 'eval_only/contacts.jsonl'))


def test_fixture_command_and_servo_vocabulary_matches_real_raw(loaded_raw):
    # Observed in the real v88 raw: no servo 2 anywhere, pulses keyed by string id.
    kinds = {}
    for row in fixture_rows(loaded_raw, 'robots/r1/commands.jsonl'):
        kinds.setdefault(row['kind'], set(row))
    assert kinds['initial_servo_command'] == {'t', 'kind', 'pulses'}
    assert kinds['arm'] == {'t', 'kind', 'servo_id', 'pulse'}
    assert kinds['look'] == {'t', 'kind', 'pan_pulse'}
    assert kinds['mecanum'] == {'t', 'kind', 'forward', 'left', 'turn', 'duration_s'}
    frames = fixture_rows(loaded_raw, 'robots/r1/frames.jsonl')
    assert set(frames[0]['commanded_servo']) == {'1', '3', '4', '5', '6'}
    assert frames[0]['actuator_state']['servo_pulses'] == frames[0]['commanded_servo']
    assert isinstance(frames[0]['frame_id'], int) and frames[0]['camera'] == 'robot_cam'



@pytest.mark.parametrize('profile', ['unloaded', 'fine', 'loaded'])
def test_real_schema_collection_audit(profile, loaded_raw, unloaded_raw, fine_raw):
    root = {'loaded': loaded_raw, 'unloaded': unloaded_raw, 'fine': fine_raw}[profile]
    inputs = raw.Inputs()
    data = raw.load_collection(root, profile, inputs)
    count = 14401 if profile == 'loaded' else 7401
    for robot in data['robots'].values():
        assert robot['t'].shape == (count,)
        assert len(robot['frames']) == (count-1)//4+1
        assert 't' not in robot['frames'][0]
    if profile == 'loaded':
        mask, reasons = raw.loaded_mask(data, inputs, criterion()['loaded_selection'])
        assert mask.all() and reasons == {'lifted': count}
        # Same local turn AND tangential left in orbit; opposite relative yaw.
        for tick in (round(385/.05), round(400/.05)):
            assert np.array_equal(data['robots']['r1']['u'][tick], data['robots']['r2']['u'][tick])
        assert data['robots']['r1']['u'][round(571/.05), 2] == -data['robots']['r2']['u'][round(571/.05), 2]
        assert all(z <= round(490/.05) for axis in data['segments'].values() for spans in axis.values() for a0,z in spans)
        assert all(a0 >= round(570/.05) for spans in data['pair_segments']['rotate'].values() for a0,z in spans)
    inputs.verify()


@pytest.mark.parametrize('fault', ['old_frame_key', 'frame_clock', 'frame_robot', 'frame_id',
    'label_clock', 'label_position', 'label_rotation', 'qpos', 'qvel', 'quaternion',
    'pose_position', 'trajectory_clock', 'missing_frame', 'command', 'servo', 'duration'])
def test_v92_audit_rejects_real_schema_corruption(loaded_raw, fault):
    class Corrupt(raw.Inputs):
        def rows(self, path):
            values = super().rows(path)
            name = str(path.relative_to(loaded_raw/MAP_ID))
            if name == 'robots/r1/frames.jsonl':
                if fault == 'old_frame_key':
                    for row in values: row['t'] = row.pop('sim_time')
                if fault == 'frame_clock': values[100]['sim_time'] += .05
                if fault == 'frame_robot': values[100]['robot_id'] = 'r2'
                if fault == 'frame_id': values[100]['frame_id'] += 1
                if fault == 'missing_frame': values.pop()
                if fault == 'servo': values[100]['commanded_servo']['3'] += 1
            if name == 'eval_only/r1/camera_labels.jsonl':
                if fault == 'label_clock': values[100]['t'] += 1e-9
                if fault == 'label_position': values[100]['base_position_m'][0] += 2e-8
                if fault == 'label_rotation': values[100]['base_rotation'] = rz(.001).tolist()
            if name == 'eval_only/trajectory.jsonl':
                if fault == 'qpos': values[400]['qpos'][0] += .0001
                if fault == 'qvel': values[400]['qvel'][0] = float('nan')
                if fault == 'quaternion': values[400]['qpos'][3:7] = [2.,0.,0.,0.]
                if fault == 'trajectory_clock': values[400]['t'] += 1e-9
            if name == 'eval_only/r1/pose.jsonl' and fault == 'pose_position':
                values[400]['base_position_m'][0] += .0001
            if name == 'robots/r2/commands.jsonl':
                first = next(row for row in values if row['kind'] == 'mecanum')
                if fault == 'command': first['forward'] *= -1
                if fault == 'duration': first['duration_s'] = .1
            return values
    with pytest.raises(ValueError):
        raw.load_collection(loaded_raw, 'loaded', Corrupt())


@pytest.mark.parametrize('fault', ['cap', 'identity', 'role', 'timing', 'schedule', 'measurement', 'incomplete'])
def test_v92_registration_and_completion_are_required(loaded_raw, fault):
    class Corrupt(raw.Inputs):
        def json(self, path):
            value = super().json(path)
            if path == loaded_raw/'result.json' and fault == 'incomplete': value['source_unchanged'] = False
            if path == loaded_raw/'plan.json' and fault == 'role': value['training_eligible'] = False
            if path == loaded_raw/MAP_ID/'bundle.json':
                if fault == 'cap': value['caps']['per_case_s'] = 370.
                if fault == 'identity': value['execution_bundle_id'] = contract.BUNDLE_ID
                if fault == 'timing': value['timing']['eval_pose_period_s'] = .1
            if path == loaded_raw/MAP_ID/'inputs/schedule.json' and fault == 'schedule':
                value[0]['action']['pulse'] += 1
            if path == loaded_raw/MAP_ID/'inputs/measurement_design.json' and fault == 'measurement':
                value['camera_windows'][0]['end_s'] += .2
            return value
    with pytest.raises(ValueError): raw.load_collection(loaded_raw, 'loaded', Corrupt())


def test_same_instant_audit_retains_pre_substep_fit_pose(loaded_raw):
    # Nonzero last-substep velocity makes pose and camera label deliberately
    # different at the same timestamp, exactly as the real writer does.
    class Moving(raw.Inputs):
        def rows(self, path):
            values = super().rows(path)
            if path.name == 'trajectory.jsonl':
                values[400]['qvel'][0] = .2
                values[400]['qpos'][0] += .00025*.2
            if path == loaded_raw/MAP_ID/'eval_only/r1/camera_labels.jsonl':
                values[100]['base_position_m'][0] += .00025*.2
            return values
    data = raw.load_collection(loaded_raw, 'loaded', Moving())
    pose = fixture_rows(loaded_raw, 'eval_only/r1/pose.jsonl')[400]
    assert np.array_equal(data['robots']['r1']['pose'][400,:2], pose['base_position_m'][:2])


def test_camera_windows_high_only_and_half_open(loaded_raw):
    inputs = raw.Inputs()
    data = raw.load_collection(loaded_raw, 'loaded', inputs)
    valid = np.ones(14401, bool)
    # Remove movement ONLY from the diagnostic arrays to test that explicit
    # camera windows (not incidental stillness) are the selection boundary.
    for robot in data['robots'].values(): robot['u'][:] = 0
    models, pans, report, missing = camera.fit_cameras({'loaded': [(data, valid)]}, criterion())
    center = '896,2035,1894,1500'
    assert report['loaded'][center]['optical']['n'] == 5*40*2
    assert set(models['loaded']) == {center, '896,2035,1894,1480', '896,2035,1894,1520'}
    assert '1269,2052,2494,1500' not in models['loaded']
    assert 'camera_models.loaded.'+center not in missing
    # [32,40) contains 40 frames per robot. The excluded 40s endpoint may be
    # arbitrarily malformed optically without entering the estimator.
    for robot in data['robots'].values():
        robot['labels'][200]['origin_m'] = [999., 999., 999.]
    again = camera.fit_cameras({'loaded': [(data, valid)]}, criterion())
    assert again[0] == models


def test_camera_requires_whole_warmup_and_load_support(loaded_raw):
    data = raw.load_collection(loaded_raw, 'loaded', raw.Inputs())
    mask = np.zeros(14401, bool)
    for robot in data['robots'].values(): robot['u'][:] = 0
    models, _, _, missing = camera.fit_cameras({'loaded': [(data, mask)]}, criterion())
    assert not models['loaded']
    assert 'camera_models.loaded.896,2035,1894,1500' in missing
    mask[:] = True
    for robot in data['robots'].values():
        for f in robot['frames']: f['_still_s'] = 7.99
    assert not camera.fit_cameras({'loaded': [(data, mask)]}, criterion())[0]['loaded']


def test_exact_mixed_motion_fit_uses_new_bounds():
    data, expected = synthetic_data('loaded', loaded=True)
    fitted, report = motion92.fit_shared([data], b.criterion(), criterion()['loaded_motion_bounds'])
    assert report['rank'] == 13
    assert np.allclose(fitted['deadband']['c0'], expected['deadband']['c0'], atol=1e-7)
    assert np.allclose(fitted['deadband']['u1'], expected['deadband']['u1'], atol=1e-7)
    assert np.allclose(fitted['gain'], expected['gain'], atol=1e-6)
    assert np.allclose(fitted['tau_axis_s'], expected['tau_axis_s'], atol=1e-6)
    assert fitted['tau_stop_s'] == pytest.approx(expected['tau_stop_s'], abs=1e-6)
    assert report['deadband_support'][0]['forward'][0]['command'] == -.001
    with pytest.raises(ValueError, match='boundary|bounds|bracket'):
        motion.fit_shared([data], b.criterion(), deadband=True)


def test_observed_stop_and_two_ramps_are_required():
    data, profile = synthetic_data('loaded', loaded=True)
    motion92.deadband_support(data, profile, b.criterion())
    for c0,u1 in ((.0005,.032), (.026,.032), (.003,.05)):
        broken = copy.deepcopy(profile)
        broken['deadband']['c0'][0] = c0
        broken['deadband']['u1'][0] = u1
        with pytest.raises(ValueError, match='bracket'):
            motion92.deadband_support(data, broken, b.criterion())
    data['segments'] = copy.deepcopy(data['segments'])
    data['segments']['forward']['steps'] = data['segments']['forward']['steps'][4:]
    with pytest.raises(ValueError, match='bracket'):
        motion92.deadband_support(data, profile, b.criterion())


def test_pair_rows_use_relative_segments_and_actual_partner(loaded_raw, monkeypatch):
    inputs = raw.Inputs()
    data = raw.load_collection(loaded_raw, 'loaded', inputs)
    valid, _ = raw.loaded_mask(data, inputs, criterion()['loaded_selection'])
    _, profile = synthetic_data('loaded', loaded=True)
    class Tracker:
        def __init__(self, ratio):
            self.ref_t = self.eff_t = None
            self.total_rad = .01
            self.stats = {}
        def observe(self, t, image, servo, closed):
            assert t >= data['robots']['r1']['t'][0]+570.
            if self.ref_t is None: self.ref_t = t
            self.eff_t = t
        def available(self, t): return True
    monkeypatch.setattr(camera, 'BeamEdgeTracker', Tracker)
    records, _ = camera.pair_rows(data, profile, valid, inputs, criterion()['pair_model'])
    assert len(records) == 18  # eight signed steps + one PRBS, both robots
    assert all(row['cell'].startswith('relative_yaw/') for row in records)
    assert all(row['ms'] == pytest.approx(-row['mp'], abs=1e-12) for row in records)
    valid[round(575/.05)] = False
    reduced, excluded = camera.pair_rows(data, profile, valid, inputs, criterion()['pair_model'])
    assert len(reduced) == 16 and len(excluded) == 2


def complete_sections():
    _, profile = synthetic_data('loaded', loaded=True)
    profile.update(load_transition={'scale_std': [.01,.01,0.], 'unloaded_scale_std': 0.},
                   drift_ratio_std=.01, yaw_bias_std_rad_s=.001)
    sections = {prefix: {'value': copy.deepcopy(profile), 'accepted': True} for prefix in a.MOTION.values()}
    sections[('pair_model',)] = {'value': {'slope_to_yaw_ratio': 1., 'b_rad_s': dict.fromkeys(('', 'pm', 'edge', 'pm+edge'), .001)}, 'accepted': True}
    for state, poses in contract92.required_camera_poses().items():
        sections[('pan_base_yaw', state)] = {'value': 0., 'accepted': True}
        for pose in poses:
            label = measurement_label([0,0,.033], np.eye(3), [.1,0,.2], np.diag([1.,-1.,-1.]))
            sections[('camera_models',state,camera.camera_key(pose))] = {'value':label,'accepted':True}
    return sections


def metadata():
    return {'source_sha': 'd'*40, 'measurement_manifest_sha256': 'a'*64,
        'contract_sha256': contract.base.sha(contract.ROOT/contract92.CALIBRATION_CONTRACT),
        'maps': contract92.calibration_contract()['maps'], 'robot_model':'masterpi_v3','render_profile':'floor_light_v1',
        'loaded_measurement_bundle_id': acquisition.BUNDLE_ID, 'loaded_pose_id': contract92.POSE_ID,
        'loaded_camera_scope':'high_only','loaded_schedule_sha256':acquisition.schedule_registration()['sha256'],
        'criterion_sha256':acquisition.CRITERION_SHA256,'assembler_sha256':contract.base.sha(contract.ROOT/a.ENTRY_POINT),
        'collection_sources':dict(zip(('unloaded','fine','loaded'), ('a'*40,'b'*40,'c'*40)))}


def test_new_loader_contract_high_only_different_sources(tmp_path):
    cal = a.assemble(metadata(), complete_sections())
    assert cal['status'] == 'MEASURED_SIM' and cal['missing'] == []
    assert cal['schema'] == contract92.SCHEMA and cal['loader_contract_version'] == 2
    assert set(cal['camera_models']['loaded']) == {'896,2035,1894,1500'}
    path = tmp_path/'calibration.json'
    write(path,cal)
    contract92.measured_calibration(path, raw.file_sha(path), MAP_ID)
    with pytest.raises(ValueError): contract.measured_calibration(path, raw.file_sha(path), MAP_ID)
    cal['camera_models']['loaded']['1269,2052,2494,1500'] = cal['camera_models']['loaded']['896,2035,1894,1500']
    write(path,cal)
    with pytest.raises(ValueError,match='HIGH only'): contract92.measured_calibration(path,raw.file_sha(path),MAP_ID)


@pytest.mark.parametrize('field', ['loaded_schedule_sha256','criterion_sha256','loaded_pose_id','contract_sha256'])
def test_loader_rejects_wrong_provenance(field):
    meta = metadata()
    meta[field] = '0'*64
    cal = a.assemble(meta,complete_sections())
    assert cal['status'] == 'PARTIAL'
    assert cal['missing'][0]['field'] == 'loader_acceptance'


def test_optional_reports_are_inputs_not_raw_permission(tmp_path):
    path = tmp_path/'score.json'
    result = {'schema':'ugrp.consumer_B_validation.v91','criterion_sha256':b.CRITERION_SHA256,
        'axis_pass':{'forward':True,'left':False,'rotate':None},'pass':False,
        'input_files':[{'path':'/Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-FORBIDDEN/pose.jsonl','sha256':'a'*64}]}
    write(path,result)
    inputs = raw.Inputs()
    report = a.optional_evidence(inputs,None,[path],{})
    assert report['criterion_B_results'][0]['report'] == result
    assert list(inputs.files) == [str(path)]
    assert not report['axis_candidates_qualify_full_profile']
    with pytest.raises(ValueError,match='forbidden'): inputs.protect(result['input_files'][0]['path'])
    with pytest.raises(ValueError,match='separate'): inputs.reject_output_overlap(path.parent)


def test_r5_hash_is_required(tmp_path):
    path = tmp_path/'fake-r5.json'
    write(path,{'criterion_sha256':b.CRITERION_SHA256,'status':'CANDIDATE_UNVALIDATED'})
    with pytest.raises(ValueError,match='r5 candidate'): a.optional_evidence(raw.Inputs(),path,[],{})


def test_run_preserves_partial_and_no_v91_score(tmp_path,unloaded_raw,fine_raw,loaded_raw,monkeypatch):
    # Orchestration check: real writer schema and real camera audit; separate
    # numerical tests above cover fit. Never turn a supplied pass into promotion.
    monkeypatch.setattr(a,'fit_loaded_profile',lambda *args: (_ for _ in ()).throw(ValueError('synthetic fit unavailable')))
    monkeypatch.setattr(a,'fit_legacy_profile',lambda *args: (_ for _ in ()).throw(ValueError('synthetic fit unavailable')))
    monkeypatch.setattr(b,'score',lambda *args: pytest.fail('B scoring forbidden'))
    report_path = tmp_path/'v91-result.json'
    write(report_path,{'schema':'ugrp.consumer_B_validation.v91','criterion_sha256':b.CRITERION_SHA256,
                     'axis_pass':dict.fromkeys(b.AXES,True),'pass':True})
    output = tmp_path/'assembly'
    cal = a.run(unloaded_raw,fine_raw,loaded_raw,output,criterion_b_results=[report_path])
    assert cal['status'] == 'PARTIAL'
    assert cal['collection_sources'] == dict(zip(('unloaded','fine','loaded'),('a'*40,'b'*40,'c'*40)))
    report = json.loads((output/'fit_report.json').read_text())
    assert all(report[p]['collection_audit'] == 'PASS' for p in a.MOTION)
    assert report['external_criterion_B']['criterion_B_results'][0]['report']['pass'] is True
    manifest = json.loads((output/'input_manifest.json').read_text())
    assert raw.file_sha(output/'input_manifest.json') == cal['measurement_manifest_sha256']
    assert str(report_path) in {row['path'] for row in manifest['files']}
    assert any(m['field']=='params.motion.tau_stop_s' and 'scalar-stop' in m['reason'] for m in cal['missing'])
    with pytest.raises(FileExistsError): a.run(unloaded_raw,fine_raw,loaded_raw,output)
    with pytest.raises(ValueError,match='separate'): a.run(unloaded_raw,fine_raw,loaded_raw,loaded_raw/'nested')


def test_loaded_profile_validates_exact_mixed_candidate():
    data, actual = synthetic_data('loaded', loaded=True)
    fitted, report = motion92.fit_profile([data], criterion())
    assert report['criterion'] == 'B-double-prime' and report['accepted']
    assert report['optimizer']['rank'] == 13
    for key in ('gain','tau_axis_s','tau_stop_s'):
        np.testing.assert_allclose(fitted[key],actual[key],atol=2e-6)
    contaminated = copy.deepcopy(data)
    for spans in data['segments'].values():
        for start,end in spans['prbs']:
            contaminated['pose'][start:end+1,0] += np.linspace(0,1.,end-start+1)
    fixed,_ = motion92.fit_shared([contaminated],b.criterion(),criterion()['loaded_motion_bounds'])
    np.testing.assert_allclose(fixed['gain'],fitted['gain'],atol=2e-6)
    scored = motion.evaluate(contaminated,fitted,b.criterion(),'prbs')
    assert not all(row['numerical_pass'] for axis in scored.values() for row in b.all_rows(axis))
    gate = {**b.criterion(),'horizons_s':[3.2]}
    groups = list(motion.budget_groups(motion.split_data(data,'prbs'),fitted,gate))
    group = next(g for g in groups if g['axis']=='rotate')
    delta = motion.increments(data,fitted)
    starts,k = b.c.windows(data['segments']['rotate']['prbs'],3.2,.05)
    _,cov = b.c.legacy_windows(delta,starts,k,.05,fitted,scale=False)
    noise = np.asarray(fitted['noise_abs'])
    var = group['fixed']+np.sum(group['quad']*noise**2+group['linear']*noise,axis=2)
    np.testing.assert_allclose(var,np.diagonal(cov,axis1=1,axis2=2),rtol=1e-10,atol=1e-15)


def test_v92_is_in_related_ci_once():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert TEST_PATTERNS.count('tests/test_final_pair_calibration_v92.py') == 1
