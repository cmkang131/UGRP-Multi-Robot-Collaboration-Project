"""Fixed posterior/command replay, never a counterfactual mission simulation."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np

from harness.ego_pose_continuity import (Options, Reporter, REP105, STATIONARY,
    CLUSTER, MAHALANOBIS, BOUND, dominant_cluster)
from harness.own_map_amcl_vendor.motion import moved
from harness.rbpf_rejection import motion_variance
from harness.self_map_csm import CSMOptions
from scripts.evaluate_egomap_covariance import lines, read

CANDIDATES = dict(off=Options(), rep105=Options(pose_continuity=REP105),
    stationary=Options(stationary_update=STATIONARY),
    cluster=Options(pose_reporting=CLUSTER),
    mahalanobis=Options(correction_gate=MAHALANOBIS),
    bounded=Options(correction_gate=MAHALANOBIS, correction_limit=BOUND),
    cluster_mahalanobis=Options(pose_reporting=CLUSTER, correction_gate=MAHALANOBIS))


def jump_metrics(poses, predicted=None):
    poses = np.asarray(poses)
    d = np.linalg.norm(np.diff(poses[:, :2], axis=0), axis=1)
    out = dict(transitions=len(d), counts={str(v):int((d>v).sum()) for v in (.05,.2,.5)},
        max_m=float(d.max()) if len(d) else 0.,
        quantiles={str(q):float(np.quantile(d,q)) for q in (.5,.95,.99)} if len(d) else {})
    if predicted is not None:
        excess = d-np.asarray(predicted)
        out['excess_over_command'] = {str(v):int((excess>v).sum()) for v in (.05,.2,.5)}
    return out


def evaluate(folder, samples):
    own, a = lines(folder/'own-controller.jsonl')
    covs, b = lines(folder/'frontend-covariances.jsonl')
    truth, c = lines(folder/'eval_only/trajectory.jsonl')
    raw, d = read(folder/'result.json'); result = json.loads(raw)
    by_t = {round(x['t'],6):x for x in samples}
    covs = {round(x['t'],6):np.asarray(x['covariance']) for x in covs}
    actual = {round(x['t'],6):x for x in truth}
    origin, angle = np.asarray(truth[0]['robot_xyz_m'][:2]), truth[0]['robot_yaw_rad']
    rotation = np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    reports, errors, controls = {}, {}, {}
    for name, options in CANDIDATES.items():
        reporter = Reporter(np.zeros(3), CSMOptions().floor(), options)
        poses, odoms, targets, stage_poses, stage_targets, events = [], [], [], [], [], []
        last_measurement_odom = None; decisions = Counter(); previous = None
        last_flags = {'B':False, 'return':False}
        for row in own:
            t = round(row['t'],6); s = by_t[t]; R = covs[t]
            delta = np.asarray(s['body_delta']); driver = np.asarray(s['command_odom'])
            reporter.predict(delta, np.diag(motion_variance(delta)))
            candidate = row['local_pose'] if options.pose_reporting == 'off' else s['cluster_pose']
            eligible = bool(s['measurement'] or s['route_delta'])
            if options.stationary_update != 'off' and last_measurement_odom is not None:
                eligible &= bool(moved(driver-last_measurement_odom))
            if eligible:
                decisions[reporter.measure(candidate, R)['reason']] += 1
                last_measurement_odom = driver.copy()
            if name in ('off', 'rep105'):
                pose = np.asarray(row['local_pose'])
            else:
                pose = reporter.pose.copy()
            target = rotation.T@(np.asarray(actual[t]['robot_xyz_m'][:2])-origin)
            poses.append(pose); targets.append(target); odoms.append(driver)
            if t >= result['start_sim_s']:
                stage_poses.append(pose); stage_targets.append(target)
            flags = {'B':bool(row.get('declared_goal')), 'return':bool(row.get('declared_return'))}
            for kind, flag in flags.items():
                if not flag or last_flags[kind]:
                    continue
                target_pose = (row.get('remembered_entities',{}).get('B',{}).get('center_m') if kind=='B'
                               else own[0]['local_pose'][:2])
                events.append(dict(t=t, kind=kind, original_declaration=True,
                    frozen_geometry_pass=None if target_pose is None else math.dist(pose[:2], target_pose)<=.20,
                    estimated_distance_m=None if target_pose is None else math.dist(pose[:2], target_pose),
                    gt_return_valid=math.dist(actual[t]['robot_xyz_m'][:2], origin)<=.20 if kind=='return' else None,
                    counterfactual_declaration='unavailable: route/map/RGB FSM were not rerun'))
            last_flags = flags; previous = row
        error = np.asarray(poses)[:, :2]-np.asarray(targets)
        stage_error = np.asarray(stage_poses)[:, :2]-np.asarray(stage_targets)
        control = odoms if options.pose_continuity != 'off' else poses
        predicted = [float(np.linalg.norm(by_t[round(r['t'],6)]['body_delta'][:2])) for r in own[1:]]
        reports[name] = dict(options=asdict(options), frames=len(poses),
            map_jumps=jump_metrics(poses,predicted), control_jumps=jump_metrics(control,predicted),
            map_xy_rmse_m=float(np.sqrt(np.mean(np.sum(error**2,axis=1)))),
            stage_xy_rmse_m=float(np.sqrt(np.mean(np.sum(stage_error**2,axis=1)))),
            final_error_m=float(np.linalg.norm(error[-1])), measurements=dict(decisions),
            declarations_at_recorded_times=events,
            command_odom_xy_rmse_m=float(np.sqrt(np.mean(np.sum((np.asarray(odoms)[:,:2]-targets)**2,axis=1)))))
        errors[name] = np.sum(error**2,axis=1).tolist()
        controls[name] = reports[name]['control_jumps']['counts']['0.2']
    diagnosis = []
    for prev, row in zip(own,own[1:]):
        distance = math.dist(prev['local_pose'][:2],row['local_pose'][:2])
        if distance <= .2:
            continue
        sample = by_t[round(row['t'],6)]
        lineage = sample['previous_lineage_current_pose']
        diagnosis.append(dict(t=row['t'], frame_id=row['frame_id'], jump_m=distance,
            previous_pose=prev['local_pose'], pose=row['local_pose'],
            predicted_translation_m=float(np.linalg.norm(sample['body_delta'][:2])),
            predicted_yaw_rad=sample['body_delta'][2],
            sigma_xy=row['sigma_xy'], status=row['status'],
            selected_previous=sample['selected_previous'], selected_now=sample['selected_before_resampling'],
            same_lineage_motion_m=None if lineage is None else math.dist(lineage[:2], prev['local_pose'][:2]),
            inter_particle_distance_m=None if lineage is None else math.dist(lineage[:2],row['local_pose'][:2]),
            reason=sample['reason'], sensor_weight_update=sample['sensor_weight_update'],
            resampled=sample['resampled'], yaw_prior=sample['yaw_prior'], route_delta=sample['route_delta']))
    return dict(run=folder.name, result=result, sources=[a,b,c,d], candidates=reports,
        largest_jumps=sorted(diagnosis,key=lambda r:r['jump_m'],reverse=True)[:5],
        jump_causes=dict(Counter(('particle_switch' if r['selected_previous']!=r['selected_now'] else 'same_particle')+
            '/'+str(r['reason']) for r in diagnosis))), errors, controls


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,required=True)
    p.add_argument('--samples',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); rows,receipt=lines(a.samples)
    by_run=defaultdict(list); sources=[]
    for row in rows:
        if row['kind']=='sources':sources.append(row)
        else:by_run[row['run']].append(row)
    reports=[]; errors=defaultdict(list); jumps=Counter()
    for name,samples in by_run.items():
        report,err,counts=evaluate(a.runs/name,samples);reports.append(report)
        for k,v in err.items():errors[k].extend(v)
        jumps.update(counts)
    totals={name:dict(frames=len(values),rmse_m=float(np.sqrt(np.mean(values))),
        jumps_gt20cm=jumps[name], worse_runs=[r['run'] for r in reports if
        r['candidates'][name]['map_xy_rmse_m']>r['candidates']['off']['map_xy_rmse_m']+1e-9]) for name,values in errors.items()}
    for name,r in totals.items():
        r['pooled_gate']=r['rmse_m']<=totals['off']['rmse_m']+1e-9 and r['jumps_gt20cm']<totals['off']['jumps_gt20cm']
        r['all_runs_gate']=r['pooled_gate'] and not r['worse_runs']
    result=dict(schema='ugrp.egojump.offline.v1',scope='fixed posterior/command replay; filter and motion-gate changes do not rerun PF, maps, RGB, or route FSM',
        evaluation_truth_control_input=False,source_receipt=receipt,ARM_sources=sources,
        runs=reports,totals=totals,
        limits=['B/return reassessment only at historical declarations; no new mission success prediction',
                'stationary comparator skips recorded posterior measurements; online also suppresses upstream PF updates',
                'REP105 removes control-frame jumps, map RMSE is evaluated after applying map-to-odom; odom drift separately reported'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(totals,indent=2))


if __name__=='__main__':main()
