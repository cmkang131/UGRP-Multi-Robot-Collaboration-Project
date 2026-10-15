"""Evaluate existing alpha=.2 against saved issued commands and GT labels.

No fitted constants, runtime correction or sensor input. Truth is used only to
score body increments and relative trajectories. Beam's original command model
is loaded from its source function, mode=off, without importing a simulator.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.map_amcl import Parameters, between, compose
from scripts.e2e_stage_pose_eval import read, wrap
from scripts.extract_e2e_pose_features import packets, source_file, sha256


def coverage(commands, truth, parameters=Parameters()):
    commands, truth = np.asarray(commands), np.asarray(truth)
    if commands.shape != (len(truth)-1, 3) or not np.isfinite(commands).all() or not np.isfinite(truth).all():
        raise ValueError('ALIGNED_FINITE_COMMAND_TRUTH_REQUIRED')
    actual = np.array([between(a, b) for a, b in zip(truth[:-1], truth[1:])])
    residual = actual-commands
    residual[:, 2] = wrap(residual[:, 2])
    variance = parameters.alpha*np.sum(commands**2, axis=1)
    moving = variance > 1e-16
    xy = np.linalg.norm(residual[:, :2], axis=1)
    sigma = np.sqrt(variance)
    # Initial truth is used only to express evaluation in own-start coordinates.
    relative_truth = np.array([between(truth[0], p) for p in truth])
    pose, covariance, path = np.zeros(3), np.zeros((3, 3)), [np.zeros(3)]
    for d, v in zip(commands, variance):
        c, s = math.cos(pose[2]), math.sin(pose[2])
        jac = np.eye(3)
        jac[0, 2], jac[1, 2] = -s*d[0]-c*d[1], c*d[0]-s*d[1]
        covariance = jac@covariance@jac.T + np.eye(3)*v
        pose = compose(pose, d)
        path.append(pose)
    trajectory_error = np.linalg.norm(np.asarray(path)[:, :2]-relative_truth[:, :2], axis=1)
    final = pose-relative_truth[-1]
    final[2] = wrap(final[2])
    max_sigma_xy = math.sqrt(max(0., np.linalg.eigvalsh(covariance[:2, :2]).max()))
    # Hypothetical motion-only epochs, not claimed observed AMCL update times.
    epoch_residual, epoch_sigma, anchor, odom = [], [], np.zeros(3), np.zeros(3)
    start = 0
    for i, d in enumerate(commands, 1):
        odom = compose(odom, d)
        pending = between(anchor, odom)
        if np.any(abs((odom-anchor)[:2]) > parameters.update_min_d) or abs(pending[2]) > parameters.update_min_a:
            error = between(truth[start], truth[i])-pending
            error[2] = wrap(error[2])
            epoch_residual.append(float(np.linalg.norm(error[:2])))
            epoch_sigma.append(math.sqrt(parameters.alpha*float(pending@pending)))
            anchor, start = odom.copy(), i
    length = float(np.linalg.norm(actual[:, :2], axis=1).sum())
    issued_length = float(np.linalg.norm(commands[:, :2], axis=1).sum())
    return dict(transitions_N=len(commands), moving_N=int(moving.sum()),
        stationary_N=int((~moving).sum()),
        stationary_residual_gt_1mm_n=int(((~moving) & (xy > .001)).sum()),
        xy_within_1sigma_n=int((xy[moving] <= sigma[moving]).sum()),
        xy_within_3sigma_n=int((xy[moving] <= 3*sigma[moving]).sum()),
        yaw_within_3sigma_n=int((abs(residual[moving, 2]) <= 3*sigma[moving]).sum()),
        xy_sigma_ratio_median=float(np.median(xy[moving]/sigma[moving])) if moving.any() else None,
        xy_sigma_ratio_p95=float(np.quantile(xy[moving]/sigma[moving], .95)) if moving.any() else None,
        path_gt_m=length, path_issued_m=issued_length, path_ratio=issued_length/length if length > .5 else None,
        trajectory_xy_median_m=float(np.median(trajectory_error)),
        final_xy_error_m=float(np.linalg.norm(final[:2])),
        final_propagated_max_axis_sigma_m=max_sigma_xy,
        final_within_3maxsigma=bool(np.linalg.norm(final[:2]) <= 3*max_sigma_xy),
        motion_only_epochs_N=len(epoch_sigma),
        motion_only_epochs_xy_within_3sigma_n=sum(e <= 3*s for e, s in zip(epoch_residual, epoch_sigma)),
        motion_epoch_scope='Threshold schedule assuming usable measurements; camera view epochs unavailable')


def aggregate(rows):
    sums = ('transitions_N', 'moving_N', 'stationary_N', 'stationary_residual_gt_1mm_n',
            'xy_within_1sigma_n', 'xy_within_3sigma_n', 'yaw_within_3sigma_n',
            'motion_only_epochs_N', 'motion_only_epochs_xy_within_3sigma_n')
    ratios = [r['path_ratio'] for r in rows if r['path_ratio'] is not None]
    return dict(segments_N=len(rows), **{k: sum(r[k] for r in rows) for k in sums},
        path_ratio_N=len(ratios), path_ratio_median=float(np.median(ratios)) if ratios else None,
        segment_median_trajectory_xy_m=float(np.median([r['trajectory_xy_median_m'] for r in rows])),
        final_within_3maxsigma_n=sum(r['final_within_3maxsigma'] for r in rows))


def beam_command_model(source):
    # Reuse exactly the owner's existing nominal model; never fit/copy gains.
    tree = ast.parse(source.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'command_delta')
    namespace = dict(math=math)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['command_delta']


def run(raw, beam_root=None, beam_model=None):
    sources, map_rows, beam_rows = {}, [], []
    def source(path, lines=False):
        f = source_file(path)
        sources[str(f)] = sha256(f)
        return read(path, lines)
    for rid in ('r1', 'r2'):
        inputs = packets(raw, rid)
        for stem in ('frames.jsonl', 'ownmap.jsonl'):
            source(raw/f'robots/{rid}/{stem}', True)
        truth = source(raw/f'eval_only/{rid}/trajectory.jsonl', True)
        times = np.array([r['t'] for r in truth])
        if len(times) != len(inputs) or not np.allclose(times, [r['physical_t'] for r in inputs], atol=1e-6, rtol=0):
            raise ValueError('EVALUATION_CLOCK_MISMATCH')
        poses = [[*r['robot_xyz_m'][:2], r['robot_yaw_rad']] for r in truth]
        map_rows.append(dict(robot=rid, **coverage([r['command_delta'] for r in inputs[1:]], poses)))
    if beam_root is not None:
        delta = beam_command_model(beam_model)
        sources[str(beam_model)] = sha256(beam_model)
        for ep in range(16, 56):
            folder = beam_root/f'cohort-{ep//16*16:03d}'/f'episode-{ep:03d}'/'raw'
            # Do not select success cases; all 40 saved episodes / both robots.
            truth = source(folder/'eval-only.jsonl', True)
            for rid in ('r1', 'r2'):
                ledger = source(folder/f'teacher-{rid}.jsonl', True)
                if len(ledger) != len(truth) or not np.allclose(
                    [r['applied_command']['t'] for r in ledger], [r['t'] for r in truth], rtol=0, atol=1e-6):
                    raise ValueError('BEAM_COMMAND_CLOCK_MISMATCH')
                commands = [delta(ledger[i-1]['applied_command'], truth[i]['t']-truth[i-1]['t'], mode='off')
                            for i in range(1, len(truth))]
                beam_rows.append(dict(episode=ep, robot=rid,
                    **coverage(commands, [r['robots'][rid]['pose'] for r in truth])))
    return dict(schema='map-amcl-alpha-audit/1', alpha=Parameters().alpha,
        sigma_formula='sqrt(alpha * (dx**2 + dy**2 + dyaw**2))',
        map_recording=dict(rows=map_rows, aggregate=aggregate(map_rows)),
        beam=dict(rows=beam_rows, aggregate=aggregate(beam_rows)) if beam_rows else None,
        sources=sources, correction_implemented=False, gt_for_evaluation_only=True,
        interpretation='Per-step 3-sigma coverage does not remove systematic bias. First-order accumulated covariance is diagnostic, not a calibrated confidence guarantee. Zero commands imply zero AMCL process variance; residual motion is reported separately.')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--beam-root', type=Path)
    p.add_argument('--beam-model', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    if bool(a.beam_root) != bool(a.beam_model):
        p.error('beam-root and beam-model must be supplied together')
    if a.output.exists():
        raise FileExistsError(a.output)
    result = run(a.raw, a.beam_root, a.beam_model)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: v['aggregate'] for k, v in result.items() if k in ('map_recording', 'beam') and v}))


if __name__ == '__main__':
    main()
