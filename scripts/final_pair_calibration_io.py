"""Read-only v88 raw audit. No simulator/renderer/model imports or extraction."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from harness import zone_final_pair_contract as contract
from harness.zone_final_pair_calibration import schedule
from harness.zone_final_pair_excitation import design, MAP_ID
from scripts import validate_consumer_criterion_b as b


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Inputs:
    def __init__(self):
        self.files = {}
        self.trees = {}
        self.paths = set()

    def protect(self, path):
        """Keep both aliases and targets, including incomplete collection roots."""
        path = Path(path).absolute()
        resolved = path.resolve()
        self.paths.update((path, resolved))
        return resolved

    def reject_output_overlap(self, *outputs):
        # Resolve again at the write boundary, including any retargeted links.
        inputs = {p.resolve() for p in self.paths}
        for output in outputs:
            output = Path(output).resolve()
            for path in inputs:
                if output.is_relative_to(path) or path.is_relative_to(output):
                    raise ValueError(f'output must be separate from every input: {output} overlaps {path}')

    def add(self, path):
        path = self.protect(path).resolve(strict=True)
        row = {'path': str(path), 'sha256': file_sha(path), 'bytes': path.stat().st_size}
        old = self.files.setdefault(str(path), row)
        if old != row:
            raise ValueError('input changed: '+str(path))
        return path

    def read(self, path):
        path = self.add(path)
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.files[str(path)]['sha256']:
            raise ValueError('input changed while reading: '+str(path))
        return blob

    def json(self, path):
        return json.loads(self.read(path))

    def rows(self, path):
        return [json.loads(line) for line in self.read(path).splitlines()]

    def verify(self):
        for row in list(self.files.values()):
            self.add(row['path'])
        for folder, names in self.trees.items():
            if {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()} != names:
                raise ValueError('raw artifact file set changed: '+str(folder))


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
    scaled = {**plan, 'segments': [{**s, 'value': s['value']/2} for s in plan['segments']]}
    u, spans, ticks = b.plan_arrays(scaled, 7400, .05, include_required_ticks=True)
    return u*2, spans, ticks


def load_collection(root, profile, inputs):
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
    if (case_result != result['cases'][0] or case_result.get('protocol_complete') is not True
            or case_result.get('status') != 'COLLECTED_UNQUALIFIED'
            or case_result.get('collection_data_status') != 'UNQUALIFIED'
            or case_result.get('check') != check or not np.isclose(case_result.get('check_sim_s', -1), 370., atol=1e-7, rtol=0)
            or case_result.get('case', {}).get('map_id') != MAP_ID):
        raise ValueError('case completion/identity mismatch')
    wanted = {'execution_bundle_id': contract.BUNDLE_ID, 'check': check, 'map_id': MAP_ID,
              'measurement': design(check), 'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
              'contact_profile': 'cargo_noslip_v1', 'weld': 'off', 'sensors': {'ultrasonic_front': 'off'}}
    if any(bundle.get(k) != v for k, v in wanted.items()) or not re.fullmatch('[0-9a-f]{40}', bundle.get('source_sha', '')):
        raise ValueError('not the registered v88 collection/physical configuration')
    if (bundle.get('case') != contract.cases(check)[0] or case_result['case'] != bundle['case']
            or plan.get('execution_bundle_id') != contract.BUNDLE_ID or plan.get('check') != check
            or plan.get('cases') != [bundle['case']] or plan.get('denominator') != 1
            or plan.get('runnable') is not True or plan.get('source_sha') != bundle['source_sha']
            or plan.get('bundles_sha256') != [contract.base.digest(bundle)]):
        raise ValueError('collection plan/bundle/case provenance mismatch')
    static = inputs.json(folder/'inputs/static_map.json')
    if (contract.base.digest(static) != contract.resolve(MAP_ID)[2]['maps'][MAP_ID]
            or bundle.get('map_sha256') != contract.base.digest(static)
            or bundle.get('calibration_contract') != contract.base.read(contract.ROOT/contract.CALIBRATION_CONTRACT)):
        raise ValueError('static map/calibration contract mismatch')
    events = inputs.json(folder/'inputs/schedule.json')
    if events != schedule(check):
        raise ValueError('recorded schedule differs from v88 source')
    expected, segments, required = plan_arrays(bundle['measurement'])
    data = {'root': root, 'folder': folder, 'bundle': bundle, 'profile': profile,
            'segments': segments, 'robots': {}}
    for rid in contract.ROBOTS:
        poses = inputs.rows(folder/f'eval_only/{rid}/pose.jsonl')
        t = np.asarray([r['t'] for r in poses], float)
        xyz = np.asarray([r['base_position_m'] for r in poses], float)
        rot = rotation_matrices([r['base_rotation'] for r in poses], 7401)
        if (len(t) != 7401 or not np.isfinite(t).all() or xyz.shape != (7401, 3)
                or not np.isfinite(xyz).all() or [r['sample_index'] for r in poses] != list(range(7401))
                or any(r.get('requested_check') != check for r in poses)
                or not np.allclose(t-t[0], np.arange(7401)*.05, atol=1e-7, rtol=0)):
            raise ValueError('missing/invalid pose or pose clock')
        if rid == 'r2' and not np.allclose(t, data['robots']['r1']['t'], atol=1e-8, rtol=0):
            raise ValueError('robot clocks differ')
        commands = inputs.rows(folder/f'robots/{rid}/commands.jsonl')
        expected_events = [{'t': round(t[0]+e['t'], 7), **e['action']} for e in events if e['robot_id'] == rid]
        recorded_events = [{**r, 't': round(r['t'], 7)} for r in commands if r['kind'] != 'initial_servo_command']
        if recorded_events != expected_events:
            raise ValueError('issued commands/arm/leases differ from frozen schedule')
        initial = [r for r in commands if r['kind'] == 'initial_servo_command']
        if len(initial) != 1 or abs(initial[0]['t']-t[0]) > 1e-7:
            raise ValueError('missing initial issued servo state')
        u = expected.copy() if rid == 'r1' else (-expected.copy() if profile == 'loaded' else np.zeros_like(expected))
        yaw = np.unwrap(np.arctan2(rot[:, 1, 0], rot[:, 0, 0]))
        frames = inputs.rows(folder/f'robots/{rid}/frames.jsonl')
        labels = inputs.rows(folder/f'eval_only/{rid}/camera_labels.jsonl')
        if len(frames) != 1851 or len(labels) != len(frames):
            raise ValueError('missing frame/camera labels')
        servo, command_i = {str(k): int(v) for k, v in initial[0]['pulses'].items()}, 0
        last_change = t[0]
        for j, (f, label) in enumerate(zip(frames, labels)):
            # Runner captures before commands at a tick, including tick zero.
            while command_i < len(recorded_events) and recorded_events[command_i]['t'] < f['t']-1e-7:
                command = recorded_events[command_i]
                sid = str(command['servo_id']) if command['kind'] == 'arm' else ('6' if command['kind'] == 'look' else None)
                if sid is not None:
                    pulse = command['pulse'] if command['kind'] == 'arm' else command['pan_pulse']
                    if servo.get(sid) != pulse:
                        last_change = command['t']
                    servo[sid] = pulse
                command_i += 1
            if (abs(f['t']-t[4*j]) > 1e-7 or label['t'] != f['t'] or label['frame_id'] != f['frame_id']
                    or label['sha256'] != f['sha256'] or label.get('requested_check') != check
                    or f['commanded_servo'] != servo or label['commanded_servo'] != servo):
                raise ValueError('frame/label/command clock or identity mismatch')
            label_position = np.asarray(label['base_position_m'], float)
            label_rotation = np.asarray(label['base_rotation'], float)
            if (label_position.shape != (3,) or label_rotation.shape != (3, 3)
                    or not np.allclose(label_position, xyz[4*j], atol=1e-8, rtol=0)
                    or not np.allclose(label_rotation, rot[4*j], atol=1e-8, rtol=0)):
                raise ValueError('camera label chassis pose differs from simultaneous pose sample')
            image = folder/f['path']
            if str(image.resolve()) not in inputs.files or inputs.files[str(image.resolve())]['sha256'] != f['sha256']:
                raise ValueError('frame image hash/path mismatch')
            f['_still_s'] = f['t']-last_change
        data['robots'][rid] = {'u': u, 'pose': np.column_stack((xyz[:, :2], yaw)), 't': t,
            'dt': .05, 'segments': segments, 'frames': frames, 'labels': labels, 'commands': commands,
            'map_id': MAP_ID, 'folder': str(folder), 'training': False, 'inputs': [],
            'pose_sha256': file_sha(folder/f'eval_only/{rid}/pose.jsonl')}
    return data


def loaded_mask(data, inputs, gate):
    """Teacher selection from measured bottom height and bilateral contacts."""
    folder = data['folder']
    trace = inputs.rows(folder/'eval_only/trajectory.jsonl')
    contact = inputs.rows(folder/'eval_only/contacts.jsonl')
    t = data['robots']['r1']['t']
    if len(trace) != len(t) or len(contact) != len(t):
        raise ValueError('loaded contact/beam sample count mismatch')
    root = ET.fromstring(inputs.read(folder/'scene.xml'))
    beam = root.find('.//body[@name="cargo_beam"]')
    if beam is None:
        raise ValueError('missing beam geometry')
    # The v88 long beam is a box. Fail closed on a different shape/frame.
    geoms = [g for g in beam.findall('geom') if g.get('contype', '1') != '0']
    if len(geoms) != 1 or geoms[0].get('type') != 'box' or any(k in geoms[0].attrib for k in ('quat', 'euler', 'axisangle', 'xyaxes', 'zaxis')):
        raise ValueError('unsupported recorded beam geometry')
    geom = geoms[0]
    size = np.asarray([float(v) for v in geom.get('size', '').split()])
    pos = np.asarray([float(v) for v in geom.get('pos', '0 0 0').split()])
    if size.shape != (3,) or pos.shape != (3,) or not np.isfinite([size, pos]).all() or np.any(size <= 0):
        raise ValueError('invalid recorded beam dimensions')
    rotation = rotation_matrices([np.asarray(r['beam_rotation']).reshape(3, 3) for r in trace], len(t))
    mask, reasons = [], Counter()
    for i, (tr, cr) in enumerate(zip(trace, contact)):
        for record in (tr, cr):
            time = record.get('t')
            if isinstance(time, bool) or not isinstance(time, (int, float)) or not np.isfinite(time):
                raise ValueError('contact/beam clock must be a finite numeric time')
        xyz = np.asarray(tr['beam_xyz_m'], float)
        if (xyz.shape != (3,) or not np.isfinite(xyz).all() or abs(tr['t']-t[i]) > 1e-7
                or abs(cr['t']-t[i]) > 1e-7 or 'active_weld_ids' not in cr):
            raise ValueError('invalid contact/beam clock or geometry')
        if cr['active_weld_ids']:
            raise ValueError('active weld in loaded collection')
        bottom = xyz[2]+(rotation[i] @ pos)[2]-np.abs(rotation[i, 2]) @ size
        touched, supported = set(), False
        for c in cr['contacts']:
            if not np.isfinite(c['dist_m']):
                raise ValueError('nonfinite contact distance')
            if geom.get('name') not in (c['geom1'], c['geom2']) or c['dist_m'] > gate['contact_max_dist_m']:
                continue
            other = c['geom2'] if c['geom1'] == geom.get('name') else c['geom1']
            if other in {rid+'__'+side+'_finger' for rid in contract.ROBOTS for side in ('left', 'right')}:
                touched.add(other)
            else:
                supported = True
        valid_contacts = all(rid+'__'+side+'_finger' in touched for rid in contract.ROBOTS for side in ('left', 'right'))
        reason = ('not_lifted' if bottom < gate['beam_bottom_min_m'] else
                  'external_support' if supported else 'missing_bilateral_grip' if not valid_contacts else 'lifted')
        reasons[reason] += 1
        mask.append(reason == 'lifted')
    data['beam_trace'] = trace
    return np.asarray(mask), dict(reasons)


def selected_segments(segments, mask):
    """Keep contiguous valid portions; never bridge a drop/contact gap."""
    result = {}
    for axis, splits in segments.items():
        result[axis] = {}
        for split, spans in splits.items():
            kept = []
            for a, z in spans:
                good = np.flatnonzero(mask[a:z+1])+a
                for block in np.split(good, np.flatnonzero(np.diff(good) != 1)+1):
                    if len(block) > 1:
                        kept.append((int(block[0]), int(block[-1])))
            result[axis][split] = kept
    return result
