"""Hash-verified saved RGB replay, stage seconds and evaluation-only accuracy.

No network, simulation or camera rendering. Missing frames fail closed before
any estimator runs. AMCL pipeline timings cannot predict the recording speed:
the recorder uses a different, self-mapping controller. Keep those costs apart.
"""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import time

import numpy as np
from PIL import Image

from harness.map_amcl_profiles import PROFILES, RGBPipeline, parameters_for
from scripts.extract_e2e_pose_features import availability, packets, sha256, source_file
from scripts.e2e_stage_pose_eval import read, wrap
from scripts.replay_map_amcl import score


def accuracy(poses, inputs, truth):
    result = score(poses, inputs, truth, dict(cutoff_s=inputs[0]['t']))
    times = np.array([r['t'] for r in truth])
    xyz = np.array([r['robot_xyz_m'][:2] for r in truth])
    yaw = np.unwrap([r['robot_yaw_rad'] for r in truth])
    targets = [r['physical_t'] for r in inputs]
    xy_error = np.linalg.norm(poses[:, :2]-np.column_stack([
        np.interp(targets, times, xyz[:, i]) for i in range(2)]), axis=1)
    yaw_error = np.degrees(abs(wrap(poses[:, 2]-np.interp(targets, times, yaw))))
    result.update(absolute_xy_p95_m=float(np.quantile(xy_error, .95)),
                  absolute_yaw_p95_deg=float(np.quantile(yaw_error, .95)), N=len(poses))
    return result


def no_material_loss(base, candidate):
    # Diagnostic tolerances registered before data: no trimming unresolved rows.
    tolerances = dict(absolute_xy_median_m=.02, absolute_xy_p95_m=.05,
                      absolute_yaw_median_deg=2., absolute_yaw_p95_deg=5.)
    return all(candidate[k] <= base[k]+slack for k, slack in tolerances.items())


def original_timing(raw):
    first = read(raw/'first30.json')
    host = read(raw/'host-timing.json')
    camera = read(raw/'camera-render.json')
    wall = first['wall_per_sim']*30
    physics = host['timers']['physics_advance']['wall_s']
    evaluation = host['timers']['eval_sample_including_io']['wall_s']
    fixed = physics+camera['capture_wall_s']+evaluation
    remainder = wall-fixed
    return dict(first30_wall_s=wall,
                first30_wall_per_sim=first['wall_per_sim'], host_timing=host,
                physics_advance_s=physics, camera_capture_s=camera['capture_wall_s'],
                camera_render_encode_hash_s=camera['render_wall_s'],
                evaluation_s=evaluation, outside_physics_camera_eval_s=remainder,
                pure_render_s=None,
                render_scope='Original capture includes render/encode/hash; pure render not instrumented',
                budget=dict(assumption='Same physics/camera/eval costs; all remaining work may change',
                    retained_wall_per_sim=fixed/30,
                    remaining_s_at_6=180-fixed,
                    remaining_reduction_fraction_at_6=1-(180-fixed)/remainder,
                    remaining_s_at_3_5=105-fixed,
                    remaining_reduction_fraction_at_3_5=1-(105-fixed)/remainder))


def controller_replay(raw, inputs, *, rectangle_batch):
    """Actual recorder actor, saved issued commands; open-loop replay only."""
    import base64
    from harness.active_camera import SEARCH
    from harness.map_recording_audit import Metrics
    from harness.map_recording_speed import using
    from harness.e2e_record_scalars import normalize
    from scripts.record_map_amcl import load_spec, make_robots
    from scripts.run_e2e_ownmap_live import ownmap_record
    robots = make_robots(load_spec(), read(raw/'result.json')['seed'])
    metrics = Metrics()
    original = {rid: read(raw/f'robots/{rid}/ownmap.jsonl', True) for rid in inputs}
    poses = {rid: [] for rid in inputs}
    exact = {rid: 0 for rid in inputs}
    for rid, robot in robots.items():
        metrics.wrap(robot.goal.sensor, 'measure', 'record_landmark_features')
        metrics.wrap(robot.goal.e2e_gate, 'observe', 'record_boundary_features')
        mapper = robot.goal.explorer.memory.self_map
        metrics.wrap(mapper, '_observe', 'record_mapper_measurement')
        metrics.wrap(mapper, 'resample_if_needed', 'record_mapper_resample')
        for sid, pwm in SEARCH.items():
            robot.commanded(dict(kind='look', pan_pulse=pwm) if sid == 6 else
                            dict(kind='arm', servo_id=sid, pulse=pwm), 0.)
    start = time.perf_counter()
    for tick in range(len(next(iter(inputs.values())))):
        for rid, robot in robots.items():
            r = inputs[rid][tick]
            with metrics.measure('decode_io'):
                data = Path(r['image_path']).read_bytes()
                if hashlib.sha256(data).hexdigest() != r['sha256']:
                    raise ValueError('REPLAY_RGB_CHANGED')
                rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
            obs = dict(frame_id=r['frame_id'], sim_time=r['t'], sha256=r['sha256'],
                       image=base64.b64encode(data).decode())
            with metrics.measure('record_controller_other'), using(rectangle_batch):
                trace = robot.receive(obs, rgb)
            with metrics.measure('serialize'):
                row = normalize(ownmap_record(robot, obs, trace, r['t']))
            exact[rid] += int(row == original[rid][tick])
            poses[rid].append(row['pose_own_m'])
            if tick % 2 == 0:
                robot.commanded(original[rid][tick]['command'], r['t'])
    return dict(wall_s=time.perf_counter()-start, timing=metrics.snapshot(),
                exact_original_rows=exact, N=sum(map(len, inputs.values())),
                rectangle_batch=rectangle_batch, map_amcl_calls=0,
                scope='Recorded command replay; no new closed-loop path')


def run(raw, *, profiles=PROFILES, repeats=2, include_controller=False):
    inputs = {rid: packets(raw, rid) for rid in ('r1', 'r2')}
    inventory = {rid: availability(rows) for rid, rows in inputs.items()}
    sources = {str(source_file(raw/f'robots/{rid}/{name}')):
               sha256(source_file(raw/f'robots/{rid}/{name}'))
               for rid in inputs for name in ('frames.jsonl', 'ownmap.jsonl')}
    report = dict(schema='map-amcl-amcl4-replay/1', raw=str(raw), inventory=inventory,
        sources=sources, environment=dict(platform=platform.platform(), load=os.getloadavg()),
        input_scope='own RGB, own issued motion/servo, static map only; truth evaluated last',
        profiles={p: asdict(parameters_for(p)) for p in profiles}, runs=[],
        original=original_timing(raw), prediction=dict(wall_per_sim=None,
        ready=False, reason='AMCL_NOT_IN_RECORDING_CONTROL_PATH'),
        new_simulation_runs=0, new_camera_renders=0, remote_connections=0)
    missing = sum(r['missing'] for r in inventory.values())
    if missing:
        report.update(status='BLOCKED_MISSING_SAVED_RGB', missing_rgb=missing,
            comparisons=[dict(profile=p, evaluated_N=0, expected_N=2,
                              stage_seconds=None, accuracy=None, adopted=False) for p in profiles])
        return report
    if any(len(r) != 301 or not np.allclose([v['t'] for v in r], np.arange(301)*.1,
                                           rtol=0, atol=1e-6) for r in inputs.values()):
        raise ValueError('EXACT_FIRST30_301_FRAMES_REQUIRED')
    for rows in inputs.values():
        for r in rows:
            if sha256(r['image_path']) != r['sha256']:
                raise ValueError('SAVED_RGB_HASH_MISMATCH')
    static_map = read(raw/'inputs/static_map.json')
    sources[str(source_file(raw/'inputs/static_map.json'))] = sha256(source_file(raw/'inputs/static_map.json'))
    trajectories = []
    for repeat in range(repeats):
        order = list(profiles) if repeat % 2 == 0 else list(reversed(profiles))
        for profile in order:
            for rid, rows in inputs.items():
                pipeline = RGBPipeline(static_map, profile=profile)
                states, poses = [], []
                started, cpu = time.perf_counter(), time.process_time()
                for r in rows:
                    with pipeline.metrics.measure('decode_io'):
                        data = Path(r['image_path']).read_bytes()
                        if hashlib.sha256(data).hexdigest() != r['sha256']:
                            raise ValueError('REPLAY_RGB_CHANGED')
                        rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
                    state = pipeline.step(t=r['t'], rgb=rgb, delta=r['command_delta'], servo=r['servo'])
                    states.append(state)
                    poses.append(state['pose'])
                report['runs'].append(dict(profile=profile, repeat=repeat, robot=rid,
                    wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
                    timing=pipeline.metrics.snapshot(), N=len(rows),
                    extracted_n=sum(s['amcl4']['extracted'] for s in states),
                    measurement_n=pipeline.pf.updates, resample_n=pipeline.pf.resamples,
                    particles_min=min(s['n'] for s in states), particles_max=max(s['n'] for s in states),
                    poses_sha256=hashlib.sha256(np.asarray(poses).tobytes()).hexdigest()))
                trajectories.append(np.asarray(poses))
    # The estimator never sees these truth rows or the initial truth pose.
    truth = {rid: read(raw/f'eval_only/{rid}/trajectory.jsonl', True) for rid in inputs}
    for rid in inputs:
        source = source_file(raw/f'eval_only/{rid}/trajectory.jsonl')
        sources[str(source)] = sha256(source)
    for result, poses in zip(report['runs'], trajectories):
        result['accuracy'] = accuracy(poses, inputs[result['robot']], truth[result['robot']])
    report['comparisons'] = []
    for profile in profiles:
        rows = [r for r in report['runs'] if r['profile'] == profile]
        passed = []
        for row in rows:
            base = next((b for b in report['runs'] if b['profile'] == 'off' and
                         b['robot'] == row['robot'] and b['repeat'] == row['repeat']), None)
            passed.append(base is not None and no_material_loss(base['accuracy'], row['accuracy']))
        report['comparisons'].append(dict(profile=profile, evaluated_N=2, expected_N=2,
            no_material_loss=all(passed), wall_s_median=float(np.median([
                sum(r['wall_s'] for r in rows if r['repeat'] == i) for i in range(repeats)])),
            adopted=False, reason='Offline candidate; recording controller is separate'))
    if include_controller:
        report['controller_replays'] = [controller_replay(raw, inputs, rectangle_batch=b)
                                       for b in (False, True, True, False)]
    report['status'] = 'OFFLINE_COMPLETE_RECORDING_SPEED_UNVERIFIED'
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--profiles', nargs='+', choices=PROFILES, default=PROFILES)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--include-controller', action='store_true')
    a = p.parse_args(argv)
    if a.repeats < 2 or 'off' not in a.profiles or len(set(a.profiles)) != len(a.profiles):
        p.error('At least two repetitions and a unique off baseline are required')
    if a.output.exists():
        raise FileExistsError(a.output)
    result = run(a.raw, profiles=a.profiles, repeats=a.repeats, include_controller=a.include_controller)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'], output=str(a.output))))
    return 2 if result['status'].startswith('BLOCKED') else 0


if __name__ == '__main__':
    raise SystemExit(main())
