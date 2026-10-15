"""Finite #480 matched-cohort replay; saved RGB/features only, evaluation last.

No network/physics/renderer calls. Every expected interval is reported, including
missing inputs and HOST_ERROR. No available-case promotion.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import subprocess
import numpy as np
from harness.map_amcl import Parameters, create, compose, between
from scripts.e2e_stage_pose_eval import align, read, wrap
from scripts.extract_e2e_pose_features import availability, extract, packets, sha256, source_file, source_sha256

EXPERIMENT = Path(__file__).resolve().parents[1]/'experiments/2026-10-15-map-amcl'
CANDIDATES = tuple((o, m) for o in ('amcl_walls_v1', 'amcl_landmarks_v1')
                   for m in ('command_delta', 'fused_delta'))


def validate_features(rows, inputs):
    if len(rows) != len(inputs):
        raise ValueError('FULL_INTERVAL_FEATURES_REQUIRED')
    for r, o in zip(rows, inputs):
        for key in ('robot_id', 't', 'physical_t', 'frame_id', 'sha256', 'command_delta', 'fused_delta'):
            if r.get(key) != o[key]:
                raise ValueError('FEATURE_SOURCE_MISMATCH:'+key)
        if {int(k): int(v) for k, v in r['servo'].items()} != o['servo']:
            raise ValueError('FEATURE_SERVO_MISMATCH')
        if r.get('settled') is not True and (r['points'] or r['features']):
            raise ValueError('UNSETTLED_MEASUREMENT')
    return rows


def replay(rows, option, motion, seed=64001, static_map=None):
    pf = create(static_map, option=option, seed=seed)
    pose, poses, audit = np.zeros(3), [], []
    for i, r in enumerate(rows):
        delta = np.zeros(3) if i == 0 else np.asarray(r[motion], float)
        if pf is None:
            pose = compose(pose, delta)
            state = dict(t=r['t'], pose=pose.tolist())
        else:
            state = pf.step(t=r['t'], points=r['points'], delta=delta,
                servo={int(k): int(v) for k, v in r['servo'].items()}, features=r['features'])
            pose = np.array(state['pose'])
        poses.append(pose.copy())
        audit.append(dict(state, frame_id=r['frame_id'], sha256=r['sha256']))
    return np.asarray(poses), audit


def jump_metrics(poses, rows):
    """5cm/5deg residual slack is diagnostic, not a measured speed limit."""
    residuals, jumps = [], []
    for i in range(1, len(poses)):
        actual = between(poses[i-1], poses[i])
        command = np.asarray(rows[i]['command_delta'], float)
        residual = actual-command
        residual[2] = wrap(residual[2])
        xy, yaw = float(np.linalg.norm(residual[:2])), float(abs(np.degrees(residual[2])))
        residuals.append([xy, yaw])
        jumps.append(dict(t=rows[i]['t'], frame_id=rows[i]['frame_id'],
            issued_delta=command.tolist(), estimated_delta=actual.tolist(),
            residual_xy_m=xy, residual_yaw_deg=yaw, flagged=xy > .05 or yaw > 5.))
    a = np.asarray(residuals).reshape(-1, 2)
    summary = dict(N=len(jumps), flagged_n=sum(r['flagged'] for r in jumps),
        acceptable_n=sum(not r['flagged'] for r in jumps), slack_xy_m=.05, slack_yaw_deg=5.,
        residual_median=None if not len(a) else np.median(a, axis=0).tolist(),
        residual_p95=None if not len(a) else np.quantile(a, .95, axis=0).tolist())
    return summary, jumps


def score(poses, inputs, truth_rows, interval):
    times = np.array([x['t'] for x in truth_rows])
    if not len(times) or np.any(np.diff(times) <= 0):
        raise ValueError('EVALUATION_CLOCK_NOT_MONOTONIC')
    targets = np.array([x['t']-interval['cutoff_s']+times[0] for x in inputs])
    if (targets.min() < times[0]-1e-6 or targets.max() > times[-1]+.051 or
            not np.allclose(targets, [x['physical_t'] for x in inputs], atol=1e-5, rtol=0)):
        raise ValueError('PR480_STAGE_CLOCK_MISMATCH')
    truth = np.array([[*x['robot_xyz_m'][:2], x['robot_yaw_rad']] for x in truth_rows])
    truth[:, 2] = np.unwrap(truth[:, 2])
    matched = np.column_stack([np.interp(targets, times, truth[:, i]) for i in range(3)])
    m = align(poses, matched)
    m['passed_pose'] = bool(m['xy_median_m'] <= .05 and m['yaw_median_deg'] <= 5)
    m['passed_pr480'] = bool(m['passed_pose'] and m['path_ratio'] is not None and .9 <= m['path_ratio'] <= 1.1)
    # Alignment can hide an incorrect global map branch. Absolute error is
    # mandatory for AMCL, and is never fed back into the estimator.
    m['absolute_xy_median_m'] = float(np.median(np.linalg.norm(poses[:, :2]-matched[:, :2], axis=1)))
    m['absolute_yaw_median_deg'] = float(np.degrees(np.median(abs(wrap(poses[:, 2]-matched[:, 2])))))
    return m


def aggregate(rows, expected):
    ready = [r for r in rows if r['status'] == 'complete']
    return dict(expected_N=expected, evaluated_N=len(ready), unavailable_N=expected-len(ready),
        passed_pose_n=sum(r['metrics']['passed_pose'] for r in ready) if ready else None,
        passed_pr480_n=sum(r['metrics']['passed_pr480'] for r in ready) if ready else None,
        median={k: (float(np.median([r['metrics'][k] for r in ready
                                    if r['metrics'][k] is not None]))
                    if any(r['metrics'][k] is not None for r in ready) else None) for k in
                ('xy_median_m', 'yaw_median_deg', 'path_ratio')} if ready else None,
        jump_acceptable_n=sum(r['jumps']['acceptable_n'] for r in ready),
        jump_flagged_n=sum(r['jumps']['N']-r['jumps']['acceptable_n'] for r in ready),
        jump_N=sum(r['jumps']['N'] for r in ready))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--feature-root', type=Path)
    p.add_argument('--extract-saved-rgb', action='store_true')
    p.add_argument('--map-amcl', choices=('off', 'amcl_v1'), default='off')
    p.add_argument('--cohort', type=Path, default=EXPERIMENT/'cohort.json')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    if a.extract_saved_rgb and a.feature_root is None:
        p.error('--extract-saved-rgb needs --feature-root')
    a.output.mkdir(parents=True, exist_ok=False)
    cohort = json.loads(a.cohort.read_text())
    intervals, expected = cohort['intervals'], cohort['expected_N']
    if (expected <= 0 or len(intervals) != expected or
            len({(r['run'], r['robot']) for r in intervals}) != expected):
        raise ValueError('EXACT_COHORT_INTERVALS_REQUIRED')
    results, inventory, raw_hashes, artifacts = [], [], {}, {}
    for interval in intervals:
        run, rid = interval['run'], interval['robot']
        raw = a.raw_root/run/'raw'
        item = dict(run=run, robot=rid, N=interval['N'])
        options = [('off', 'fused_delta')]+(list(CANDIDATES) if a.map_amcl != 'off' else [])
        try:
            if interval.get('unavailable_reason'):
                raise ValueError(interval['unavailable_reason'])
            inputs = packets(raw, rid)
            if len(inputs) != interval['N']:
                raise ValueError('INTERVAL_LENGTH_MISMATCH')
            for name in ('frames.jsonl', 'ownmap.jsonl'):
                f = source_file(raw/f'robots/{rid}/{name}')
                raw_hashes[str(f)] = sha256(f)
            inventory.append(dict(item, **availability(inputs)))
            # Fresh-recording mode requires byte-verified identical frame sets
            # for ALL five estimates. Missing RGB cannot leave a baseline-only
            # available-case subset in the paired summary.
            if cohort.get('paired_recording'):
                if inventory[-1]['missing']:
                    raise ValueError('PAIRED_RGB_MISSING')
                for row in inputs:
                    if sha256(row['image_path']) != row['sha256']:
                        raise ValueError('PAIRED_RGB_HASH_MISMATCH')
            feature_dir = a.feature_root/run/rid if a.feature_root else None
            features, feature_error = None, 'SAVED_OWN_RGB_OR_VERIFIED_FEATURES_REQUIRED'
            if a.map_amcl != 'off' and feature_dir is not None:
                try:
                    if not feature_dir.exists() and a.extract_saved_rgb:
                        extract(raw, raw/'inputs/static_map.json', feature_dir, (rid,))
                    manifest = json.loads((feature_dir/'summary.json').read_text())
                    f = feature_dir/f'{rid}.jsonl'
                    if (manifest['schema'] != 'saved-own-rgb-features/1' or
                            manifest['files'][f.name] != sha256(f) or
                            manifest['static_map_sha256'] != source_sha256(raw/'inputs/static_map.json')):
                        raise ValueError('FEATURE_MANIFEST_MISMATCH')
                    if cohort.get('paired_recording'):
                        for name in ('frames.jsonl', 'ownmap.jsonl'):
                            original = source_file(raw/f'robots/{rid}/{name}')
                            if manifest['source_hashes'].get(str(original)) != sha256(original):
                                raise ValueError('FEATURE_LOG_HASH_MISMATCH')
                    features = validate_features(read(f, True), inputs)
                    raw_hashes[str(f)] = sha256(f)
                    raw_hashes[str(feature_dir/'summary.json')] = sha256(feature_dir/'summary.json')
                except (OSError, ValueError, KeyError) as error:
                    feature_error = type(error).__name__+':'+str(error)[:300]
            if cohort.get('paired_recording') and features is None:
                raise ValueError(feature_error)
            # Generate every estimate before opening evaluator output.
            produced = []
            for option, motion in options:
                name = option+'+'+motion
                if option != 'off' and features is None:
                    results.append(dict(item, candidate=name, status='missing_features', error=feature_error))
                    continue
                try:
                    static_path = raw/'inputs/static_map.json'
                    static = read(static_path) if option != 'off' else None
                    if static is not None:
                        raw_hashes[str(source_file(static_path))] = sha256(source_file(static_path))
                    poses, trace = replay(inputs if option == 'off' else features, option, motion, static_map=static)
                    jumps, jump_trace = jump_metrics(poses, inputs)
                    path = a.output/f'{run}-{rid}-{name}.jsonl'
                    with path.open('w') as stream:
                        for j, row in enumerate(trace):
                            stream.write(json.dumps(dict(row, command_check=jump_trace[j-1] if j else None),
                                                    separators=(',', ':'))+'\n')
                    artifacts[path.name] = sha256(path)
                    produced.append((name, poses, jumps, trace))
                except (OSError, ValueError, KeyError) as error:
                    results.append(dict(item, candidate=name, status='HOST_ERROR', error=str(error)))
            truth_path = source_file(raw/f'eval_only/{rid}/trajectory.jsonl')
            truth = read(truth_path, True)
            raw_hashes[str(truth_path)] = sha256(truth_path)
            for name, poses, jumps, trace in produced:
                m = score(poses, inputs, truth, interval)
                results.append(dict(item, candidate=name, status='complete', metrics=m, jumps=jumps,
                    resolved_frames=sum(r.get('resolved', False) for r in trace),
                    updates=trace[-1].get('updates', 0), resamples=trace[-1].get('resamples', 0)))
        except (OSError, ValueError, KeyError) as error:
            for option, motion in options:
                name = option+'+'+motion
                if not any(r['run'] == run and r['robot'] == rid and r['candidate'] == name for r in results):
                    results.append(dict(item, candidate=name, status='HOST_ERROR', error=str(error)))
        print(json.dumps(dict(interval=run+'/'+rid, done=len(inventory), expected=expected)), flush=True)
    # A candidate failure removes the interval from every paired aggregate,
    # while retaining each candidate's original status and trace for diagnosis.
    paired = []
    for interval in intervals:
        group = [r for r in results if (r['run'], r['robot']) == (interval['run'], interval['robot'])]
        complete = len(group) == 5 and all(r['status'] == 'complete' for r in group)
        paired.extend([r if complete else dict(r, status='paired_unavailable') for r in group])
    aggregates = {name: aggregate([r for r in results if r['candidate'] == name], expected)
                  for name in sorted({r['candidate'] for r in results})}
    paired_aggregates = {name: aggregate([r for r in paired if r['candidate'] == name], expected)
                         for name in aggregates} if a.map_amcl != 'off' else {}
    summary = dict(schema='map-amcl-replay/1', source_sha=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], text=True).strip(), python=platform.python_version(),
        platform=platform.platform(), numpy=np.__version__, parameters=asdict(Parameters()),
        initial_pose_source='uniform_static_free_space', seed=64001, aggregates=aggregates,
        comparison_complete=all(r['evaluated_N'] == expected for r in aggregates.values()) and a.map_amcl != 'off',
        paired_aggregates=paired_aggregates, cohort_sha256=sha256(a.cohort),
        gate_promotion_authorized_if_all_conditions_pass=False, physical_runs=0,
        inventory=inventory, rows=results, source_hashes=raw_hashes, artifact_sha256=artifacts,
        scope=cohort.get('scope', 'Frozen staged suffix; full interval including convergence; #480 rigid SE2 metrics; GT evaluation only'),
        caveat=cohort.get('caveat', '40 diagnostic grasp exposures include 8 staging-invalid and 2 supervisor-censored; not a valid success cohort'))
    (a.output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps(aggregates, indent=2))
    return summary


if __name__ == '__main__':
    main()
