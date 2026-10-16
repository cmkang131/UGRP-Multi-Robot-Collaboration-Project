"""Same own recording: LK-only vs default-off own-map RBPF, gcp5 CPU only.

Predictions, scans and maps are saved/hash-sealed before evaluation files open.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(1,str(ROOT/'scripts'))


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def predicted(grid):
    return dict(frame='r1/start',resolution_m=grid.resolution_m,
        cells=[[int(x),int(y),'occupied' if value>0 else 'free'] for (x,y),value in sorted(grid.cells.items()) if value!=0],
        wall=grid.occupied_points().tolist(),obstacle=[],door=[],destination=[])


def replay(root,vision,calibration,output):
    import numpy as np
    import cv2
    import harness,sim
    harness.__path__.append(str(vision/'harness'));sim.__path__.append(str(vision/'sim'))
    from harness.mapbuild_rbpf import virtual_scan,MapbuildRBPF,OPTION
    from harness.e2e_rgb_vo import ground_pair,compose,PARAMS
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from harness.self_odom_grid import OdomGrid,transform
    from mapbuild1_replay import read_frame
    from mapbuild5_motion import command_intervals
    cv2.setNumThreads(1)
    calibration_path=vision/'experiments/2026-10-16-reloc16/colour-calibration.json'
    if hashlib.sha256(calibration_path.read_bytes()).hexdigest()!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':
        raise ValueError('FROZEN_COLOUR_CALIBRATION_REQUIRED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',json.loads(calibration_path.read_text()),option=RELOC16_OPTION)
    own=json.loads((root/'own.json').read_text())
    if own['physics_backend']!='mjwarp':raise ValueError('MJWARP_RECORDING_REQUIRED')
    frames=own['frames'];commands=json.loads((root/'commands.json').read_text())
    intervals=command_intervals(frames,commands,json.loads(calibration.read_text()))
    output.mkdir(parents=True,exist_ok=False)
    before=None;old=None;servo_before=None;last_map=-float('inf');lk_pose=np.zeros(3)
    baseline=OdomGrid('r1',profiles={});rbpf=None;rows=[];scans=[];events=[]
    for frame in frames:
        servo={int(k):int(v) for k,v in frame['servo'].items()};rgb=read_frame(root,frame)
        if rbpf is None:rbpf=MapbuildRBPF(servo,option=OPTION)
        lk=dict(status='bootstrap')
        if before is not None:
            if frame['t']<=old['t']:raise ValueError('CAUSAL_FRAMES_REQUIRED')
            lk=(dict(status='unknown_stale') if frame['t']-old['t']>PARAMS['max_pair_gap_s'] else
                ground_pair(before,rgb,servo) if servo==servo_before else dict(status='unknown_servo_change'))
        command_delta,command_cov=intervals[frame['frame_id']]
        delta=np.asarray(lk['delta']) if lk['status']=='measured' else command_delta
        cov=np.asarray(lk['covariance']) if lk['status']=='measured' else command_cov
        lk_pose=compose(lk_pose,delta)
        scan=virtual_scan(rgb,servo,state)
        pose,event=rbpf.step(frame['t'],frame['frame_id'],delta,cov,scan)
        if scan['segments'] and frame['t']>=.25 and frame['t']-last_map>=rbpf.grid.options.keyframe_interval_s-1e-8:
            baseline.insert(transform([scan['camera']],lk_pose)[0],[transform(s,lk_pose) for s in scan['segments']]);last_map=frame['t']
        rows.append(dict(t=frame['t'],frame_id=frame['frame_id'],lk_pose=lk_pose.tolist(),rbpf_pose=pose,
            prior_pose=event['prior_pose'],lk=lk,motion_source='measured_LK' if lk['status']=='measured' else 'command_prediction',
            motion_delta=delta.tolist(),motion_covariance=cov.tolist(),command_delta=command_delta.tolist(),
            command_covariance=command_cov.tolist(),rbpf_covariance=rbpf.grid.odom.covariance.tolist()))
        scans.append(dict(t=frame['t'],frame_id=frame['frame_id'],**scan));events.append(event)
        before=rgb;old=frame;servo_before=servo
        if frame['frame_id']%10==0:print('replayed',frame['t'],event['reason'],flush=True)
    dump(output/'trajectory.json',rows);dump(output/'scans.json',scans);dump(output/'events.json',events)
    dump(output/'lk-predicted.json',predicted(baseline));dump(output/'rbpf-predicted.json',predicted(rbpf.grid))
    dump(output/'rbpf-state.json',rbpf.grid.export())
    inputs=[root/'own.json',root/'commands.json',calibration,calibration_path]
    dump(output/'prediction-seal.json',dict(inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        predictions={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.json')},
        input_audit=dict(truth_inputs=0,top_actor_reads=0,peer_pose_inputs=0,measured_joint_inputs=0),
        sensor_proposal='off; existing Grisetti Gaussian proposal retained; no extra mixture assumptions'))
    returned=sum(c['status']=='hit' for s in scans for c in s['columns'])
    staged=[('frames',len(rows)),('visible_scan',sum(bool(s['segments']) for s in scans)),
            ('inserted_keyframe',sum(bool(e.get('inserted')) for e in events))]
    previous=len(rows);funnel=[]
    for stage,n in staged:funnel.append(dict(stage=stage,cumulative_pass_n=n,rejected_n=previous-n));previous=n
    dump(output/'rejection_table.json',dict(raw=str(root),reproduction=sys.argv,stages=funnel,
        motion_reasons=dict(Counter(r['lk']['status'] for r in rows)),
        column_funnel=[dict(stage='input_columns',cumulative_pass_n=len(scans)*96,rejected_n=0),
                       dict(stage='returned_contacts',cumulative_pass_n=returned,rejected_n=len(scans)*96-returned)],
        column_reasons=dict(Counter(c['reason'] for s in scans for c in s['columns'])),
        reasons=dict(Counter(e['reason'] for e in events)),
        work=dict(particles=30,scans=len(scans),proposal_candidates=sum(p.get('candidates',0) for e in events for p in e.get('particle_events',[])),
                  colour_line_pair_checks=sum(s['work']['line_pair_checks'] for s in scans)),
        rejection_fields='scans.json and events.json: reason/blocked_object/minimum_gap_m/gap_status'))
    return rows,events


def evaluate(root,vision,output,rows,events):
    import numpy as np
    from mapbuild2_map_eval import raster
    from score_mapbuild1 import score
    labels=json.loads((root/'eval-only.json').read_text())
    truth={r['frame_id']:np.asarray(r['pose']) for r in labels['frames']}
    if set(truth)!={r['frame_id'] for r in rows}:raise ValueError('EXACT_LABEL_COVERAGE_REQUIRED')
    static_path=vision/'maps/zones_final_v3/zone_hardmaps1_h1_final_v3.json'
    static=json.loads(static_path.read_text());origin=labels['first_origin'][0]
    target=raster(static,origin);metrics={}
    for method in ('lk','rbpf'):
        p=np.array([r[method+'_pose'] for r in rows]);gt=np.array([truth[r['frame_id']] for r in rows])
        error=p-gt;error[:,2]=np.arctan2(np.sin(error[:,2]),np.cos(error[:,2]))
        pred=json.loads((output/(method+'-predicted.json')).read_text())
        metrics[method]=dict(ate_xy_rmse_m=float(np.sqrt(np.mean(np.sum(error[:,:2]**2,axis=1)))),
            ate_xy_p95_m=float(np.percentile(np.linalg.norm(error[:,:2],axis=1),95)),
            ate_yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(error[:,2]**2)))),
            final_xy_error_m=float(np.linalg.norm(error[-1,:2])),map=score(pred,target))
    updates=[]
    for e in events:
        if e.get('matching_attempted') and e['t']>=29:
            gt=truth[e['frame_id']]
            after=next(r for r in rows if r['frame_id']==e['frame_id'])['rbpf_pose']
            updates.append(dict(t=e['t'],reason=e['reason'],sensor_update=e.get('sensor_weight_update',False),
                before_xy_m=float(np.linalg.norm(np.asarray(e['prior_pose'])[:2]-gt[:2])),
                after_xy_m=float(np.linalg.norm(np.asarray(after)[:2]-gt[:2]))))
    path=np.array([truth[r['frame_id']] for r in rows])
    result=dict(status='EVALUATED_NOT_ADMITTED',termination='cap_end',methods=metrics,
        measured_path_m=float(np.linalg.norm(np.diff(path[:,:2],axis=0),axis=1).sum()),
        lateral_roundtrip=dict(outbound_sim=[19,29],return_sim=[29,39],
            actual_outbound_m=float(np.linalg.norm(path[290,:2]-path[190,:2])),
            actual_return_m=float(np.linalg.norm(path[390,:2]-path[290,:2])),
            return_to_lateral_start_m=float(np.linalg.norm(path[390,:2]-path[190,:2]))),
        return_scan_corrections=updates,input_audit=dict(truth_opened_after_prediction_seal=True),
        limits='single fixed stimulus/scene/host, unloaded FOLDED only; static raster excludes dynamic cargo; no task/arrival success')
    dump(output/'summary.json',result)
    # Separate full physical-obstacle check after sealing predictions. Reuse
    # the former mapbuild2 evaluator's cargo-box raster at reset and at end;
    # mj_forward derives geometry only (no CPU integration or actor feedback).
    import os,mujoco,scripts
    scripts.__path__.append(str(vision/'scripts'))
    from scripts import probe_scene_tex2 as tools
    from scripts.generate_scene_textures import MAPS
    os.chdir(vision)
    model,scene,*_=tools.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    states=np.load(root/'eval-state.npz')['qpos'];data=mujoco.MjData(model)
    roots={model.body(item['body_name']).id for item in scene.config['setup_only']['objects'].values()}
    roots.add(model.body('cargo_tex2_beam').id)
    extended={}
    for k,label in [(0,'reset'),(-1,'end')]:
        data.qpos[:]=states[k];mujoco.mj_forward(model,data);extra=[];excluded=[]
        for gid in range(model.ngeom):
            body=int(model.geom_bodyid[gid])
            while body and body not in roots:body=int(model.body_parentid[body])
            if body not in roots or not (model.geom_contype[gid] or model.geom_conaffinity[gid]):continue
            if model.geom_type[gid]!=mujoco.mjtGeom.mjGEOM_BOX:
                excluded.append(model.geom(gid).name);continue
            rotation=data.geom_xmat[gid].reshape(3,3)
            extra.append(dict(id='eval_'+model.geom(gid).name,kind='cargo',center_m=data.geom_xpos[gid,:2].tolist(),
                half_extents_m=model.geom_size[gid,:2].tolist(),yaw_rad=float(np.arctan2(rotation[1,0],rotation[0,0]))))
        physical={**static,'obstacles':static['obstacles']+extra}
        extended[label]=dict(rectangles=extra,excluded_non_box_geoms=excluded,
            methods={method:score(json.loads((output/(method+'-predicted.json')).read_text()),raster(physical,origin))
                     for method in ('lk','rbpf')})
    dump(output/'cargo-map-scores.json',dict(evaluation_only=True,cpu_physics_steps=0,
        scope='saved MJWarp reset/end collision boxes; endpoint snapshots, not swept dynamic occupancy',snapshots=extended))
    # Verify re-observed wall identity from evaluation-only nearest wall boxes.
    from harness.e2e_rgb_vo import compose
    from harness.self_odom_grid import transform
    walls=[v for v in static['obstacles'] if v.get('kind')=='wall' or v['id'].startswith('wall_')]
    identities=[]
    for scan in json.loads((output/'scans.json').read_text()):
        xy=np.asarray([s[0] for s in scan['segments']]).reshape(-1,2)
        if not len(xy):continue
        world=transform(xy,compose(origin,truth[scan['frame_id']]))
        distances=[]
        for wall in walls:
            angle=wall.get('yaw_rad',0);c,s=np.cos(angle),np.sin(angle)
            local=(world-wall['center_m'])@np.array([[c,-s],[s,c]])
            distances.append(np.linalg.norm(np.maximum(abs(local)-wall['half_extents_m'],0),axis=1))
        distance=np.asarray(distances);ids=np.argmin(distance,axis=0)
        identities.append(dict(t=scan['t'],nearest_wall_counts=dict(Counter(walls[i]['id'] for i in ids)),
             nearest_residual_p50_m=float(np.median(distance.min(0))),nearest_residual_max_m=float(distance.min(0).max())))
    outbound=Counter();returning=Counter()
    for event in identities:
        target_counts=outbound if 19<=event['t']<29 else returning if 29<=event['t']<=39 else None
        if target_counts is not None:target_counts.update(event['nearest_wall_counts'])
    dump(output/'wall-reobservation.json',dict(evaluation_only=True,frames=identities,
         outbound_wall_counts=dict(outbound),return_wall_counts=dict(returning),
         common_nearest_walls=sorted(outbound.keys() & returning.keys()),
         scope='nearest geometry labels with residuals, no truth acceptance gate or control use'))
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','vision','calibration','output','queue'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mapbuild-rbpf-v1',action='store_true');a=p.parse_args()
    if not a.mapbuild_rbpf_v1 or platform.system()!='Linux' or not platform.node().startswith('ugrp-act-l4-gcp5'):
        p.error('explicit gcp5 offline replay only')
    receipt=json.loads((ROOT/'SOURCE_FILES.json').read_text())
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in receipt.items()):
        raise ValueError('SOURCE_BYTES_CHANGED')
    queue=json.loads(a.queue.read_text());table=Path(queue['rejection_table'])
    if not table.is_absolute() or not table.is_file():raise ValueError('EXISTING_ABSOLUTE_FUNNEL_REQUIRED')
    if queue.get('toggle')!='mapbuild_rbpf_v1' or queue.get('enabled') is not True:
        raise ValueError('EXPLICIT_RBPF_QUEUE_REQUIRED')
    if (ROOT/'SOURCE_SHA').read_text().strip()!=queue['source_sha']:
        raise ValueError('PINNED_SOURCE_REQUIRED')
    if hashlib.sha256(a.calibration.read_bytes()).hexdigest()!=queue['calibration_sha256']:
        raise ValueError('PINNED_PRIOR_DISTRIBUTION_REQUIRED')
    rows,events=replay(a.input,a.vision,a.calibration,a.output)
    evaluate(a.input,a.vision,a.output,rows,events)
