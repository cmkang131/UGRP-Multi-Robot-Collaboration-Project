"""Read-only audit of saved logs; no simulation or controller imports."""
import argparse
import hashlib
import json
import math
import subprocess
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def decoded(data, name):
    return subprocess.check_output(['zstd', '-qdc'], input=data) if name.endswith('.zst') else data


def wrap(x):
    return np.arctan2(np.sin(x), np.cos(x))


def stats(xs):
    a = np.asarray(xs, dtype=float)
    return {'n': len(xs), 'median': float(np.median(a)), 'p95': float(np.quantile(a, .95)),
            'max': float(a.max())} if len(a) else {'n': 0, 'median': None, 'p95': None, 'max': None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--evidence-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    inputs, members = {}, {}
    for archive in ('selected-evaluation.tar.gz', 'selected-pose-truth.tar.gz'):
        path = a.evidence_root/archive
        inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        with tarfile.open(path) as tar:
            for f in tar.getmembers():
                data = tar.extractfile(f).read()
                members[f.name.removesuffix('.zst')] = decoded(data, f.name)

    def read(path, lines=False):
        path = Path(path)
        if not path.exists(): path = Path(str(path)+'.zst')
        if not path.exists(): return None
        data = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(data).hexdigest()
        raw = decoded(data, str(path))
        return [json.loads(x) for x in raw.splitlines() if x.strip()] if lines else json.loads(raw)

    def remote(run, rel, lines=False):
        raw = members.get(run+'/'+rel)
        if raw is None: return None
        return [json.loads(x) for x in raw.splitlines() if x.strip()] if lines else json.loads(raw)

    rows, aggregate, errors = [], defaultdict(list), defaultdict(lambda: defaultdict(list))
    for name in sorted(set(x.split('/')[0] for x in members)):
        result = remote(name, 'raw/result.json') or {}
        cohort = name.rsplit('-', 2)[0]
        root = a.source_root/'outputs/azure3-runs'/name/'raw'
        trace = read(root/'transport-trace.json') or []
        held = remote(name, 'raw/eval_only/stage-held.jsonl', True)
        beam = remote(name, 'raw/eval_only/referee_truth.jsonl', True)
        phase = [x for x in trace if x.get('event') == 'phase']
        cutoff = next((x['t'] for x in phase if x.get('state') == 'align'), None)
        robot_rows = []
        for rid in ('r1', 'r2'):
            own = read(root/f'robots/{rid}/ownmap.jsonl', True)
            gt = read(root/f'eval_only/{rid}/trajectory.jsonl', True)
            cmd = read(root/f'robots/{rid}/commands.jsonl', True)
            if not own:
                robot_rows.append({'robot': rid, 'status': 'missing_ownmap', 'stages': None})
                continue
            approach = [x.get('carrier_approach') or {} for x in own]
            obs = [(x.get('own_beam_observation') or {}).get('result') or {} for x in own]
            ready = any(x.get('robot_id') == rid and x.get('event') == 's3_coarse_fine'
                        and x.get('phase') == 'ready' for x in trace)
            seen = any(x.get('visible') or x.get('body_visible') for x in obs)
            estimated = any(x.get('own_beam') for x in own)
            station = any(x.get('distance_m', math.inf) <= .08 for x in approach)
            align_enter = any(x.get('status') == 'visual_servo' for x in approach)
            closed = any(x.get('kind') == 'arm' and x.get('servo_id') == 1
                         and x.get('pulse', 2500) <= 1600 for x in cmd or []) if cmd is not None else None
            lifted = any(x.get('grasp_lift_labels', {}).get(rid, False) for x in held) if held is not None else None
            both = any(all(x.get('grasp_lift_labels', {}).get(r, False) for r in ('r1', 'r2'))
                       for x in held) if held is not None else None
            stages = dict(seen_current_segment=seen, estimated=estimated, station_estimated_8cm=station,
                          fine_alignment_entered=align_enter, alignment_ready=ready,
                          close_command=closed, closed_measured=None, held=lifted, joint_held=both)
            reason_counts = Counter(x.get('reason', 'unspecified') for x in obs if not x.get('visible'))
            failure = ('no_current_detection' if not seen else 'no_estimate' if not estimated else
                       'no_estimated_station_arrival' if not station else 'no_fine_alignment' if not align_enter else
                       'no_ready' if not ready else 'no_close_command' if not closed else
                       'no_held' if not lifted else 'no_joint_held' if not both else None)
            rr = {'robot': rid, 'status': 'read', 'samples': len(own), 'stages': stages,
                  'first_unreached_stage': failure, 'miss_reason_frames': dict(reason_counts)}
            # Post-hoc SE(2) fit is diagnostic residual, not global localization accuracy.
            if gt and cutoff is not None:
                ts = np.array([x['t'] for x in gt])
                target = np.array([x['t']-cutoff+ts[0] for x in own])
                if target.min() < ts[0]-.051 or target.max() > ts[-1]+.051:
                    rr['error_status'] = 'clock_out_of_bounds'
                else:
                    g = np.array([[*x['robot_xyz_m'][:2], x['robot_yaw_rad']] for x in gt])
                    g[:, 2] = np.unwrap(g[:, 2])
                    truth = np.column_stack([np.interp(target, ts, g[:, i]) for i in range(3)])
                    poses = np.array([x['pose_own_m'] for x in own])
                    u, _, vt = np.linalg.svd((poses[:, :2]-poses[:, :2].mean(0)).T @
                                            (truth[:, :2]-truth[:, :2].mean(0)))
                    rot = vt.T @ u.T
                    if np.linalg.det(rot) < 0: vt[1] *= -1; rot = vt.T @ u.T
                    offset = truth[:, :2].mean(0)-poses[:, :2].mean(0)@rot.T
                    err = np.linalg.norm(poses[:, :2]@rot.T+offset-truth[:, :2], axis=1)
                    yawerr = np.degrees(np.abs(wrap(poses[:, 2]+math.atan2(rot[1, 0], rot[0, 0])-truth[:, 2])))
                    rr['posthoc_pose_residual'] = {'xy_m': stats(err), 'yaw_deg': stats(yawerr)}
                    bt = np.array([x['t'] for x in beam]) if beam else None
                    for i, x in enumerate(own):
                        stage = (x.get('carrier_approach') or {}).get('status', 'none')
                        bucket = 'fine' if stage == 'visual_servo' else 'approach_or_search'
                        errors[cohort+'/'+bucket]['pose_xy_m'].append(float(err[i]))
                        errors[cohort+'/'+bucket]['pose_yaw_deg'].append(float(yawerr[i]))
                        ob = obs[i]
                        if not beam or not ob.get('visible') or ob.get('grip_base_m') is None: continue
                        k = int(np.argmin(abs(bt-target[i])))
                        if abs(bt[k]-target[i]) > .051: continue
                        b = beam[k]['items']['beam_1']; yaw = truth[i, 2]
                        R = np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])
                        ends = [np.array([b['x']+s*.27*math.cos(b['yaw']), b['y']+s*.27*math.sin(b['yaw'])])
                                for s in (-1, 1)]
                        predicted = truth[i, :2]+R@np.array(ob['grip_base_m'])
                        # Nearest end is evaluation-only optimistic matching; does not prove assigned-end correctness.
                        best = min(np.linalg.norm(predicted-e) for e in ends)
                        distance = min(np.linalg.norm(truth[i, :2]-e) for e in ends)
                        db = 'near_lt_0.3m' if distance < .3 else 'mid_0.3_0.6m' if distance < .6 else 'far_ge_0.6m'
                        for group in (cohort+'/'+bucket, cohort+'/'+db):
                            errors[group]['nearest_end_position_m'].append(float(best))
                            if ob.get('axis_heading_rad') is not None:
                                axis_error = abs(float(wrap(ob['axis_heading_rad']+yaw-b['yaw'])))
                                errors[group]['axis_undirected_deg'].append(math.degrees(min(axis_error, math.pi-axis_error)))
                        ap = approach[i]
                        if ap.get('station_own_m') and ap.get('grip_own_m'):
                            # Station expressed relative to owned pose; absolute truth pose only used by evaluator.
                            rel = np.asarray(ap['station_own_m'][:2])-poses[i, :2]
                            ca, sa = math.cos(truth[i, 2]-poses[i, 2]), math.sin(truth[i, 2]-poses[i, 2])
                            station_world = truth[i, :2]+np.array([[ca,-sa],[sa,ca]])@rel
                            targets = [ends[0]-.203*np.array([math.cos(b['yaw']), math.sin(b['yaw'])]),
                                       ends[1]+.203*np.array([math.cos(b['yaw']), math.sin(b['yaw'])])]
                            errors[cohort+'/'+bucket]['nearest_station_target_m'].append(float(min(np.linalg.norm(station_world-e) for e in targets)))
            robot_rows.append(rr)
        row = {'run': name, 'cohort': cohort, 'version': name.rsplit('-', 1)[1],
               'source_sha': members.get(name+'/SOURCE_SHA', b'').decode().strip(),
               'raw': 'oracle:/home/ubuntu/ugrp-archive/runs/native-'+name,
               'exit': members.get(name+'/EXIT', b'').decode().strip(), 'result': result,
               'robots': robot_rows}
        rows.append(row); aggregate[cohort].append(row)
    grouped = {}
    for group, rs in aggregate.items():
        gs = {'runs_N': len(rs), 'by_robot': {}, 'joint_held_runs': {'n': 0, 'N': 0}}
        for rid in ('r1', 'r2'):
            rr = [next(x for x in r['robots'] if x['robot'] == rid) for r in rs]
            good = [x for x in rr if x['stages'] is not None]
            gs['by_robot'][rid] = {'requested_N': len(rr), 'read_N': len(good), 'stages': {},
                                  'failures': dict(Counter(x['first_unreached_stage'] or 'joint_held' for x in good))}
            for stage in (good[0]['stages'] if good else []):
                xs = [x['stages'][stage] for x in good if x['stages'][stage] is not None]
                gs['by_robot'][rid]['stages'][stage] = {'n': sum(xs), 'N': len(xs), 'unknown': len(rr)-len(xs)}
            if rid == 'r1':
                xs = [x['stages']['joint_held'] for x in good if x['stages']['joint_held'] is not None]
                gs['joint_held_runs'] = {'n': sum(xs), 'N': len(xs), 'unknown': len(rr)-len(xs)}
        grouped[group] = gs
    value = {'status': 'saved_stage_audit', 'groups': grouped, 'runs': rows,
             'errors': {k: {m: stats(v) for m,v in d.items()} for k,d in errors.items()},
             'definitions': {'seen': 'current segment detector visible/body_visible; inherited observations excluded',
                             'station': 'controller estimated distance <=8cm, not ground-truth arrival',
                             'align': 'fine visual_servo; global align phase includes search and is not this stage',
                             'ready': 's3_coarse_fine ready event', 'close': 'issued servo1 <=1600; actual aperture unmeasured',
                             'held': 'archived eval_only stage-held grasp_lift_labels, any sample; not 1s persistence',
                             'errors': 'posthoc pose residual; base-relative RGB endpoint evaluated with same-time GT pose; nearest end/axis optimistic matching',
                             'station_target': 'base-relative controller station vs nearest GT station, 0.203m v3 radius; not final physical station error'},
             'limitations': ['stage1 gate host failures/missing local ownmap remain unknown',
                             'historical r69/r76/r80 and prior 40-run pose figure not independently remeasured here',
                             'frame counts are correlated, not independent success denominators',
                             'stage trajectories can enter fine alignment without a new detection in this segment'],
             'inputs': inputs}
    a.output.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps(grouped, ensure_ascii=False))


if __name__ == '__main__': main()
