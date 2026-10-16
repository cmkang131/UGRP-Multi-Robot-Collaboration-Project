"""Opt-in, post-action geometric alignment diagnostic from saved MJWarp qpos.

This does not run physics, render, select actions or change task-success scores.
The registered validation tie-break uses this recorded geometric diagnostic.
It is narrower than the teacher's full visible/IK-qualified transition.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from act16w_runtime import frozen_source, require_gcp2, sha256

B = Path('/home/ugrp/ugrp-sim')
T = B / 'src/warp1-teacher-snapshot-6f057f7e'
TEACHER_SHA = '6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--world-root', type=Path, required=True)
    parser.add_argument('--states', type=Path, help='explicit teacher aggregate file; default owner world-root/states.npz')
    parser.add_argument('--actions', type=Path, required=True)
    parser.add_argument('--action-format', choices=('teacher', 'student'), required=True)
    parser.add_argument('--world-index', type=int, default=0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('alignment diagnostic default OFF')
    host = require_gcp2()
    source = frozen_source(Path(__file__).resolve().parents[1])
    frozen_source(T, TEACHER_SHA)
    import mujoco
    import numpy as np
    sys.path.insert(0, str(T))
    from harness.visual_arm_v3 import MOUNT_X_M
    from sim.grasp_act_release_teacher import PAD_MID_M, PAD_TOL_M

    # Qualified pad_window_v2 uses these physical pad-window values verbatim:
    # T:sim/grasp_act_release_teacher.py:46-48, solo_teacher.py:192-198.
    # Yaw <=.04 and stable >=.3s are the unchanged qualified _seek predicate
    # at solo_teacher.py:404-412. No new physical acceptance tolerance is set.
    station, xy_tol, yaw_tol, dwell = MOUNT_X_M + PAD_MID_M, PAD_TOL_M, .04, .3
    clock_tol = 1e-5  # frozen ACT ChunkExecutor/owner issued-clock tolerance
    root = args.world_root
    states_path = args.states if args.states else root / 'states.npz'
    plan = json.loads((root / 'plan.json').read_text())
    if plan['kind'] not in ('cyan', 'red', 'green', 'yellow') or plan['role'] != 'west':
        raise ValueError('qualified solo BOX west geometry only')
    scene_path = root / 'scene.json' if (root / 'scene.json').exists() else root / 'scene-index.json'
    scene = json.loads(scene_path.read_text())
    target = scene['box_replicas'][plan['item_id']]['body_name']
    # Qualified scene XML uses paths relative to its source checkout. The
    # caller runs in that same qualified cwd, as the original Owner does.
    model = mujoco.MjModel.from_xml_string((root / 'scene.xml').read_text())
    data = mujoco.MjData(model)
    base_id = model.body(plan['robot_id'] + '__robot').id
    target_id = model.body(target).id
    with np.load(states_path) as archive:
        ticks, qpos = archive['ticks'].copy(), archive['qpos'].copy()
    if qpos.shape != (len(ticks), model.nq):
        raise ValueError('saved MJWarp qpos/model dimensions differ')
    action_text = (subprocess.check_output(['zstd', '-dc', str(args.actions)], text=True)
                   if args.actions.suffix == '.zst' else args.actions.read_text())
    actions = [json.loads(line) for line in action_text.splitlines() if line.strip()]
    if args.action_format == 'student':
        # State tick k is after actor action k-1; initial tick0 has not acted.
        grasp_ticks = {i + 1 for i, row in enumerate(actions)
                       if row['skills'][args.world_index] == 'grasp'}
        if actions and actions[0]['skills'][args.world_index] == 'grasp':
            grasp_ticks.add(0)
    else:
        grasp_ticks = {i for i, row in enumerate(actions)
                       if row['student_context']['skill'] == 'grasp'}
    points, start, previous, max_dwell = [], None, None, 0.
    for tick, position in zip(ticks, qpos):
        tick = int(tick)
        if tick not in grasp_ticks:
            continue
        data.qpos[:] = position
        mujoco.mj_kinematics(model, data)  # poses only; never mj_step/mj_forward
        base_yaw = math.atan2(data.xmat[base_id, 3], data.xmat[base_id, 0])
        target_yaw = math.atan2(data.xmat[target_id, 3], data.xmat[target_id, 0])
        delta = data.xpos[target_id, :2] - data.xpos[base_id, :2]
        c, s = math.cos(base_yaw), math.sin(base_yaw)
        x, y = c * delta[0] + s * delta[1], -s * delta[0] + c * delta[1]
        angle = math.atan2(math.sin(target_yaw-base_yaw), math.cos(target_yaw-base_yaw))
        error = math.hypot(x-station*math.cos(angle), y-station*math.sin(angle))
        ready = error <= xy_tol and abs(angle) <= yaw_tol
        now = tick * .1
        if ready:
            if start is None or previous is None or abs(now-previous-.1) > clock_tol:
                start = now
            max_dwell = max(max_dwell, now-start)
        else:
            start = None
        previous = now
        points.append(dict(tick=tick, elapsed_SIM_s=now, xy_error_m=error,
                           abs_yaw_error_rad=abs(angle), geometric_ready=bool(ready)))
    if not points:
        raise ValueError('no saved grasp-state samples; cannot impute alignment')
    passed = max_dwell >= dwell - 1e-8  # identical frozen teacher time epsilon
    report = dict(status='complete', source_sha=source, host=host, seed=plan['seed'],
                  target_item_id=plan['item_id'], samples=len(points),
                  geometric_alignment_passed=passed, alignment_rejection=int(not passed),
                  max_ready_dwell_SIM_s=max_dwell,
                  min_xy_error_m=min(p['xy_error_m'] for p in points),
                  thresholds=dict(station_m=station, xy_tol_m=xy_tol,
                                  yaw_tol_rad=yaw_tol, stable_SIM_s=dwell),
                  threshold_source=dict(teacher_sha=TEACHER_SHA,
                      teacher_file_sha256=sha256(T / 'sim/grasp_act_solo_teacher.py'),
                      pad_file_sha256=sha256(T / 'sim/grasp_act_release_teacher.py'),
                      evidence='qualified pad_window_v2 physical pad window and existing _seek readiness; values unchanged'),
                  scope='post-action saved-state geometric readiness during grasp; visibility and IK are not tested, task success is unchanged; no C-physics robustness run',
                  raw=[dict(path=str(p), sha256=sha256(p)) for p in
                       (root/'scene.xml', scene_path, states_path, root/'plan.json', args.actions)],
                  points=points, reproduce=sys.argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('points', 'raw', 'reproduce')}))


if __name__ == '__main__':
    main()
