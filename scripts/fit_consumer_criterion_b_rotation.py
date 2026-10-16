"""Training-only yaw addendum to frozen B/r4; never opens v91 held-out raw.

Only the two coordinator-authorized training roots can be read by the CLI.
No images/frames, simulator, renderer or controller are used. Pose time is `t`;
frames (not needed for this fit) use `sim_time`, not `t` (PR #358).
"""
from __future__ import annotations

import argparse
import copy
import json
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np
import scipy
from scipy.optimize import least_squares

from scripts import fit_consumer_criterion_b as r4
from scripts import validate_consumer_criterion_b as b
from scripts.fit_unloaded_hammerstein import require_disjoint_output, sha, write

TRAINING_MAP = 'zone_wide_two_doors_final_v3'
V89 = Path('/Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001') / TRAINING_MAP
V88 = Path('/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded')
V88_SOURCE = '747d2b9f1eb43e21804ccef58fff4db241d1a844'
R4_SHA = 'fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071'
FOLDER = b.ROOT / 'experiments/2026-10-03-critb-rotation'


def training_path(path):
    """Reject before reading: no sibling discovery, held-out paths or symlinks."""
    path = Path(path).absolute()
    if not any(path == root or path.is_relative_to(root) for root in (V89, V88)):
        raise ValueError('not an authorized training path')
    if path.resolve() != path:
        raise ValueError('training symlink/alias is not allowed')
    return path


def load_training(gate):
    # Audit the exact v89 inputs r4 saw, even when there is no yaw excitation.
    old = json.loads((b.FOLDER / 'input_manifest_r4.json').read_bytes())
    for item in old['files']:
        path = training_path(item['path'])
        blob = path.read_bytes()
        if sha(blob) != item['sha256'] or len(blob) != item['bytes']:
            raise ValueError('v89 input differs from frozen r4 manifest')
    v89 = b.load_case(training_path(V89), gate)
    # Exact one-case path: do not discover other collections under outputs/.
    root = training_path(V88)
    folder = training_path(root / TRAINING_MAP)
    for rel in ('result.json', 'bundle.json', 'eval_only/r1/pose.jsonl', 'robots/r1/commands.jsonl'):
        training_path(folder / rel)
    inputs = []
    result = json.loads(b.read_input(training_path(root / 'result.json'), inputs))
    case_result = json.loads(b.read_input(folder / 'result.json', inputs))
    if (type(result.get('denominator')) is not int or result['denominator'] != 1
            or result.get('status') != 'COLLECTED_UNQUALIFIED'
            or result.get('unattempted') or result.get('source_unchanged') is not True
            or result.get('cases') != [case_result]):
        raise ValueError('v88 training collection incomplete/detached')
    v88 = b.load_case(folder, gate)
    if v88['source_sha'] != V88_SOURCE or v88['map_id'] != TRAINING_MAP:
        raise ValueError('wrong v88 training source/map')
    v88['inputs'].extend(inputs)
    v88['training'] = True
    cases = [v89, v88]
    for case in cases:
        if case['map_id'] != TRAINING_MAP:
            raise ValueError('only the training map is allowed')
        case['training'] = True
    return cases


def fit_mean(cases, gate):
    """Same objective, bounds, initialization and solver as r4, pooled by case."""
    samples = []
    for data in cases:
        windows = []
        for spans in data['segments']['rotate'].values():
            for h in gate['horizons_s']:
                starts, k = b.c.windows(spans, h, data['dt'])
                windows.append((starts, k, b.c.endpoint_targets(data['pose'], starts, k)[:, 2]))
        samples.append((data, windows))

    def residual(theta):
        errors = []
        for data, windows in samples:
            increments = b.c.legacy_increments(data, r4.profile(2, np.exp(theta), gate))
            p = np.r_[0., np.cumsum(increments[:, 2])]
            errors.extend(p[s+k]-p[s]-target for s, k, target in windows)
        return np.concatenate(errors)

    lower, upper = np.log([.05, .01, .005]), np.log([4., 4., .5])
    opt = least_squares(residual, np.log([1., .8, .06]), bounds=(lower, upper),
                        max_nfev=150, ftol=1e-10, xtol=1e-10, gtol=1e-10)
    rank = int(np.linalg.matrix_rank(opt.jac))
    boundary = [name for name, val, lo, hi in zip(('gain', 'tau_s', 'tau_stop_s'), opt.x, lower, upper)
                if min(val-lo, hi-val) < 1e-4]
    audit = {'success': bool(opt.success), 'rank': rank, 'boundary': boundary,
             'nfev': opt.nfev, 'residual_count': len(opt.fun),
             'rmse_rad': float(np.sqrt(np.mean(opt.fun**2)))}
    if not opt.success or rank != 3 or boundary:
        return None, audit
    return {'parameters': dict(zip(('gain', 'tau_s', 'tau_stop_s'), np.exp(opt.x).tolist())),
            'consumer_fields': r4.profile(2, np.exp(opt.x), gate),
            'scope': 'axis-only unloaded yaw; other mean axes are structural zero, not calibrated',
            'allowed_command_axis': 'turn', 'optimizer': audit, 'validation': None}, audit


def noise_groups(cases, model, gate):
    """Exact diagonal variance coefficients for a pure-yaw Euler mean.

    Translation mean is zero, so the heading Jacobian is identity. Rotation
    still mixes body x/y noise: Vx=C*a_x^2+S*a_y^2, Vy=S*a_x^2+C*a_y^2.
    C/S sum dt^2*cos/sin(heading BEFORE each tick)^2. Yaw is the same
    quadratic in noise_abs as r4. Cross covariance is checked independently
    by the frozen full-matrix evaluator after selection.
    """
    groups = []
    for data in cases:
        dt = data['dt']
        delta = b.c.legacy_increments(data, model['consumer_fields'])
        if np.any(delta[:, :2]):
            raise ValueError('rotation minimum requires a pure-yaw mean')
        for split, spans in data['segments']['rotate'].items():
            for h in gate['horizons_s']:
                starts, k = b.c.windows(spans, h, dt)
                angle = np.zeros(len(starts))
                cc, ss, sv, sv2 = (np.zeros(len(starts)) for _ in range(4))
                for tick in range(k):
                    cc += np.cos(angle)**2*dt**2
                    ss += np.sin(angle)**2*dt**2
                    v = np.abs(delta[starts+tick, 2]/dt)
                    sv += v*dt**2
                    sv2 += v**2*dt**2
                    angle += delta[starts+tick, 2]
                predicted = np.column_stack((np.zeros((len(starts), 2)), angle))
                error = predicted-b.c.endpoint_targets(data['pose'], starts, k)
                error[:, 2] = np.arctan2(np.sin(error[:, 2]), np.cos(error[:, 2]))
                groups.append({'case': data['folder'], 'split': split, 'horizon': h,
                               'error': error, 'cc': cc, 'ss': ss, 'sv': sv,
                               'sv2': sv2, 'kdt2': k*dt**2})
    return groups


def order95(values):
    index = int(np.ceil(.95*len(values)))-1
    return float(np.partition(values, index)[index])


def minimum_noise(groups, gate):
    """B's lexicographic order, with later coefficients free to increase.

    For the forward minimum, any window with S>0 can be covered by a finite
    later left coefficient. Only zero-left-coefficient windows constrain it.
    This differs from incorrectly holding left at its floor while minimizing
    forward. No tolerance replaces positive S by zero.
    """
    relative = np.asarray(gate['noise']['floor_noise_rel'])
    absolute = np.asarray(gate['noise']['floor_noise_abs']).copy()
    certificate = {}

    def choose(component, requirements):
        floor = float(absolute[component])
        required, limiting = floor, None
        for values, group, constrained_component in requirements:
            value = order95(values)
            if value > required:
                required = value
                limiting = {key: group[key] for key in ('case', 'split', 'horizon')}
                limiting.update(component=constrained_component, n=len(values),
                                required_covered=int(np.ceil(.95*len(values))))
        if not np.isfinite(required):
            raise ValueError('no finite lexicographic noise solution')
        absolute[component] = required + (1e-12 if required > floor else 0.)
        certificate[str(component)] = {'floor': floor, 'minimum_without_roundoff_slack': required,
                                       'limiting_group': limiting}

    yaw_requirements = []
    for g in groups:
        linear = 2*relative[2]*g['sv']
        fixed = relative[2]**2*g['sv2']
        need = np.maximum(g['error'][:, 2]**2/4-fixed, 0.)
        denominator = linear+np.sqrt(linear**2+4*g['kdt2']*need)
        threshold = np.divide(2*need, denominator, out=np.zeros_like(need), where=denominator > 0)
        yaw_requirements.append((threshold, g, 2))
    choose(2, yaw_requirements)
    forward_requirements = []
    for g in groups:
        for component, a, later in ((0, g['cc'], g['ss']), (1, g['ss'], g['cc'])):
            need = g['error'][:, component]**2/4
            # 0 for all windows coverable by the later coefficient. Otherwise
            # exact scalar threshold (infinity when both coefficients vanish).
            threshold = np.zeros(len(need))
            mask = later == 0
            threshold[mask] = np.sqrt(np.divide(need[mask], a[mask],
                out=np.full(mask.sum(), np.inf), where=a[mask] > 0))
            threshold[need == 0] = 0.
            forward_requirements.append((threshold, g, component))
    choose(0, forward_requirements)
    left_requirements = []
    for g in groups:
        for component, a, later in ((0, g['cc'], g['ss']), (1, g['ss'], g['cc'])):
            need = np.maximum(g['error'][:, component]**2/4-a*absolute[0]**2, 0.)
            threshold = np.sqrt(np.divide(need, later, out=np.full(len(need), np.inf), where=later > 0))
            threshold[need == 0] = 0.
            left_requirements.append((threshold, g, component))
    choose(1, left_requirements)
    return {'method': 'exact lexicographic minimum for pure yaw; relative floors then yaw/forward/left absolute',
            'noise_rel': relative.tolist(), 'noise_abs': absolute.tolist(), 'certificate': certificate,
            'roundoff_slack_if_inflated': 1e-12, 'scope': 'yaw profile only; r4 forward/left noise unchanged'}


def fit_training(cases, gate):
    active, audit = [], []
    for data in cases:
        nonzero = int(np.count_nonzero(data['u'][:, 2]))
        supported = b.axis_supported(data, 2, gate)
        audit.append({'case': data['folder'], 'turn_nonzero_ticks': nonzero,
                      'signed_steps_prbs_horizons_supported': supported,
                      'rotation_spans_ticks': data['segments']['rotate']})
        if nonzero:
            if not supported:
                return None, {'reason': 'excited training case lacks signed steps/PRBS/horizon support', 'cases': audit}
            active.append(data)
    if not active:
        return None, {'reason': 'no turn excitation', 'cases': audit}
    model, optimizer = fit_mean(active, gate)
    if model is None:
        return None, {'reason': 'mean optimizer/rank/boundary failure', 'optimizer': optimizer, 'cases': audit}
    groups = noise_groups(active, model, gate)
    noise = minimum_noise(groups, gate)
    model['consumer_fields']['noise_abs'] = noise['noise_abs']
    model['noise_selection'] = noise
    training = [{'case': data['folder'], 'scope': 'TRAINING_ONLY',
                 'metrics': b.evaluate_axis(data, 2, model['consumer_fields'], gate)} for data in active]
    minimum = min(min(row['coverage_2sigma']) for case in training for row in b.all_rows(case['metrics']))
    if minimum < .95:
        raise ValueError('noise minimum failed independent frozen covariance coverage check')
    model['minimum_training_2sigma_coverage'] = minimum
    return model, {'cases': audit, 'training': training, 'minimum_training_2sigma_coverage': minimum}


def make_candidate(previous, model, cases):
    candidate = copy.deepcopy(previous)
    candidate.update(revision='v88-consumer-r5-yaw',
                     qualification='Training-only yaw extension under 2026-10-03 delegated authority; v91 unseen/unscored.',
                     previous_revision={'path': b.CANDIDATE.name, 'sha256': R4_SHA},
                     rotation_addendum='consumer_criterion_B_rotation.json')
    candidate['candidate_axes']['rotate'] = model
    candidate['previously_seen_pose_sha256'] = sorted(set(previous['previously_seen_pose_sha256']) |
                                                     {case['pose_sha256'] for case in cases})
    candidate['motion_identification']['yaw_training_source_sha'] = V88_SOURCE
    candidate['motion_identification']['yaw_validation'] = None
    candidate['loader_requirements'] = [
        'Follow the frozen r4 loader requirements for forward/left; those profiles are unchanged.',
        'Yaw is a separate axis-only turn profile under consumer_criterion_B_rotation.json; no mixed-axis commands.',
        'Read candidate_axes.rotate.consumer_fields only after verifying candidate/addendum/public commitment hashes.',
        'All axis_validation and params.motion remain null; no MEASURED_SIM promotion or runtime loader admission.',
        'Keep Euler dt=.05, rest_noise=true, use_scale=false, scale_std=scale_walk=0, with scalar run/stop tau.'
    ]
    candidate['limitations'] = [
        'All included raw is training; no v91 raw read, hash-scan or score by this work.',
        'Criterion A remains failed, B text/thresholds and r4 forward/left profiles remain unchanged.',
        'Yaw-only noise need not equal the unchanged shared r4 translation noise.',
        'No acquisition-before-freeze claim for yaw: v91 already exists, so its new commitment is pre-scoring only.',
        'No PF posterior, mixed-axis, loaded/fine, camera, task or hardware success claim.'
    ]
    return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require_disjoint_output(args.output, V88, V89, b.FOLDER)
    args.output.mkdir(parents=True, exist_ok=False)
    gate = b.criterion()
    previous_blob = b.CANDIDATE.read_bytes()
    if sha(previous_blob) != R4_SHA:
        raise ValueError('frozen r4 candidate changed')
    cases = load_training(gate)
    model, report = fit_training(cases, gate)
    candidate = make_candidate(json.loads(previous_blob), model, cases)
    b.verify_inputs(cases)
    files = list({(r['path'], r['sha256']): r for case in cases for r in case['inputs']}.values())
    source_files = ('scripts/fit_consumer_criterion_b_rotation.py', 'scripts/fit_consumer_criterion_b.py',
                    'scripts/validate_consumer_criterion_b.py', 'scripts/fit_unloaded_consumer.py',
                    'scripts/fit_unloaded_hammerstein.py')
    manifest = {'files': files, 'source_sha256': {p: sha((b.ROOT/p).read_bytes()) for p in source_files},
                'execution_source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=b.ROOT).decode().strip(),
                'criterion_sha256': b.CRITERION_SHA256, 'r4_sha256': R4_SHA,
                'python': sys.version, 'numpy': np.__version__, 'scipy': scipy.__version__,
                'platform': platform.platform(), 'v91_raw_read': False,
                'frame_schema_note': 'frames use sim_time; not consumed. Pose and commands use t.'}
    write(args.output/'input_manifest_r5_yaw.json', manifest)
    candidate['yaw_measurement_manifest_sha256'] = sha((args.output/'input_manifest_r5_yaw.json').read_bytes())
    write(args.output/'calibration_candidate_r5_yaw.json', candidate)
    report.update(scope='TRAINING_ONLY', axis_validation=dict.fromkeys(b.AXES),
                  candidate_sha256=sha((args.output/'calibration_candidate_r5_yaw.json').read_bytes()),
                  physical_runs=0, rendering_runs=0, model_calls=0, v91_raw_read=False)
    write(args.output/'training_report_r5_yaw.json', report)
    print(json.dumps({'yaw': None if model is None else model['parameters'],
                      'minimum_training_2sigma_coverage': None if model is None else model['minimum_training_2sigma_coverage'],
                      'noise': None if model is None else model['noise_selection'],
                      'candidate_sha256': report['candidate_sha256']}))


if __name__ == '__main__':
    main()
