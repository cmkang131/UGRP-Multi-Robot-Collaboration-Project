"""Assemble v88 calibration offline, or an explicit field-by-field PARTIAL.

python -m scripts.assemble_final_pair_calibration --raw-root /absolute/raw \
    --output /absolute/new-output

Never reads an unfinished collection, mutates raw, starts physics/rendering,
calls a model, changes student factories, or upgrades a numerical diagnostic.
Exit 0 = measured and loader accepted; 2 = PARTIAL (also for missing inputs).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from harness import zone_final_pair_contract as contract
from harness.vision_pose_source_final import camera_key
from harness.zone_final_pair_vision import required_camera_poses
from scripts import validate_consumer_criterion_b as b
from scripts.final_pair_calibration_io import Inputs, load_collection, loaded_mask, selected_segments
from scripts.final_pair_calibration_motion import fit_profile, fit_spread
from scripts.final_pair_calibration_camera import fit_cameras, pair_rows, fit_pair

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT/'experiments/2026-10-01-v88-measured-calibration'
CRITERION = RECORD/'criterion_B_prime.json'
CRITERION_SHA256 = '3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33'
MOTION = {'unloaded': ('params', 'motion'), 'fine': ('params', 'motion_profiles', 'fine'),
          'loaded': ('params', 'motion_loaded')}
MOTION_FIELDS = ('gain', 'tau_s', 'tau_axis_s', 'tau_stop_s', 'noise_rel', 'noise_abs',
                 'scale_std', 'scale_walk', 'use_scale', 'rest_noise')


def label(path):
    return '.'.join(path) if path[-1] else '.'.join(path[:-1])+'[""]'


def required_fields():
    fields = [prefix+(key,) for prefix in MOTION.values() for key in MOTION_FIELDS]
    fields += [MOTION['loaded']+('load_transition', key) for key in ('scale_std', 'unloaded_scale_std')]
    fields += [MOTION['loaded']+('deadband', key) for key in ('c0', 'u1')]
    fields += [MOTION['loaded']+(key,) for key in ('drift_ratio_std', 'yaw_bias_std_rad_s')]
    fields += [('pair_model', 'slope_to_yaw_ratio')]
    fields += [('pair_model', 'b_rad_s', key) for key in ('', 'pm', 'edge', 'pm+edge')]
    for state, poses in required_camera_poses().items():
        fields.append(('pan_base_yaw', state))
        for key in sorted({camera_key(pose) for pose in poses}):
            for sub in (('frame',), ('origin_m',), ('rotation',), ('chassis_to_floor', 'origin_m'), ('chassis_to_floor', 'rotation')):
                fields.append(('camera_models', state, key)+sub)
    return fields


def at(value, path):
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def put(value, path, item):
    for key in path[:-1]:
        value = value.setdefault(key, {})
    value[path[-1]] = item


def assemble(metadata, sections):
    """Sections are internal measured results, not caller-supplied CLI files.

    Tests can exercise a complete synthetic certificate. Real unloaded B
    remains unconditionally ineligible in the existing frozen validator.
    """
    cal = {**metadata, 'schema': 'ugrp.final_environment_measured_calibration.v1', 'status': 'PARTIAL'}
    missing = []
    for path in required_fields():
        matches = [(prefix, result) for prefix, result in sections.items() if path[:len(prefix)] == prefix]
        if matches:
            prefix, result = max(matches, key=lambda item: len(item[0]))
            value = at(result.get('value'), path[len(prefix):])
            accepted = result.get('accepted') is True
            reason = result.get('reason', 'measurement or acceptance missing')
        else:
            value, accepted, reason = None, False, 'measurement not available'
        if value is not None:
            try:
                json.dumps(value, allow_nan=False)
            except (ValueError, TypeError):
                value, accepted, reason = None, False, 'non-finite or unserializable measured field'
        if value is None or not accepted:
            missing.append({'field': label(path), 'reason': reason if not accepted else 'required measured field absent'})
            value = None
        put(cal, path, copy.deepcopy(value))
    for name in ('source_sha', 'measurement_manifest_sha256', 'contract_sha256', 'maps', 'robot_model', 'render_profile'):
        if not metadata.get(name):
            missing.append({'field': name, 'reason': 'provenance missing or inconsistent across collections'})
    # Finite and structural loader validation is a separate necessary gate.
    if not missing:
        cal['status'] = 'MEASURED_SIM'
        try:
            with tempfile.TemporaryDirectory(prefix='v88-loader-check-') as tmp:
                path = Path(tmp)/'candidate.json'
                path.write_text(json.dumps(cal, allow_nan=False))
                for map_id in metadata['maps']:
                    contract.measured_calibration(path, contract.base.sha(path), map_id)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            missing.append({'field': 'loader_acceptance', 'reason': str(exc)})
            cal['status'] = 'PARTIAL'
    cal['missing'] = missing
    cal['qualification'] = 'offline calibration only; no student/P03/carry or physical task acceptance'
    return cal


def run(raw_root, output):
    raw_root, output = Path(raw_root).resolve(), Path(output).resolve()
    inputs = Inputs()
    inputs.protect(raw_root)
    inputs.reject_output_overlap(output)
    if output.exists():
        raise FileExistsError(output)
    bp_blob = inputs.read(CRITERION)
    if hashlib.sha256(bp_blob).hexdigest() != CRITERION_SHA256:
        raise ValueError('frozen B-prime hash mismatch')
    prime = json.loads(bp_blob)
    gate = b.criterion()
    inputs.add(b.CRITERION)
    if prime['parent_sha256'] != b.CRITERION_SHA256 or prime['parent_text'] != gate:
        raise ValueError('B-prime parent text differs from frozen B')
    candidate = inputs.json(b.CANDIDATE)
    report_r4 = inputs.json(b.FOLDER/'consumer_report_r4.json')
    if inputs.files[str(b.CANDIDATE.resolve())]['sha256'] != report_r4['candidate_sha256']:
        raise ValueError('frozen r4 candidate changed')
    from harness.python_source_closure import source_closure
    for path in source_closure(ROOT, ['scripts/assemble_final_pair_calibration.py']):
        inputs.add(ROOT/path)
    for path in ('scripts/assemble_final_pair_calibration.py', 'scripts/final_pair_calibration_io.py',
                 'scripts/final_pair_calibration_motion.py', 'scripts/final_pair_calibration_camera.py',
                 'scripts/fit_consumer_criterion_b.py', 'scripts/fit_unloaded_consumer.py',
                 'scripts/fit_final_environment_unloaded.py', 'scripts/validate_consumer_criterion_b.py',
                 'harness/own_beam_edge.py', 'harness/zone_final_pair_camera.py',
                 'harness/zone_final_pair_contract.py', 'harness/zone_final_pair_vision.py',
                 'harness/zone_final_pair_excitation.py', 'harness/zone_final_pair_calibration.py',
                 contract.CALIBRATION_CONTRACT,
                 'experiments/2026-09-29-pair-v6e-carry/fit_carry_dr.py',
                 'experiments/2026-09-29-pair-v6e-carry/fit_carry_general.py',
                 'experiments/2026-09-29-pair-v6e-carry/fit_carry_pair_yaw.py'):
        inputs.add(ROOT/path)
    sections, diagnostics, data = {}, {}, {}
    camera_inputs = {'unloaded': [], 'loaded': []}
    for profile in MOTION:
        try:
            collection = load_collection(raw_root/('calibration-'+profile), profile, inputs)
            data[profile] = collection
            diagnostics[profile] = {'collection_audit': 'PASS'}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            diagnostics[profile] = {'collection_audit': 'FAIL', 'reason': str(exc)}
            sections[MOTION[profile]] = {'accepted': False, 'reason': 'collection audit: '+str(exc)}
            continue
        valid = np.ones(7401, bool)
        if profile == 'loaded':
            try:
                valid, selection = loaded_mask(collection, inputs, prime['loaded_selection'])
                diagnostics[profile]['load_selection'] = selection
            except (ValueError, KeyError, TypeError, OSError) as exc:
                diagnostics[profile]['load_selection'] = {'error': str(exc)}
                valid[:] = False
            collection['valid_load'] = valid
            for robot in collection['robots'].values():
                robot['segments'] = selected_segments(collection['segments'], valid)
        camera_inputs['loaded' if profile == 'loaded' else 'unloaded'].append((collection, valid))
        if profile == 'unloaded':
            try:
                cases = b.load_collection(collection['root'], gate)
                score = b.score(cases, candidate, gate)
                b.verify_inputs(cases)
                for case in cases:
                    for row in case['inputs']:
                        inputs.add(row['path'])
                diagnostics[profile]['criterion_B'] = score
                # No conversion from independent axis-only candidates to a
                # full profile. B currently supplies null decisions and no yaw.
                sections[MOTION[profile]] = {'accepted': False,
                    'reason': 'frozen criterion B axis_pass='+json.dumps(score['axis_pass'])+
                              '; no accepted complete 3-axis/scalar-stop unloaded profile'}
            except (ValueError, KeyError, TypeError, OSError) as exc:
                sections[MOTION[profile]] = {'accepted': False, 'reason': 'frozen criterion B: '+str(exc)}
            continue
        robots = [collection['robots']['r1']] if profile == 'fine' else list(collection['robots'].values())
        try:
            fitted, score = fit_profile(robots, gate, loaded=profile == 'loaded')
            diagnostics[profile]['motion'] = {'candidate': fitted, **score}
            sections[MOTION[profile]] = {'value': fitted, 'accepted': score['accepted'],
                'reason': 'criterion B-prime PRBS rejected'}
        except (ValueError, KeyError, TypeError, FloatingPointError) as exc:
            sections[MOTION[profile]] = {'accepted': False, 'reason': 'motion identification: '+str(exc)}
            diagnostics[profile]['motion'] = {'error': str(exc)}
            continue
        if profile == 'loaded':
            try:
                spread, score = fit_spread(robots, fitted, gate)
                diagnostics[profile]['spread'] = {'candidate': spread, **score}
                for key, value in spread.items():
                    sections[MOTION[profile]+(key,)] = {'value': value, 'accepted': score['accepted'] and sections[MOTION[profile]]['accepted'],
                        'reason': 'spread requires an accepted loaded mean'}
            except (ValueError, KeyError, TypeError) as exc:
                diagnostics[profile]['spread'] = {'error': str(exc)}
                for key in ('load_transition', 'drift_ratio_std', 'yaw_bias_std_rad_s'):
                    sections[MOTION[profile]+(key,)] = {'accepted': False, 'reason': str(exc)}
            try:
                rows, excluded = pair_rows(collection, fitted, valid, inputs, prime['pair_model'])
                pair, score = fit_pair(rows, prime['pair_model'])
                diagnostics[profile]['pair'] = {'candidate': pair, **score, 'excluded': excluded}
                sections[('pair_model',)] = {'value': pair, 'accepted': score['accepted'] and sections[MOTION[profile]]['accepted'],
                    'reason': 'pair PRBS validation or loaded mean rejected'}
            except (ValueError, KeyError, TypeError, OSError) as exc:
                diagnostics[profile]['pair'] = {'error': str(exc)}
                sections[('pair_model',)] = {'accepted': False, 'reason': str(exc)}
    try:
        cameras, pans, report, missing = fit_cameras(camera_inputs, prime['camera'])
        diagnostics['camera'] = report
        for state, poses in required_camera_poses().items():
            for servo in poses:
                key = camera_key(servo)
                sections[('camera_models', state, key)] = {'value': cameras[state].get(key),
                    'accepted': key in cameras[state], 'reason': missing.get(f'camera_models.{state}.{key}', 'unmeasured settled pose')}
            sections[('pan_base_yaw', state)] = {'value': pans.get(state), 'accepted': state in pans,
                'reason': missing.get(f'pan_base_yaw.{state}', 'unmeasured pan')}
    except (ValueError, KeyError, TypeError) as exc:
        diagnostics['camera'] = {'error': str(exc)}
        sections[('camera_models',)] = sections[('pan_base_yaw',)] = {'accepted': False, 'reason': str(exc)}
    inputs.reject_output_overlap(output)
    inputs.verify()
    manifest = {'schema': 'ugrp.v88_calibration_inputs.v1', 'files': sorted(inputs.files.values(), key=lambda row: row['path']),
        'criterion_B_prime_sha256': CRITERION_SHA256, 'criterion_B_sha256': b.CRITERION_SHA256,
        'execution_source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'source_state': 'input file hashes identify the implementation; HEAD alone is insufficient if dirty',
        'python': platform.python_version(), 'numpy': np.__version__, 'raw_unchanged': True}
    manifest_blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n'
    source_shas = {d['bundle']['source_sha'] for d in data.values()}
    metadata = {'source_sha': next(iter(source_shas)) if len(source_shas) == 1 and len(data) == 3 else None,
        'measurement_manifest_sha256': hashlib.sha256(manifest_blob.encode()).hexdigest(),
        'contract_sha256': contract.base.sha(ROOT/contract.CALIBRATION_CONTRACT),
        'maps': contract.resolve(next(iter(contract.registry()['maps'])))[2]['maps'],
        'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
        'criterion_B_prime_sha256': CRITERION_SHA256, 'criterion_B_sha256': b.CRITERION_SHA256,
        'collection_sources': {k: d['bundle']['source_sha'] for k, d in data.items()}}
    cal = assemble(metadata, sections)
    inputs.reject_output_overlap(output)
    inputs.verify()
    output.mkdir(parents=True, exist_ok=False)
    (output/'input_manifest.json').write_text(manifest_blob)
    for name, value in (('calibration.json', cal), ('fit_report.json', diagnostics)):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return cal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    cal = run(args.raw_root, args.output)
    print(json.dumps({'status': cal['status'], 'missing_fields': len(cal['missing']), 'output': str(args.output)}, ensure_ascii=False))
    return 0 if cal['status'] == 'MEASURED_SIM' else 2


if __name__ == '__main__':
    raise SystemExit(main())
