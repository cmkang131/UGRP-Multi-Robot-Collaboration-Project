"""Describe retained TRAIN DAgger states against the recorded teacher path.

Saved full qpos is evaluation-only here; metrics use the robot root pose.
No teacher query, physics step, admission threshold or policy change is introduced.
Nearest-path distances include the teacher's finite sampling resolution;
they do not classify recovery states or establish sufficient coverage.
"""
import argparse
import json
from pathlib import Path
import sys

from act16w_runtime import ACT_SHA, frozen_source, require_gcp2, sha256
from act16w_dagger import prepare_single_step

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
ACT = B/'src'/ACT_SHA


def read(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('collection', 'teacher-records', 'out', 'summary-out'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    frozen_source(ACT, ACT_SHA)
    import numpy as np
    import mujoco
    sys.path.insert(0, str(ACT))
    from harness import grasp_act_contract as contract

    def poses(model, state_path):
        data = mujoco.MjData(model)
        robot = model.body('r1__robot').id
        with np.load(state_path) as state:
            ticks, qpos = state['ticks'].copy(), state['qpos'].copy()
        if qpos.shape != (len(ticks), model.nq):
            raise ValueError('saved pose dimensions differ')
        result = {}
        for tick, pose in zip(ticks, qpos):
            data.qpos[:] = pose
            mujoco.mj_kinematics(model, data)
            rot = data.xmat[robot].reshape(3, 3)
            result[int(tick)] = [*data.xpos[robot, :2], np.arctan2(rot[1, 0], rot[0, 0])]
        return result

    batch = read(a.collection/'summary.json')
    if not batch['complete'] or batch['N'] != 20:
        raise ValueError('completed registered20 TRAIN prefixes required')
    teacher = {}
    for group in sorted(a.teacher_records.glob('group-*')):
        root = group/'controller'
        report = read(root/'summary.json')
        for world, seed in enumerate(report['world_seeds']):
            if seed in teacher:
                raise ValueError('duplicate teacher start')
            teacher[seed] = root/f'world-{world:03d}-states.npz'

    rows, points, receipts = [], [], []
    for collection in map(Path, batch['collections']):
        audit = read(collection/'owner/oracle-audit.json')
        plans = read(collection/'initial-plans.json')['episodes']
        camera = read(collection/'owner/RUN_META.json')['camera']
        period = camera.get('period_s', .1)  # frozen native640x480/10Hz contract
        if period != .1:
            raise ValueError('registered10Hz camera contract required')
        for world, plan in enumerate(plans):
            seed = plan['seed']
            raw = collection/f'world-{world:03d}'
            owner = collection/f'owner/world-{world:03d}'
            obs, labels = lines(raw/'student-r1.jsonl'), lines(raw/'teacher-r1.jsonl')
            valid, _ = prepare_single_step(obs, labels, contract=contract, audit=audit)
            xml, states, reference = owner/'scene.xml', owner/'states.npz', teacher[seed]
            model = mujoco.MjModel.from_xml_string(xml.read_text())
            if model.opt.noslip_iterations != 0:
                raise ValueError('native0 saved student scene required')
            student, expert = poses(model, states), poses(model, reference)
            path = np.array(list(expert.values()))
            initial = np.asarray(student[0])-np.asarray(expert[0])
            retained = []
            for target in valid:
                index = target['observation_index']
                if index == 0:
                    continue
                tick = index  # each active student observation is one fixed0.1SIM tick
                if tick not in student or tick not in expert:
                    raise ValueError('retained observation lacks matching saved tick')
                robot = np.asarray(student[tick])
                same = np.asarray(expert[tick])
                distance = np.linalg.norm(path[:, :2]-robot[:2], axis=1)
                point = dict(seed=seed, observation_index=index, elapsed_SIM_s=tick*period,
                    same_elapsed_robot_xy_distance_m=float(np.linalg.norm(robot[:2]-same[:2])),
                    same_elapsed_robot_yaw_abs_rad=float(abs(np.arctan2(np.sin(robot[2]-same[2]), np.cos(robot[2]-same[2])))),
                    nearest_recorded_teacher_xy_distance_m=float(distance.min()))
                retained.append(point)
            rows.append(dict(seed=seed, kind=plan['kind'], retained_noninitial_N=len(retained),
                initial_robot_pose_exact=bool(np.all(initial == 0)),
                initial_robot_pose_difference=initial.tolist(),
                last_retained_elapsed_SIM_s=retained[-1]['elapsed_SIM_s'] if retained else None))
            points.extend(retained)
            receipts.extend(dict(path=str(x), sha256=sha256(x)) for x in (xml, states, reference, raw/'student-r1.jsonl', raw/'teacher-r1.jsonl'))
    if len(rows) != 20 or {x['seed'] for x in rows} != set(batch['requested_seeds']):
        raise ValueError('exact registered20-start coverage required')
    metrics = {}
    for key in ('same_elapsed_robot_xy_distance_m', 'same_elapsed_robot_yaw_abs_rad', 'nearest_recorded_teacher_xy_distance_m'):
        values = [x[key] for x in points]
        metrics[key] = dict(N=len(values), quantiles=dict(zip(('min', 'p50', 'p95', 'max'), map(float, np.quantile(values, [0, .5, .95, 1]))))) if values else dict(N=0)
    summary = dict(status='complete', complete=True, source_sha=source, host=host,
        N=20, retained_noninitial_N=len(points), rows=rows, distributions=metrics,
        physics_steps=0, teacher_queries=0, cargo_pose_metrics=False,
        privileged_saved_qpos_used_for_offline_metrics=True,
        scope=__doc__, reproduce=sys.argv, raw=receipts)
    with a.out.open('x') as f:
        json.dump({**summary, 'points': points}, f, indent=2); f.write('\n')
    with a.summary_out.open('x') as f:
        json.dump({**summary, 'full_report':dict(path=str(a.out), sha256=sha256(a.out))}, f, indent=2); f.write('\n')
    print(json.dumps(dict(status='complete', N=20, retained_noninitial_N=len(points), distributions=metrics)))


if __name__ == '__main__':
    main()
