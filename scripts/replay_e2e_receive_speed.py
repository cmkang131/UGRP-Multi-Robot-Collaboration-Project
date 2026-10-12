"""Fixed saved own RGB -> e2e Robot.receive replay; no simulator, render or model.

Mac-side equivalence/benchmark adapter for exact speed toggles. Each robot gets
a fixed list of saved JPEG frames (decoded once, never re-rendered). After each
receive the robot's own nav command is fed back exactly as the live runner
does during mapping. Physics/camera/render cadence are not involved: the
images do not respond to commands, so this is an open-loop controller replay,
not an E2E counterfactual.

Per receive it records digests of the trace, nav command, wall segments,
own_inputs_at output and the RBPF state (scripts.e2e_speed_measure.rbpf_digest).
"""
import argparse
import base64
import copy
import cProfile
import hashlib
import json
import os
from pathlib import Path
import pstats
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STUDY = dict(event_driven_llm=True, compact_prompt_v1=True, prompt_lang='en')
E2E = dict(setdown_only_when_relook='on_v1', goal_geometry='e2e_b80_v1',
           exploration_progress='frontier_progress_v1', pose_fix='innovation',
           path_follow='rpp_v1', stall_odometry='rgb_pulse_gate_v1',
           stall_recovery='backup_replan_v1', stall_noise='amcl_alpha_v1',
           mapping_budget_s=1800.)
V200 = dict(provenance_index=True, sha_validation_cache=True, omit_discarded_copy=True,
            scalar_cells=True, geometry_cache=True)


def canonical(value):
    def default(x):
        if isinstance(x, np.ndarray):
            return dict(dtype=x.dtype.str, shape=list(x.shape), sha256=hashlib.sha256(x.tobytes()).hexdigest())
        if isinstance(x, np.generic):
            return dict(np_scalar=x.dtype.str, value=x.tobytes().hex())
        if isinstance(x, (set, frozenset)):
            return dict(set=sorted(repr(v) for v in x))
        return dict(repr=repr(x))
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     default=default).encode()).hexdigest()


def load_frames(spec):
    """spec: robot=dir[:limit]; JPEG bytes and decoded RGB, sorted by name."""
    frames = {}
    for item in spec:
        rid, path = item.split('=', 1)
        limit = None
        if ':' in path:
            path, limit = path.rsplit(':', 1)
            limit = int(limit)
        files = sorted(Path(path).glob('*.jpg'))[:limit]
        rows = []
        for f in files:
            data = f.read_bytes()
            bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            rows.append(dict(name=f.name, jpeg=data, sha256=hashlib.sha256(data).hexdigest(),
                             rgb=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        if not rows:
            raise ValueError('NO_FRAMES:' + path)
        frames[rid] = rows
    return frames


def build_robots(speedups, seed=61001):
    from harness.controller_exact_speedups import install as controller_speedups
    from harness.e2e_exact_speedups import Options as SpeedOptions
    from harness.e2e_live_mapping import Robot
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.s4_event_policy import Options
    from harness.active_camera import SEARCH
    installed = controller_speedups()
    cov = json.loads((ROOT / 'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robots = {}
    for i, rid in enumerate(('r1', 'r2', 'r3')):
        robots[rid] = Robot(rid, seed + i, cov, Options(**STUDY), relook=E2E['setdown_only_when_relook'],
            goal_geometry=E2E['goal_geometry'], exploration_progress=E2E['exploration_progress'],
            pose_fix=E2E['pose_fix'], path_follow=E2E['path_follow'],
            stall_options=StallOptions(E2E['stall_odometry'], E2E['stall_recovery'], E2E['stall_noise']),
            mapping_budget_s=E2E['mapping_budget_s'], exact_speedups=SpeedOptions(**speedups))
        robots[rid].decider = 'off'
    for rid, robot in robots.items():
        for sid, pwm in SEARCH.items():
            a = dict(kind='look', pan_pulse=pwm) if sid == 6 else dict(kind='arm', servo_id=sid, pulse=pwm)
            robot.commanded(a, 0.)
    return robots, installed


def replay(frames, speedups, *, profile=None, period=.2):
    from scripts.e2e_speed_measure import rbpf_digest
    robots, installed = build_robots(speedups)
    rows = []
    n = max(len(v) for v in frames.values())
    profiler = cProfile.Profile() if profile else None
    receive_s = 0.
    for k in range(n):
        now = round((k + 1) * period, 8)
        for rid, robot in robots.items():
            if k >= len(frames[rid]):
                continue
            f = frames[rid][k]
            obs = dict(frame_id=k + 1, sim_time=now, sha256=f['sha256'],
                       image=base64.b64encode(f['jpeg']).decode())
            rgb = f['rgb'].copy()
            start = time.perf_counter()
            if profiler: profiler.enable()
            error = None
            try:
                trace = robot.receive(obs, rgb)
            except Exception as exc:  # recorded, then the robot is retired
                trace, error = None, f'{type(exc).__name__}:{exc}'
            if profiler: profiler.disable()
            elapsed = time.perf_counter() - start
            receive_s += elapsed
            row = dict(robot=rid, frame=k + 1, t=now, receive_s=elapsed, error=error,
                       rgb_unchanged=bool(np.array_equal(rgb, f['rgb'])))
            if error is None:
                try:
                    inputs = robot.own_inputs_at(now)
                    inputs_digest = canonical(inputs)
                except Exception as exc:
                    inputs_digest = f'{type(exc).__name__}:{exc}'
                row.update(trace=canonical(trace), command=robot.nav_command,
                           command_digest=canonical(robot.nav_command),
                           wall_segments=canonical(robot.wall_segments),
                           own_inputs=inputs_digest, rbpf=rbpf_digest(robot),
                           pose=canonical(robot.goal.explorer.local_pose))
                if rid != 'r3' and robot.packet is None:
                    robot.commanded(copy.deepcopy(robot.nav_command), now)
            else:
                frames[rid] = frames[rid][:k]
            rows.append(row)
    if profiler:
        profiler.dump_stats(profile)
    from harness.e2e_exact_speedups2 import STATS
    snapshot = installed.snapshot()
    snapshot['exact_speedups2'] = dict(STATS)
    return rows, receive_s, snapshot


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--frames', action='append', required=True, help='robot=dir[:limit]')
    p.add_argument('--speedups', default='v200', help="'off', 'v200' or JSON of e2e_exact_speedups fields")
    p.add_argument('--extra', default='{}', help='JSON added to the speedup fields')
    p.add_argument('--output', required=True)
    p.add_argument('--profile')
    a = p.parse_args(argv)
    os.environ.setdefault('UGRP_CONTROLLER_VISIBILITY_SPEEDUPS', 'shared-v1')
    speed = {} if a.speedups == 'off' else dict(V200) if a.speedups == 'v200' else json.loads(a.speedups)
    speed.update(json.loads(a.extra))
    frames = load_frames(a.frames)
    started = time.perf_counter()
    rows, receive_s, controller = replay(frames, speed, profile=a.profile)
    out = dict(schema='ugrp.e2e_receive_replay.v1', speedups=speed, frames={r: [f['name'] for f in v] for r, v in frames.items()},
               frame_sha256={r: [f['sha256'] for f in v] for r, v in frames.items()},
               receives=len(rows), errors=sum(r['error'] is not None for r in rows),
               receive_s=receive_s, wall_s=time.perf_counter() - started,
               controller_speedups=controller.get('applied'), exact_speedups2=controller['exact_speedups2'], rows=rows)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(out, sort_keys=True, default=str))
    print(json.dumps({k: out[k] for k in ('receives', 'errors', 'receive_s', 'wall_s', 'exact_speedups2')}))


if __name__ == '__main__':
    main()
