"""Replay the actual recording controller on saved own RGB, without physics.

Issued commands, not estimated deltas or truth, are the only motion input.
Compare newly proposed commands before applying the recorded command. This is
an open-loop computation benchmark, never a new navigation success.
"""
import argparse
import base64
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import pstats
import time

import cv2
import numpy as np
from PIL import Image

from harness.active_camera import SEARCH
from harness.e2e_record_scalars import normalize
from harness.map_recording_audit import InputAudit
from harness.map_recording_speed import using, controller_profile
from scripts.e2e_stage_pose_eval import read
from scripts.extract_e2e_pose_features import packets, sha256, source_file
from scripts.profile_map_amcl import accuracy, no_material_loss, original_timing
from scripts.record_map_amcl import load_spec, make_robots
from scripts.run_e2e_ownmap_live import ownmap_record


def distribution(values):
    a = np.asarray(values, float)
    return dict(n=len(a), total_s=float(a.sum()), median_s=float(np.median(a)),
                p95_s=float(np.quantile(a, .95)), max_s=float(a.max()))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def command_schedule(raw, rid, rows):
    """Validate the 5 Hz source ledger; the final hold is shutdown, not feedback."""
    commands = read(raw/f'robots/{rid}/commands.jsonl', True)
    origin = rows[0]['physical_t']
    initial = [dict(kind='look', pan_pulse=pwm) if sid == 6 else
               dict(kind='arm', servo_id=sid, pulse=pwm) for sid, pwm in SEARCH.items()]
    if [{k: v for k, v in c.items() if k != 't'} for c in commands[1:6]] != initial:
        raise ValueError('INITIAL_COMMAND_MISMATCH')
    motion = commands[6:]
    expected = [r for i, r in enumerate(rows[:-1]) if i % 2 == 0]
    if len(motion) != len(expected)+1 or motion[-1]['kind'] != 'hold':
        raise ValueError('ISSUED_COMMAND_CADENCE_MISMATCH')
    schedule = {}
    for row, cmd in zip(expected, motion[:-1]):
        if abs(cmd['t']-origin-row['t']) > 1e-6:
            raise ValueError('ISSUED_COMMAND_TIME_MISMATCH')
        schedule[row['frame_id']] = {k: v for k, v in cmd.items() if k != 't'}
    return schedule


def top_functions(profiler):
    rows = []
    stats = profiler if isinstance(profiler, pstats.Stats) else pstats.Stats(profiler)
    for (file, line, name), (primitive, calls, own, cumulative, _) in stats.stats.items():
        rows.append(dict(file=file, line=line, function=name, calls=calls,
                         primitive_calls=primitive, self_s=own, cumulative_s=cumulative))
    return sorted(rows, key=lambda r: r['cumulative_s'], reverse=True)[:20]


def controller_accuracy(poses, inputs, truth):
    """Evaluate own-start estimates in the initial truth frame, evaluation only.

    Unlike static-map AMCL, this controller has no world-coordinate pose.
    Freeze one initial SE(2) transform, not a fitted trajectory alignment.
    """
    origin = np.asarray(truth[0]['robot_xyz_m'][:2])
    yaw = truth[0]['robot_yaw_rad']
    c, s = np.cos(yaw), np.sin(yaw)
    relative = []
    for row in truth:
        xy = (np.asarray(row['robot_xyz_m'][:2])-origin) @ np.array([[c, -s], [s, c]])
        relative.append(dict(row, robot_xyz_m=[*xy, row['robot_xyz_m'][2]],
                             robot_yaw_rad=row['robot_yaw_rad']-yaw))
    return dict(accuracy(poses, inputs, relative), frame='fixed_initial_truth_SE2_evaluation_only')


def project_first30(baselines, candidates):
    """Conditional cross-host projection; never call a measured speed pass.

    The original GCP remainder includes unmeasured non-controller work. Scaling
    ALL of it is optimistic, even if the Mac speed ratio transfers perfectly.
    Publish sensitivity to retained overhead, rather than claiming an upper
    bound or passing based on cProfile overhead.
    """
    if len(baselines) < 2 or len(candidates) < 2:
        raise ValueError('REPEATED_UNPROFILED_FULL_REPLAY_REQUIRED')
    runs = baselines+candidates
    if any(r['profile'] or r['N'] != 602 or set(r['robots']) != {'r1', 'r2'} or
           any(v['frames'] != 301 for v in r['robots'].values()) for r in runs):
        raise ValueError('REPEATED_UNPROFILED_FULL_REPLAY_REQUIRED')
    if any(r['mode'] != 'legacy' or any(v['exact_proposed_commands'] != 301 or
           v['exact_issued_commands'] != 150 for v in r['robots'].values()) for r in baselines):
        raise ValueError('ORIGINAL_RECORDING_COMMAND_PARITY_REQUIRED')
    if any(r['sources'] != runs[0]['sources'] or r['raw'] != runs[0]['raw'] for r in runs):
        raise ValueError('SAME_SAVED_INPUTS_REQUIRED')
    if len({r['mode'] for r in candidates}) != 1:
        raise ValueError('ONE_CANDIDATE_PROFILE_REQUIRED')
    total = lambda r: sum(v['controller']['total_s'] for v in r['robots'].values())
    a, b = list(map(total, baselines)), list(map(total, candidates))
    ratio = float(np.median(b)/np.median(a))
    slow_ratio = max(b)/min(a)
    original = baselines[0]['original_timing']
    residual = original['outside_physics_camera_eval_s']
    retained = original['first30_wall_s']-residual
    passed = all(no_material_loss(baselines[0]['robots'][rid]['accuracy'], r['robots'][rid]['accuracy'])
                 for r in candidates for rid in ('r1', 'r2'))
    projection = (retained+residual*ratio)/30
    return dict(schema='map-recording-first30-projection/1', candidate=candidates[0]['mode'],
        baseline_controller_s=a, candidate_controller_s=b, ratio=ratio,
        controller_reduction_fraction=1-ratio, no_material_loss=passed,
        predicted_wall_per_sim=projection,
        slow_candidate_fast_baseline_wall_per_sim=(retained+residual*slow_ratio)/30,
        retained_physics_camera_eval_s=retained, original_residual_s=residual,
        remaining_s_at_6=180-retained,
        sensitivity=[dict(retained_other_s=h, wall_per_sim=(retained+h+(residual-h)*ratio)/30)
                     for h in (0., 5., 10., 20., 40.)],
        formula='(retained_physics_camera_eval_s + H + (original_residual_s-H) * ratio) / 30',
        assumptions=['Mac controller timing ratio transfers to GCP n4-highcpu-64',
                     'Same saved path, physics/cameras/evaluation and host load',
                     'H=0 scales all unmeasured non-controller costs: optimistic, not an upper bound'],
        meets_nominal_target=bool(projection <= 6 and passed),
        actual_speed_verified=False, execution_authorized=False, ready=False)


def replay(raw, output, *, mode='batch', profile=False, limit=301):
    output.mkdir(parents=True, exist_ok=False)
    inputs = {rid: packets(raw, rid) for rid in ('r1', 'r2')}
    if any(len(rows) != 301 or not np.allclose([r['t'] for r in rows], np.arange(301)*.1,
            rtol=0, atol=1e-6) for rows in inputs.values()):
        raise ValueError('FULL_FIRST30_INPUT_REQUIRED')
    sources = {}
    for rid, rows in inputs.items():
        for name in ('frames.jsonl', 'commands.jsonl', 'ownmap.jsonl'):
            path = source_file(raw/f'robots/{rid}/{name}')
            sources[str(path)] = sha256(path)
        for row in rows:
            if sha256(row['image_path']) != row['sha256']:
                raise ValueError('SAVED_RGB_HASH_MISMATCH')
    schedules = {rid: command_schedule(raw, rid, rows) for rid, rows in inputs.items()}
    originals = {rid: read(raw/f'robots/{rid}/ownmap.jsonl', True) for rid in inputs}
    for rid, schedule in schedules.items():
        for row in originals[rid][:-1:2]:
            if schedule[row['frame_id']] != row['command']:
                raise ValueError('PROPOSED_VS_ISSUED_SOURCE_MISMATCH')
    # PhysicsBackend.reset installs these in the real recording. Reproduce the
    # same pure controller setup without constructing a world or camera.
    from harness.controller_exact_speedups import install
    recorded_setup = read(raw/'controller-speedups.json')
    setup = install(recorded_setup['mode'])
    for key in ('applied', 'fallback', 'scan_speedups', 'local_submap_active_m',
                'visibility_speedups', 'referee_event_speedups'):
        if setup.snapshot()[key] != recorded_setup[key]:
            setup.close()
            raise ValueError('RECORDED_RUNTIME_SETUP_MISMATCH:'+key)
    spec = load_spec()
    selected = mode if mode in ('exact_v1', 'squared_v1') else 'off'
    spec['performance']['controller_profile'] = selected
    robots = make_robots(spec, read(raw/'result.json')['seed'])
    for robot in robots.values():
        for sid, pwm in SEARCH.items():
            robot.commanded(dict(kind='look', pan_pulse=pwm) if sid == 6 else
                            dict(kind='arm', servo_id=sid, pulse=pwm), 0.)
    audit = InputAudit()
    generated = {rid: [] for rid in robots}
    timings = {rid: [] for rid in robots}
    profilers = {rid: cProfile.Profile() for rid in robots}
    mismatches = {rid: [] for rid in robots}
    start_load = os.getloadavg()
    started, cpu = time.perf_counter(), time.process_time()
    for tick in range(limit):
        for rid, robot in robots.items():
            packet = inputs[rid][tick]
            start = time.perf_counter()
            data = Path(packet['image_path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != packet['sha256']:
                raise ValueError('REPLAY_RGB_CHANGED')
            rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
            obs = dict(frame_id=packet['frame_id'], sim_time=packet['t'], sha256=packet['sha256'],
                       image=base64.b64encode(data).decode())
            decoded = time.perf_counter()
            controller_cpu = time.process_time()
            if profile:
                profilers[rid].enable()
            with using(mode != 'legacy'), controller_profile(selected):
                trace = audit.receive(robot, obs, rgb, packet['t'])
            if profile:
                profilers[rid].disable()
            controlled = time.perf_counter()
            controller_cpu = time.process_time()-controller_cpu
            row = normalize(ownmap_record(robot, obs, trace, packet['t']))
            # Freeze mutable histories before the next receive/command.
            generated[rid].append(json.loads(canonical(row)))
            if row != originals[rid][tick]:
                mismatches[rid].append(dict(t=packet['t'], frame_id=packet['frame_id'],
                    keys=[k for k in row if row[k] != originals[rid][tick].get(k)]))
            timings[rid].append(dict(t=packet['t'], frame_id=packet['frame_id'],
                decode_s=decoded-start, controller_s=controlled-decoded,
                controller_cpu_s=controller_cpu,
                serialize_compare_s=time.perf_counter()-controlled))
            issued = schedules[rid].get(packet['frame_id'])
            if issued is not None:
                robot.commanded(issued, packet['t'])
        if tick % 50 == 0:
            progress = dict(tick=tick, wall_s=time.perf_counter()-started,
                            cpu_s=time.process_time()-cpu, load=os.getloadavg())
            (output/'progress.json').write_text(json.dumps(progress)+'\n')
            print(json.dumps(progress), flush=True)
    elapsed, cpu_s = time.perf_counter()-started, time.process_time()-cpu
    report = dict(schema='map-recording-replay/1', mode=mode, profile=profile,
        raw=str(raw), N=2*limit, wall_s=elapsed, cpu_s=cpu_s, sources=sources,
        environment=dict(platform=platform.platform(), python=platform.python_version(),
            numpy=np.__version__, opencv=cv2.__version__, opencv_threads=cv2.getNumThreads(),
            load_start=start_load, load_end=os.getloadavg()),
        input_audit=audit.snapshot(), robots={}, original_timing=original_timing(raw),
        controller_speedups=setup.snapshot(),
        scope='Saved own RGB + issued commands; open-loop, truth evaluated only after all control',
        new_simulation_runs=0, new_renders=0, remote_connections=0)
    # No evaluation data is loaded until both robots have finished.
    for rid in robots:
        rows = generated[rid]
        truth = read(raw/f'eval_only/{rid}/trajectory.jsonl', True)
        result = dict(frames=limit, issued_commands=sum(r['frame_id'] in schedules[rid] for r in rows),
            exact_rows=limit-len(mismatches[rid]),
            exact_proposed_commands=sum(r['command'] == o['command'] for r, o in zip(rows, originals[rid])),
            exact_issued_commands=sum(r['command'] == schedules[rid][r['frame_id']]
                for r in rows if r['frame_id'] in schedules[rid]),
            mismatches=mismatches[rid],
            controller=distribution([r['controller_s'] for r in timings[rid]]),
            controller_cpu=distribution([r['controller_cpu_s'] for r in timings[rid]]),
            decode=distribution([r['decode_s'] for r in timings[rid]]),
            serialize_compare=distribution([r['serialize_compare_s'] for r in timings[rid]]),
            accuracy=controller_accuracy(np.array([r['pose_own_m'] for r in rows]), inputs[rid][:limit], truth))
        for name, records in (('ownmap', rows), ('timing', timings[rid])):
            path = output/f'{rid}-{name}.jsonl'
            path.write_text(''.join(canonical(r)+'\n' for r in records))
            result[name+'_sha256'] = sha256(path)
        if profile:
            profilers[rid].dump_stats(str(output/f'{rid}.prof'))
            result['top20_cumulative'] = top_functions(profilers[rid])
        report['robots'][rid] = result
    if profile:
        combined = pstats.Stats(profilers['r1']).add(profilers['r2'])
        combined.dump_stats(str(output/'both.prof'))
        report['top20_cumulative'] = top_functions(combined)
    (output/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    setup.close()
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=('legacy', 'batch', 'exact_v1', 'squared_v1'), default='batch')
    p.add_argument('--profile', action='store_true')
    p.add_argument('--limit', type=int, default=301)
    a = p.parse_args()
    if not 1 <= a.limit <= 301:
        p.error('limit must be between 1 and 301; prediction requires all 301')
    result = replay(a.raw, a.output, mode=a.mode, profile=a.profile, limit=a.limit)
    print(json.dumps({rid: {k: r[k] for k in ('exact_rows','exact_proposed_commands','controller')}
                      for rid, r in result['robots'].items()}))


if __name__ == '__main__':
    main()
