"""Fixed own-RGB/command replay; score GT only after off/on files are closed."""
import argparse
import base64
import copy
import hashlib
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness.s2_stiff_camera_calibration import runtime_class as stiff_runtime
from harness.zone_solo_cyan_kld_start import Runtime as StartRuntime
from harness.zone_solo_cyan_look_ahead import Runtime as CarryRuntime
from harness.zone_solo_cyan_best_cluster import runtime_class, OPTION
from harness.zone_pair_highpose_exact_speedups import install

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CRITERIA = HERE/'best-cluster-criteria.json'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
rows = lambda p: [json.loads(l) for l in p.read_text().splitlines()]


def replay(which, option, out, criteria):
    cfg = criteria['recordings'][which]; raw = Path(cfg['raw'])
    start = which == 'start1052'
    bundle = read(raw/('setup_bundle.json' if start else 'bundle.json'))
    record = None if start else read(raw/'student_record.json')
    commands = read(raw/'fixed_commands.json') if start else record['commands']
    frames = rows(raw/'robots/r3/frames.jsonl')
    commands_by_t = {}
    for cmd in commands:
        commands_by_t.setdefault(round(cmd['t'], 6), []).append(copy.deepcopy(cmd))
    omit = ('drive_profile', 'stagnation_watch', 'idle_robot_contacts', 'dev_grasp_policy', 'eval_camera_trace')
    kw = {k: v for k, v in bundle['options'].items() if k not in omit}
    kw.update({k: bundle[k] for k in ('motion_model', 'pulse_calibration', 'extrinsic_calibration', 'floor_appearance')})
    if start:
        kw.update(global_localization='augmented_active_v1', particle_sampling='kld_global_v1',
            camera_pitch='stiff_target_v1', servo_stiffness='real_v1',
            stiff_camera_table=read(ROOT/'configs/calibration/s2_camera_stiff_target_v1.json'))
    else:
        kw.update({k: bundle[k] for k in ('stiff_camera_table', 'look_ahead_calibration')})
    kw['pose_estimate'] = OPTION if option == 'on' else 'off'
    _, undo = install('v98-exact-v6')
    runtime = runtime_class(stiff_runtime(StartRuntime) if start else CarryRuntime)(
        c.hp.resolve(c.MAP_ID)[0], ROOT/c.CALIBRATION, c.CALIBRATION_SHA, seed=cfg['seed'], **kw)
    provider = runtime.pose; pf = provider.provider.loc._pf
    predictions = []; snapshots = []; clouds = {}; cloud_digest = hashlib.sha256()
    wall = time.perf_counter()
    initial = commands_by_t[round(frames[0]['sim_time'], 6)].pop(0)
    runtime.initial_commands(initial['t'], {'r3': {int(k): v for k, v in initial['pulses'].items()}})
    try:
        for i, f in enumerate(frames):
            now = f['sim_time']; data = (raw/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == f['sha256']
            rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), 1), cv2.COLOR_BGR2RGB)
            verdict, _ = frame_gate.gate().assess({**f, 'image': base64.b64encode(data).decode()}, 'r3', now, ob=False)
            before = runtime.amcl_audit['updates']
            p = provider.on_frame(now, rgb if verdict == frame_gate.VALID else None)
            predictions.append(dict(t=now, t_est=p.t_est, x=p.x_m, y=p.y_m, yaw=p.yaw_rad,
                std_xy_m=p.std_xy_m, last_fix_t=p.last_fix_t,
                cluster=copy.deepcopy((p.observation_quality or {}).get('diagnostics', {}).get('pose_estimate'))))
            cloud_digest.update(pf.px.tobytes()); cloud_digest.update(pf._weights().tobytes())
            if before != runtime.amcl_audit['updates'] or i == len(frames)-1:
                snapshots.append(dict(t=now, n=pf.n, updates=runtime.amcl_audit['updates']))
                if start:
                    j = len(snapshots)-1; clouds[f'p{j}'] = pf.px.copy(); clouds[f'w{j}'] = pf._weights().copy()
            for cmd in commands_by_t.get(round(now, 6), []):
                action = {k: v for k, v in cmd.items() if k != 't'}
                runtime.on_command('r3', now, action)
            if i % 500 == 0:
                print(which, option, i, '/', len(frames), 'frames; updates', runtime.amcl_audit['updates'], flush=True)
        amcl = copy.deepcopy(runtime.amcl_audit)
        audit = copy.deepcopy(getattr(runtime, 'best_cluster_audit', None))
    finally:
        runtime.close(); undo()
    result = dict(recording=which, option=option, poses=predictions, amcl=amcl, best_cluster=audit,
        snapshots=snapshots, cloud_trajectory_sha256=cloud_digest.hexdigest(),
        source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        criteria_sha256=sha(CRITERIA), source_raw=str(raw), gt_inputs=False, physics_runs=0,
        commands_fixed=True, incidental_wall_s=time.perf_counter()-wall, performance_comparison=False,
        source_hashes={name:sha(raw/name) for name in ('robots/r3/frames.jsonl',
            'setup_bundle.json' if start else 'bundle.json', 'fixed_commands.json' if start else 'student_record.json')})
    (out/f'{which}-{option}.json').write_text(json.dumps(result)+'\n')
    if clouds: np.savez_compressed(out/f'{which}-{option}-clouds.npz', **clouds)


def score(out, criteria):
    result = dict(schema='ugrp.s2.best_cluster.result.v1', criteria=criteria,
        gt_use='evaluation after all prediction files close; never controller input',
        physics_runs=0, model_calls=0, recordings={})
    for which, cfg in criteria['recordings'].items():
        raw = Path(cfg['raw']); truth = rows(raw/'eval_only/trajectory.jsonl')
        times = np.array([r['t'] for r in truth]); xy = np.array([r['robot_xyz_m'][:2] for r in truth])
        off = read(out/f'{which}-off.json'); on = read(out/f'{which}-on.json')
        ref = read(Path(cfg['baseline_poses']))
        ref_poses = ref['poses']
        metrics = []
        for pred in (off, on):
            errors = [float(np.linalg.norm(np.array([p['x'], p['y']])-
                [np.interp(p['t_est'], times, xy[:, j]) for j in (0, 1)])) for p in pred['poses']]
            begin, end = cfg['window']
            ix = [i for i, p in enumerate(pred['poses']) if begin <= p['t'] < end]
            mse = np.square([errors[i] for i in ix])
            r = dict(option=pred['option'], final_error_m=errors[-1],
                window_xy_rmse_m=float(np.sqrt(np.mean(mse))), window_end_error_m=errors[ix[-1]],
                frames=len(errors), updates=pred['amcl']['updates'],
                final_cluster=pred['poses'][-1]['cluster'],
                uncertain_frames=sum(bool(p['cluster'] and p['cluster']['uncertain']) for p in pred['poses']))
            if which == 'start1052':
                cloud = np.load(out/f"{which}-{pred['option']}-clouds.npz")
                j = len(pred['snapshots'])-1; p = cloud[f'p{j}']; w = cloud[f'w{j}']
                actual = min(truth, key=lambda t:abs(t['t']-pred['snapshots'][-1]['t']))
                near = (np.linalg.norm(p[:, :2]-actual['robot_xyz_m'][:2], axis=1) <= .25)
                da = p[:, 2]-actual['robot_yaw_rad']
                near &= abs(np.arctan2(np.sin(da), np.cos(da))) <= np.deg2rad(15)
                r.update(truth_near_mass=float(w[near].sum()), truth_near_count=int(near.sum()))
            metrics.append(r)
        same_cloud = off['cloud_trajectory_sha256'] == on['cloud_trajectory_sha256']
        same_updates = off['amcl'] == on['amcl']
        baseline_delta = max(abs(p[k]-q[k]) for p, q in zip(off['poses'], ref_poses) for k in ('x', 'y', 'yaw'))
        result['recordings'][which] = dict(conditions=metrics, particle_trajectory_bytes_equal=same_cloud,
            amcl_audit_equal=same_updates, baseline_max_pose_delta=baseline_delta,
            baseline_frames_equal=len(off['poses'])==len(ref_poses))
    start = result['recordings']['start1052']; carry = result['recordings']['carry1051']
    result['gates'] = dict(start_error_within_25cm=start['conditions'][1]['final_error_m'] <= .25,
        unchanged_particle_trajectories=all(q['particle_trajectory_bytes_equal'] for q in result['recordings'].values()),
        unchanged_amcl_updates=all(q['amcl_audit_equal'] for q in result['recordings'].values()),
        baseline_reproduced=all(q['baseline_max_pose_delta'] <= 1e-9 and q['baseline_frames_equal'] for q in result['recordings'].values()))
    result['physical_start_admitted'] = all(result['gates'].values())
    result['hashes'] = {p.name:sha(p) for p in out.glob('*.json') if p.name != 'result.json'}
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(gates=result['gates'], metrics=result['recordings'])), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--recording', choices=('start1052', 'carry1051'))
    p.add_argument('--score', action='store_true'); a = p.parse_args(); criteria = read(CRITERIA)
    a.output.mkdir(parents=True, exist_ok=True)
    if a.score: score(a.output, criteria)
    else:
        for which in ([a.recording] if a.recording else criteria['recordings']):
            for option in ('off', 'on'):
                assert not (a.output/f'{which}-{option}.json').exists()
                replay(which, option, a.output, criteria)
