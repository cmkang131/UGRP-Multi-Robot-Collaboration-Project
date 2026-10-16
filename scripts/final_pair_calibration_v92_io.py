"""v92 조립 전용 원본 감사. 엔진/렌더/모델 호출 없음.

동일 시각 감사는 PR #358, 368903e6377eb34e714fd5cc33f13c5b4304703f에서
가져왔다. v88 파일은 그대로 두고 표본 수와 v92 명령 설계만 확장한다.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from harness import zone_final_pair_contract as contract
from harness.zone_final_pair_calibration import schedule
from harness.zone_final_pair_excitation import design, MAP_ID
from scripts import validate_consumer_criterion_b as b
from scripts.final_pair_calibration_io import (
    Inputs as LegacyInputs, file_sha, loaded_mask, selected_segments,
)
from harness import zone_final_pair_loaded as v92
from harness import zone_final_pair_loaded_schedule as acquisition


# Labels use refreshed kinematics at trajectory.qpos, whereas pose.jsonl
# records pre-integration kinematics. Compare each to its own instant with
# tight componentwise tolerances (rotation is a matrix element, not radians).
# Equal stationary states cannot prove timing; retain clock/ID/hash checks.
LABEL_POSE_ATOL_M = 1e-8
LABEL_ROTATION_ATOL = 1e-8


class Inputs(LegacyInputs):
    def protect(self, path):
        path = Path(path).absolute()
        for alias in (path, path.resolve()):
            if any(p.startswith('final-pair-v91-heldout-') for p in alias.parts):
                raise ValueError('v91 held-out raw is forbidden; supply scoring JSON outside raw')
        return super().protect(path)


def finite_time(value, context):
    """Reject malformed JSON clocks before coercion, rounding or comparison."""
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value))
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(context+' must be a finite numeric time')


def record_times(records, context, key='t'):
    for record in records:
        finite_time(record.get(key), context)


def rotation_matrices(value, n):
    a = np.asarray(value, float)
    if (a.shape != (n, 3, 3) or not np.isfinite(a).all()
            or not np.allclose(a.transpose(0, 2, 1) @ a, np.eye(3), atol=1e-6, rtol=0)
            or not np.allclose(np.linalg.det(a), 1., atol=1e-6, rtol=0)):
        raise ValueError('invalid recorded rotations')
    return a


def plan_arrays(plan):
    # Reuse B's exact partition/audit. Only its unloaded amplitude cap needs
    # adapting to the registered .04 loaded command, without editing B.
    finite_time(plan.get('initial_hold_s', plan.get('motion_start_s', 0.)), 'motion start')
    record_times(plan['segments'], 'motion segment duration', 'duration_s')
    scaled = {**plan, 'segments': [{**s, 'value': s['value']/2} for s in plan['segments']]}
    u, spans, ticks = b.plan_arrays(scaled, 7400, .05, include_required_ticks=True)
    return u*2, spans, ticks


def loaded_arrays(plan):
    """분리된 common-orbit 운동 창과 relative-yaw 쌍 창, 실제 두 로봇 명령."""
    if plan != acquisition.design():
        raise ValueError('v92 measurement design changed')
    n = round(acquisition.CAP_S/.05)
    commands = {rid: np.zeros((n, 3)) for rid in contract.ROBOTS}
    motion = {axis: {'steps': [], 'prbs': []} for axis in b.AXES}
    pair = {'rotate': {'steps': [], 'prbs': []}}
    bounds = []
    for segment in plan['segments']:
        a = round(segment['start_s']/.05)
        z = a+round(segment['duration_s']/.05)
        for rid in contract.ROBOTS:
            vector = acquisition.action_vector(segment, rid)
            commands[rid][a:z] = [vector[key] for key in b.COMMAND_AXES]
        bounds.append((a, z, segment))
    j = 0
    while j < len(bounds):
        a, z, segment = bounds[j]
        phase, mode = segment['phase'], segment['mode']
        if phase == 'coast':
            raise ValueError('unattached v92 coast')
        j += 1
        if phase == 'prbs':
            while (j < len(bounds) and bounds[j][2]['phase'] == 'prbs'
                   and bounds[j][2]['mode'] == mode and bounds[j][2]['axis'] == segment['axis']):
                z = bounds[j][1]
                j += 1
        if j < len(bounds) and bounds[j][2]['phase'] == 'coast':
            z = bounds[j][1]
            j += 1
        target = pair if mode == 'relative_yaw' else motion
        axis = b.AXES[b.COMMAND_AXES.index(segment['axis'])]
        target[axis]['steps' if phase == 'step' else 'prbs'].append((a, z))
    return commands, motion, pair


def quaternion_matrices(quat):
    """MuJoCo's scalar-first unit quaternions, using only NumPy."""
    quat = np.asarray(quat, float)
    norm = np.linalg.norm(quat, axis=1)
    if (quat.shape[1:] != (4,) or not np.isfinite(quat).all()
            or not np.allclose(norm, 1., atol=1e-8, rtol=0)):
        raise ValueError('invalid recorded chassis quaternion')
    w, x, y, z = (quat/norm[:, None]).T
    return np.stack((1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y),
                     2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x),
                     2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)), axis=1).reshape(-1, 3, 3)


def trajectory_chassis(folder, inputs, count):
    """Audit-only current and pre-substep poses from saved arrays; no engine.

    Resolve free-joint addresses from the recorded scene's joint order, not
    hardcoded robot offsets. v88's implicitfast last substep integrates the
    saved qvel: p_prev = p - dt*v, R_prev = R @ Exp(-dt*w_local).
    Neither reconstructed pose is passed to a fit or substituted for raw.
    """
    scene = ET.fromstring(inputs.read(folder/'scene.xml'))
    option, world = scene.find('option'), scene.find('worldbody')
    if option is None or world is None or option.get('integrator') != 'implicitfast':
        raise ValueError('unsupported recorded trajectory integrator/scene')
    dt = float(option.get('timestep', 'nan'))
    if not np.isfinite(dt) or dt != .00025:
        raise ValueError('unsupported recorded trajectory timestep')
    nq, nv, addresses = 0, 0, {}
    for node in world.iter():
        if node.tag not in ('joint', 'freejoint'):
            continue
        kind = node.get('type', 'free' if node.tag == 'freejoint' else 'hinge')
        if kind not in ('free', 'ball', 'hinge', 'slide'):
            raise ValueError('unsupported recorded joint type')
        name = node.get('name')
        if name in {rid+'__base_free' for rid in contract.ROBOTS}:
            if kind != 'free' or name in addresses:
                raise ValueError('invalid recorded chassis free joint')
            addresses[name] = (nq, nv)
        nq += {'free': 7, 'ball': 4}.get(kind, 1)
        nv += {'free': 6, 'ball': 3}.get(kind, 1)
    if set(addresses) != {rid+'__base_free' for rid in contract.ROBOTS}:
        raise ValueError('missing recorded chassis free joint')
    trace = inputs.rows(folder/'eval_only/trajectory.jsonl')
    record_times(trace, 'trajectory clock')
    qpos = np.asarray([r['qpos'] for r in trace], float)
    qvel = np.asarray([r['qvel'] for r in trace], float)
    if (qpos.shape != (count, nq) or qvel.shape != (count, nv)
            or not np.isfinite(qpos).all() or not np.isfinite(qvel).all()):
        raise ValueError('invalid recorded trajectory qpos/qvel')
    states = {}
    for rid in contract.ROBOTS:
        qa, va = addresses[rid+'__base_free']
        xyz, quat = qpos[:, qa:qa+3], qpos[:, qa+3:qa+7]
        rotation = quaternion_matrices(quat)
        previous_xyz = xyz-dt*qvel[:, va:va+3]
        angle = -dt*qvel[:, va+3:va+6]
        half = np.linalg.norm(angle, axis=1)/2
        step_quat = np.column_stack((np.cos(half), angle*(.5*np.sinc(half/np.pi))[:, None]))
        previous_rotation = rotation @ quaternion_matrices(step_quat)
        # Reset's first sample can already have refreshed kinematics.
        previous_xyz[0], previous_rotation[0] = xyz[0], rotation[0]
        states[rid] = (xyz, rotation, previous_xyz, previous_rotation)
    return np.asarray([r['t'] for r in trace]), states


def load_collection(root, profile, inputs):
    if profile not in ('unloaded', 'fine', 'loaded'):
        raise ValueError('unknown calibration profile')
    high = profile == 'loaded'
    cap = acquisition.CAP_S if high else 370.
    count, frame_count = round(cap/.05)+1, round(cap/.2)+1
    identity = v92.BUNDLE_ID if high else contract.BUNDLE_ID
    root = inputs.protect(root)
    folder = inputs.protect(root/MAP_ID)
    if not (root/'result.json').is_file():
        raise ValueError('collection completion record missing (not read while running)')
    result = inputs.json(root/'result.json')
    if (result.get('status') != 'COLLECTED_UNQUALIFIED' or result.get('source_unchanged') is not True
            or result.get('denominator') != 1 or result.get('unattempted') != []
            or len(result.get('cases', [])) != 1):
        raise ValueError('collection incomplete / HOST_ERROR / source changed')
    plan = inputs.json(root/'plan.json')
    for path in root.iterdir():
        if path.is_file():
            inputs.add(path)
    paths = list(root.rglob('*'))
    for path in paths:
        inputs.protect(path)
    inputs.trees[root] = {str(p.relative_to(root)) for p in paths if p.is_file()}
    manifest = inputs.json(folder/'artifacts.sha256.json')
    actual = {str(p.relative_to(folder)) for p in folder.rglob('*')
              if p.is_file() and p.name != 'artifacts.sha256.json'}
    if set(manifest) != actual:
        raise ValueError('artifact manifest file set mismatch')
    inputs.trees[folder] = {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()}
    for relative, digest in manifest.items():
        path = folder/relative
        if not path.resolve().is_relative_to(folder) or path.is_symlink():
            raise ValueError('artifact escapes raw case')
        inputs.add(path)
        if inputs.files[str(path.resolve())]['sha256'] != digest:
            raise ValueError('artifact sha256 mismatch: '+relative)
    bundle = inputs.json(folder/'bundle.json')
    case_result = inputs.json(folder/'result.json')
    check = 'calibration-'+profile
    finite_time(case_result.get('check_sim_s'), 'case completion clock')
    if (case_result != result['cases'][0] or case_result.get('protocol_complete') is not True
            or case_result.get('status') != 'COLLECTED_UNQUALIFIED'
            or case_result.get('collection_data_status') != 'UNQUALIFIED'
            or case_result.get('check') != check or not np.isclose(case_result.get('check_sim_s', -1), cap, atol=1e-7, rtol=0)
            or case_result.get('case', {}).get('map_id') != MAP_ID):
        raise ValueError('case completion/identity mismatch')
    wanted = {'execution_bundle_id': identity, 'check': check, 'map_id': MAP_ID,
              'measurement': acquisition.design() if high else design(check), 'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
              'contact_profile': 'cargo_noslip_v1', 'weld': 'off', 'sensors': {'ultrasonic_front': 'off'}}
    if any(bundle.get(k) != v for k, v in wanted.items()) or not re.fullmatch('[0-9a-f]{40}', bundle.get('source_sha', '')):
        raise ValueError('not the registered v88/v92 collection/physical configuration')
    if (bundle.get('case') != (v92.cases(check, MAP_ID)[0] if high else contract.cases(check)[0]) or case_result['case'] != bundle['case']
            or plan.get('execution_bundle_id') != identity or plan.get('check') != check
            or plan.get('cases') != [bundle['case']] or plan.get('denominator') != 1
            or plan.get('runnable') is not True or plan.get('source_sha') != bundle['source_sha']
            or plan.get('bundles_sha256') != [contract.base.digest(bundle)]):
        raise ValueError('collection plan/bundle/case provenance mismatch')
    if high:
        v92.validate_bundle(bundle)
        for record in (plan, result, case_result):
            for key, value in v92.record(bundle).items():
                if type(record.get(key)) is not type(value) or record[key] != value:
                    raise ValueError('v92 collection role/registration mismatch: '+key)
        if (plan.get('seed') != 911 or plan.get('execution_started') is not True
                or plan.get('blocked_on') != [] or case_result.get('check_sim_cap_s') != cap
                or case_result.get('timing') != v92.timing()):
            raise ValueError('v92 plan/result timing or execution mismatch')
        if inputs.json(folder/'inputs/measurement_design.json') != bundle['measurement']:
            raise ValueError('v92 recorded measurement design mismatch')
    static = inputs.json(folder/'inputs/static_map.json')
    if (contract.base.digest(static) != contract.resolve(MAP_ID)[2]['maps'][MAP_ID]
            or bundle.get('map_sha256') != contract.base.digest(static)
            or bundle.get('calibration_contract') != contract.base.read(contract.ROOT/contract.CALIBRATION_CONTRACT)):
        raise ValueError('static map/calibration contract mismatch')
    events = inputs.json(folder/'inputs/schedule.json')
    record_times(events, 'schedule clock')
    record_times([e['action'] for e in events if e['action']['kind'] == 'mecanum'],
                 'schedule command duration', 'duration_s')
    if events != (acquisition.schedule() if high else schedule(check)):
        raise ValueError('recorded schedule differs from registered source')
    if high:
        if file_sha(folder/'inputs/schedule.json') != bundle['schedule']['sha256']:
            raise ValueError('v92 schedule byte hash mismatch')
        commands_by_robot, segments, pair_segments = loaded_arrays(bundle['measurement'])
    else:
        expected, segments, _ = plan_arrays(bundle['measurement'])
        commands_by_robot = {'r1': expected, 'r2': np.zeros_like(expected)}
        pair_segments = {}
    data = {'root': root, 'folder': folder, 'bundle': bundle, 'profile': profile,
            'segments': segments, 'pair_segments': pair_segments, 'robots': {}}
    trajectory_t, chassis = trajectory_chassis(folder, inputs, count)
    for rid in contract.ROBOTS:
        poses = inputs.rows(folder/f'eval_only/{rid}/pose.jsonl')
        record_times(poses, rid+' pose clock')
        t = np.asarray([r['t'] for r in poses], float)
        xyz = np.asarray([r['base_position_m'] for r in poses], float)
        rot = rotation_matrices([r['base_rotation'] for r in poses], count)
        if (len(t) != count or not np.isfinite(t).all() or xyz.shape != (count, 3)
                or not np.isfinite(xyz).all() or [r['sample_index'] for r in poses] != list(range(count))
                or any(r.get('requested_check') != check for r in poses)
                or not np.allclose(t-t[0], np.arange(count)*.05, atol=1e-7, rtol=0)):
            raise ValueError('missing/invalid pose or pose clock')
        if rid == 'r2' and not np.allclose(t, data['robots']['r1']['t'], atol=1e-8, rtol=0):
            raise ValueError('robot clocks differ')
        if not np.array_equal(t, trajectory_t):
            raise ValueError('trajectory/pose clocks differ')
        current_xyz, current_rot, previous_xyz, previous_rot = chassis[rid]
        if (not np.allclose(xyz, previous_xyz, atol=LABEL_POSE_ATOL_M, rtol=0)
                or not np.allclose(rot, previous_rot, atol=LABEL_ROTATION_ATOL, rtol=0)):
            raise ValueError('recorded chassis pose differs from trajectory pre-substep state')
        commands = inputs.rows(folder/f'robots/{rid}/commands.jsonl')
        # Check every kind, especially initial_servo_command which is excluded
        # from the frozen schedule comparison below.
        record_times(commands, rid+' command clock')
        record_times([r for r in commands if r['kind'] == 'mecanum'],
                     rid+' command duration', 'duration_s')
        expected_events = [{'t': round(t[0]+e['t'], 7), **e['action']} for e in events if e['robot_id'] == rid]
        recorded_events = [{**r, 't': round(r['t'], 7)} for r in commands if r['kind'] != 'initial_servo_command']
        if recorded_events != expected_events:
            raise ValueError('issued commands/arm/leases differ from frozen schedule')
        initial = [r for r in commands if r['kind'] == 'initial_servo_command']
        if len(initial) != 1 or abs(initial[0]['t']-t[0]) > 1e-7:
            raise ValueError('missing initial issued servo state')
        u = commands_by_robot[rid].copy()
        yaw = np.unwrap(np.arctan2(rot[:, 1, 0], rot[:, 0, 0]))
        frames = inputs.rows(folder/f'robots/{rid}/frames.jsonl')
        labels = inputs.rows(folder/f'eval_only/{rid}/camera_labels.jsonl')
        record_times(frames, rid+' frame clock', 'sim_time')
        record_times(labels, rid+' camera label clock')
        if len(frames) != frame_count or len(labels) != len(frames):
            raise ValueError('missing frame/camera labels')
        servo, command_i = {str(k): int(v) for k, v in initial[0]['pulses'].items()}, 0
        last_change = t[0]
        for j, (f, label) in enumerate(zip(frames, labels)):
            # Runner captures before commands at a tick, including tick zero.
            while command_i < len(recorded_events) and recorded_events[command_i]['t'] < f['sim_time']-1e-7:
                command = recorded_events[command_i]
                sid = str(command['servo_id']) if command['kind'] == 'arm' else ('6' if command['kind'] == 'look' else None)
                if sid is not None:
                    pulse = command['pulse'] if command['kind'] == 'arm' else command['pan_pulse']
                    if servo.get(sid) != pulse:
                        last_change = command['t']
                    servo[sid] = pulse
                command_i += 1
            if (abs(f['sim_time']-t[4*j]) > 1e-7 or label['t'] != trajectory_t[4*j]
                    or label['t'] != f['sim_time'] or label['frame_id'] != f['frame_id']
                    or label['sha256'] != f['sha256'] or label.get('requested_check') != check
                    or f.get('robot_id') != rid or f.get('frame_id') != j+1 or f.get('camera') != 'robot_cam'
                    or f['commanded_servo'] != servo or label['commanded_servo'] != servo):
                raise ValueError('frame/label/command clock or identity mismatch')
            label_position = np.asarray(label['base_position_m'], float)
            label_rotation = np.asarray(label['base_rotation'], float)
            if (label_position.shape != (3,) or label_rotation.shape != (3, 3)
                    or not np.allclose(label_position, current_xyz[4*j], atol=LABEL_POSE_ATOL_M, rtol=0)
                    or not np.allclose(label_rotation, current_rot[4*j], atol=LABEL_ROTATION_ATOL, rtol=0)):
                raise ValueError('camera label chassis pose differs from simultaneous trajectory qpos')
            image = folder/f['path']
            if str(image.resolve()) not in inputs.files or inputs.files[str(image.resolve())]['sha256'] != f['sha256']:
                raise ValueError('frame image hash/path mismatch')
            f['_still_s'] = f['sim_time']-last_change
        data['robots'][rid] = {'u': u, 'pose': np.column_stack((xyz[:, :2], yaw)), 't': t,
            'dt': .05, 'segments': segments, 'frames': frames, 'labels': labels, 'commands': commands,
            'map_id': MAP_ID, 'folder': str(folder), 'training': False, 'inputs': [],
            'pose_sha256': file_sha(folder/f'eval_only/{rid}/pose.jsonl')}
    return data
