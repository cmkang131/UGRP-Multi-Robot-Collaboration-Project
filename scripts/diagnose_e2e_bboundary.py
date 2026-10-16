"""Read-only saved-input diagnosis; never imports a backend or opens a VM.

Evaluator trajectories are used ONLY by pose_diagnosis, after control-policy
replay. Compressed inputs are decoded in memory; originals are not rewritten.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.e2e_boundary_views import request, OPTION
from harness.e2e_rgb_gate import boundary
from harness.self_odom_grid import transform


def read(path, manifests):
    data = path.read_bytes()
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else data
    manifests[str(path)] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                               decoded_sha256=hashlib.sha256(raw).hexdigest())
    return raw


def find(raw, name):
    plain = raw/name
    return plain if plain.exists() else raw/(name+'.zst')


def load(raw, name, manifests, lines=False):
    data = read(find(raw, name), manifests)
    return [json.loads(l) for l in data.splitlines()] if lines else json.loads(data)


def diameter(points):
    points = np.unique(np.asarray(points, float).reshape(-1, 2), axis=0)
    return max((float(np.linalg.norm(points-p, axis=1).max()) for p in points), default=None)


def pose_diagnosis(raw, rid, rows, manifests):
    """Evaluation-only: align capture time to its archived trajectory clock."""
    trajectory_path = find(raw, f'eval_only/{rid}/trajectory.jsonl')
    if not trajectory_path.exists(): return dict(status='missing_evaluator_trajectory')
    tr = load(raw, f'eval_only/{rid}/trajectory.jsonl', manifests, lines=True)
    frames = load(raw, f'robots/{rid}/frames.jsonl', manifests, lines=True)
    times = np.array([v['t'] for v in tr]); captures = {v['frame_id']:v for v in frames}
    start = tr[0]; xy0 = start['robot_xyz_m'][:2]; yaw0 = start['robot_yaw_rad']
    c,s = math.cos(yaw0), math.sin(yaw0); rotation = np.array([[c,s],[-s,c]])
    errors, heading, displacement, corrected, centers = [], [], [], [], []
    time_residuals = []
    for row in rows:
        cap = captures.get(row['frame_id'])
        if cap is None: continue
        index = int(np.searchsorted(times, cap['sim_time']))
        index = min(range(max(0,index-1), min(len(tr),index+1)), key=lambda i:abs(times[i]-cap['sim_time']))
        time_residuals.append(abs(times[index]-cap['sim_time']))
        gtxy = rotation@(np.asarray(tr[index]['robot_xyz_m'][:2])-xy0)
        gtyaw = tr[index]['robot_yaw_rad']-yaw0
        pose = np.asarray(row['pose_own_m'], float)
        errors.append(float(np.linalg.norm(pose[:2]-gtxy)))
        heading.append(abs(math.atan2(math.sin(pose[2]-gtyaw),math.cos(pose[2]-gtyaw)))*180/math.pi)
        candidate = row.get('remembered_B')
        if not candidate: continue
        center = np.asarray(candidate['center_m'])
        # A what-if rigid re-projection, not a corrected controller input.
        cp,sp = math.cos(pose[2]),math.sin(pose[2])
        body = np.array([[cp,sp],[-sp,cp]])@(center-pose[:2])
        inferred = transform([body], [*gtxy,gtyaw])[0]
        centers.append(center); corrected.append(inferred)
        displacement.append(float(np.linalg.norm(inferred-center)))
    return dict(scope='evaluation_only; candidate memory snapshots include stale hypotheses, not independent detections',
        aligned_frames=len(errors), max_capture_time_residual_s=max(time_residuals,default=None),
        max_position_error_m=max(errors,default=None), max_heading_error_deg=max(heading,default=None),
        candidate_logged_diameter_m=diameter(centers),
        candidate_rigid_reprojection_diameter_m=diameter(corrected),
        max_candidate_rigid_reprojection_shift_m=max(displacement,default=None))


def diagnose(outputs, experiment_dir):
    manifests, runs, source_records = {}, [], []
    for record in sorted((ROOT/'experiments').glob('2026-10-11-e2e[0-9]*/*summary.json')):
        if not any(f'e2e{n}-' in str(record) for n in (9,10,11,12)): continue
        d = json.loads(read(record, manifests)); source_records.append(dict(path=str(record), status=d['status']))
        for run in d['runs']:
            name = run.get('id', run.get('run'))
            raw = outputs/'azure-runs'/name/'raw'
            result = dict(id=name, status=run.get('status'), source_sha=run.get('source_sha',d.get('source_sha')),
                          archived_raw=run.get('arm_raw',run.get('raw')), robots={})
            progress = raw/'e2e-progress.json'
            if progress.exists():
                p = json.loads(read(progress, manifests))
                result['boundary_remembered'] = p['own_B_boundary_remembered']
                result['own_route_generated'] = p['own_route_generated']
            for rid in ('r1','r2','r3'):
                if not find(raw,f'robots/{rid}/ownmap.jsonl').exists(): continue
                rows = load(raw,f'robots/{rid}/ownmap.jsonl',manifests,lines=True)
                if not rows: continue
                candidates = [r['remembered_B'] for r in rows if r.get('remembered_B')]
                ev = [e for r in rows for e in (r.get('exploration') or {}).get('events',[])]
                counts = Counter(e['reason'] for e in ev)
                ends = [r['t'] for r in rows if r.get('navigation_status') == 'exploration_finished']
                # Identical saved memories feed both options. No proposals executed.
                on = sum(request(r.get('remembered_B'),result.get('boundary_remembered',False),option=OPTION) for r in rows)
                off = sum(request(r.get('remembered_B'),result.get('boundary_remembered',False)) for r in rows)
                item = dict(frames=len(rows), candidate_frames=len(candidates),
                    max_recorded_candidate_observations=max((v['observation']['observations'] for v in candidates),default=None),
                    candidate_observation_scope='entity stores first confirmation metadata; not tracking maximum',
                    candidate_centers_diameter_m=diameter([v['center_m'] for v in candidates]),
                    max_recorded_candidate_bounds_area_m2=max((float(np.prod(np.diff(v['observation']['bounds_m'],axis=0))) for v in candidates),default=None),
                    first_exploration_finished_s=min((e['t'] for e in ev if e['reason']=='exploration_finished_no_frontier'),default=min(ends,default=None)),
                    first_finished_trace_s=min(ends,default=None), frontier_events=dict(counts),
                    frontier_lifecycle=[e for e in ev if e['reason'] in ('frontier_selected','frontier_cycle_visited',
                        'ABORTED_goal_blacklisted','frontier_unreachable_blacklisted','exploration_finished_no_frontier')],
                    fixed_memory_replay=dict(off_request_frames=off,on_request_frames=on, path_admission='unmeasured: original costmap absent',
                        gate_changes=0, proposed_actions_executed=0))
                final = find(raw,f'{rid}-ownmap-final.json')
                if final.exists():
                    snap = json.loads(read(final,manifests)); nodes=snap['graph']['nodes']
                    sigmas=[math.sqrt(float(np.linalg.eigvalsh(np.asarray(n['covariance'])[:2,:2]).max())) for n in nodes]
                    item['keyframe_sigma_xy_m'] = dict(min=min(sigmas,default=None),max=max(sigmas,default=None),N=len(sigmas),
                        scope='saved keyframes only, already inflated; not all received frames')
                item['pose_diagnosis'] = pose_diagnosis(raw,rid,rows,manifests)
                result['robots'][rid]=item
            runs.append(result)
    # The only locally retrieved JPEG subset: no download, rendering or decoding a video.
    selected_root=outputs/'e2e11-stall-odometry/selected-frames'
    image_rows=[]
    for run_path in sorted(selected_root.iterdir()):
        raw=outputs/'azure-runs'/run_path.name/'raw'
        for rid in ('r1','r2'):
            frames=load(raw,f'robots/{rid}/frames.jsonl',manifests,lines=True)
            poses={r['frame_id']:r for r in load(raw,f'robots/{rid}/ownmap.jsonl',manifests,lines=True)}
            for f in frames:
                p=run_path/'raw'/f['path']
                if not p.exists(): continue
                data=read(p,manifests)
                if hashlib.sha256(data).hexdigest()!=f['sha256']: raise ValueError('SAVED_RGB_HASH_MISMATCH')
                rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
                servo={int(k):v for k,v in f['commanded_servo'].items()}; diag={}
                b=boundary(rgb,servo,poses[f['frame_id']]['pose_own_m'],diagnostics=diag)
                baseline=boundary(rgb,servo,poses[f['frame_id']]['pose_own_m'])
                if baseline!=b: raise ValueError('DIAGNOSTICS_CHANGED_GATE')
                image_rows.append(dict(run=run_path.name,robot=rid,frame_id=f['frame_id'],sha256=f['sha256'],
                    t=poses[f['frame_id']]['t'],accepted=b is not None,**diag))
    contours=[c for r in image_rows for c in r['contours']]
    metrics={k:max((r[k] for r in contours if r.get(k) is not None),default=None) for k in (
        'area_px2','vertices','border_margin_px','white_islands','valid_floor_corners','projected_area_m2')}
    metrics['low_saturation_value_max']=max((c['low_saturation_value_max'] for c in contours if c.get('low_saturation_value_max') is not None),default=None)
    r1_contours=[c for r in image_rows if r['robot']=='r1' for c in r['contours']]
    metrics['r1']=dict(contour_area_px2_max=max((c['area_px2'] for c in r1_contours),default=None),
        area_pass_components=sum(c['area_px2']>=100 for c in r1_contours),
        white_test_reached_components=sum('white_islands' in c for c in r1_contours),
        white_islands_max=max((c['white_islands'] for c in r1_contours if 'white_islands' in c),default=None),
        low_saturation_pixels_max=max((c.get('low_saturation_pixels',0) for c in r1_contours),default=None),
        low_saturation_value_max=max((c['low_saturation_value_max'] for c in r1_contours if c.get('low_saturation_value_max') is not None),default=None),
        complete_boundary_frames=sum(r['accepted'] for r in image_rows if r['robot']=='r1'))
    metrics.update(blue_pixels=max((r['blue_pixels'] for r in image_rows),default=None),
        complete_boundary_frames=sum(r['accepted'] for r in image_rows),
        contour_rejections=dict(Counter(c['reason'] for c in contours)),
        r1_frames=sum(r['robot']=='r1' for r in image_rows), frames=len(image_rows),
        scope='selected JPEG subset of two round10 runs; not full-cohort maxima',
        diagnostics_equal_baseline_frames=len(image_rows))
    summary=dict(schema='ugrp.e2e-bboundary.offline.v1',status='OFFLINE_DIAGNOSED_PARTIAL_TELEMETRY',
        source_base='31f4f41ac7594ebc82c8cfc089c64ef50f65c57c',research_result=False,
        execution=dict(physics=0,render=0,model_calls=0,VM_connections=0,simulations=0),
        thresholds=dict(remember_B=dict(contour_area_px2_min=100,vertices=4,convex=True,border_margin_px_min=3,
            self_mask_overlap_px_max=0,white_islands_exact=3,white_island_area_px_min=9,valid_floor_corners=4,
            accepted_components_exact=1,entity_boundary_center_distance_m_max=.20,
            required_frames=1,covariance_gate=False,metric_area_gate=False),
          replan_verify=dict(fresh_age_s_max=.25,fresh_frames=3,max_frame_gap_s=.5,min_span_s=.2,
            mutual_matches_min=12,RANSAC_inliers_min=12,inlier_fraction_min=.6,image_coverage_min=.04),
          arrival=dict(distance_plus_3sigma_m_max=.20,frame_rule='same as replan; full current boundary required'),
          color_candidate=dict(min_pixels=64,min_observed_area_m2=.005,views_min=3,min_span_s=2.,translation_m_min=.05,
            temporal_center_residual_m_max=.10,temporal_overlap_min=.35)),
        selected_RGB_metrics=metrics,source_records=source_records,runs=runs,
        navigation_parameters=dict(resolution_m=.05,inflation_radius_m=.5,inscribed_radius_m=.12,
            footprint_half_m=[.14,.12],unknown_cost=255,blocked_goal_costs=[253,254],
            navfn_allow_unknown=True,candidate_view_requires_known_filled_footprint=True,
            blacklist_and_visited_axis_tolerance_m=.25,progress_translation_m=.5,progress_timeout_s=10.,
            frontier_min_extent_m=.1,frontier_kernel='unmodified explore_lite over raw grid; NavFn over inflated grid'),
        limitations=['Full RGB, boundary counters and original costmaps were not retrieved. Pixel maxima are subset-only.',
            'No per-frame full-boundary/ORB history was persisted; no boundary anchor in r1 does not identify the failing pixel test.',
            'Raw frontier clusters/min-size rejections/inflated connectivity/blacklist contents at exhaustion cannot be recovered exactly.',
            'Frozen-memory scheduling replay changes requests only; no executed approach, boundary gain, path or E2E success claimed.'])
    raw_out=outputs/'e2e-bboundary-20261012';raw_out.mkdir(parents=True,exist_ok=True)
    def compressed(name,value):
        data=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
        packed=subprocess.check_output(['zstd','-q','-c','-3'],input=data)
        p=raw_out/(name+'.zst');p.write_bytes(packed)
        if subprocess.check_output(['zstd','-dc',str(p)])!=data:raise ValueError('DERIVED_RECORD_HASH_MISMATCH')
        return dict(path=str(p),bytes=len(packed),sha256=hashlib.sha256(packed).hexdigest(),
                    decoded_sha256=hashlib.sha256(data).hexdigest())
    summary['detailed_diagnosis']=compressed('detailed-diagnosis.json',summary)
    summary['selected_RGB_replay']=compressed('selected-rgb-replay.json',image_rows)
    summary['input_manifest']=compressed('inputs.sha256.json',manifests)
    # Short JSON accounts for every attempt; detailed robot/event records stay local.
    for run in summary['runs']:
        for rid,item in run['robots'].items():
            if run['id']!='e2e12-a-s61001' or rid!='r1':item.pop('frontier_lifecycle',None)
            item.pop('candidate_observation_scope',None)
            if 'pose_diagnosis' in item:item['pose_diagnosis'].pop('scope',None)
            if 'keyframe_sigma_xy_m' in item:item['keyframe_sigma_xy_m'].pop('scope',None)
            item['fixed_memory_replay'].pop('path_admission',None)
            if rid!='r1':
                run['robots'][rid]={k:item[k] for k in ('frames','candidate_frames','first_exploration_finished_s')}
    experiment_dir.mkdir(parents=True,exist_ok=True)
    (experiment_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':'))+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outputs',type=Path,required=True)
    p.add_argument('--record',type=Path,required=True)
    a=p.parse_args();d=diagnose(a.outputs,a.record)
    print(json.dumps(dict(runs=len(d['runs']),RGB=d['selected_RGB_metrics']),ensure_ascii=False))
