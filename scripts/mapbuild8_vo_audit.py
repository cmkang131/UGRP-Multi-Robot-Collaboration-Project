"""gcp5 post-seal audit: signed yaw causes and wall features in floor VO.

Evaluation values are diagnostics only. Does not fit means, covariances, masks
or thresholds. Feature masks and colour calibration are the frozen originals.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(a.vision)]
    import harness,sim
    harness.__path__.append(str(a.vision/'harness'));sim.__path__.append(str(a.vision/'sim'))
    import numpy as np
    import cv2
    from harness.mapbuild_camera import adapters
    from harness.servo_camera_fk import CARRY_OPTION
    from harness.e2e_rgb_vo import between,PARAMS,wrap
    from harness.scene_colour_boundary import surface_masks
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    seal=read(a.prediction/'prediction-seal.json')
    for name,h in seal['prediction_sha256'].items():
        if sha(a.prediction/name)!=h:raise ValueError('PREDICTION_SEAL_CHANGED')
    a.output.mkdir(parents=True,exist_ok=False);cv2.setNumThreads(1)
    rows=read(a.prediction/'trajectory.json');frames=read(a.input/'own.json')['frames'];gt=read(a.input/'eval-only.json')['frames']
    groups=defaultdict(list)
    for k in range(1,len(rows)):
        r=rows[k];truth=between(gt[k-1]['pose'],gt[k]['pose']);turn=frames[k]['command_delta'][2]!=0
        category=('measured_turn' if turn else 'measured_other') if r['lk']['status']=='measured' else ('command_turn_' if turn else 'command_other_')+r['lk']['status']
        used=np.array(r['motion_delta']);command=np.array(frames[k]['command_delta'])
        groups[category].append(dict(t=r['t'],used_yaw_error_deg=float(np.degrees(wrap(used[2]-truth[2]))),
            nominal_yaw_error_deg=float(np.degrees(wrap(command[2]-truth[2]))),
            visual_yaw_error_deg=float(np.degrees(wrap(r['lk']['delta'][2]-truth[2]))) if r['lk']['status']=='measured' else None,
            xy_increment_error_m=float(np.linalg.norm(used[:2]-truth[:2]))))
    distributions=[]
    for name,rs in groups.items():
        measured=[r for r in rs if r['visual_yaw_error_deg'] is not None]
        distributions.append(dict(category=name,n=len(rs),signed_yaw_error_sum_deg=sum(r['used_yaw_error_deg'] for r in rs),
            absolute_yaw_error_sum_deg=sum(abs(r['used_yaw_error_deg']) for r in rs),nominal_signed_yaw_error_deg=sum(r['nominal_yaw_error_deg'] for r in rs),
            visual_signed_yaw_error_deg=sum(r['visual_yaw_error_deg'] for r in measured) if measured else None,
            xy_increment_error_sum_m=sum(r['xy_increment_error_m'] for r in rs),blocked_object='own_floor_projection_or_command_model',minimum_gap_m=None,gap_status='not_measured'))
    distributions.sort(key=lambda x:-abs(x['signed_yaw_error_sum_deg']))
    pair,_=adapters(CARRY_OPTION);image_mask=pair.__globals__['image_mask']
    cal_path=a.vision/'experiments/2026-10-16-reloc16/colour-calibration.json';cal=read(cal_path)
    if sha(cal_path)!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':raise ValueError('COLOUR_CHANGED')
    feature_rows=[];pictures=[]
    # Descriptive 1SIM-second sampling, inherited CSM report cadence.
    for k in range(0,len(rows),10):
        f=frames[k];servo={int(k):v for k,v in f['servo'].items()};im=cv2.imread(str(a.input/f['rgb']));rgb=cv2.cvtColor(im,cv2.COLOR_BGR2RGB)
        mask=image_mask(rgb,servo);masks,_=surface_masks(im,cal,expanded_wall_value=True)
        points=cv2.goodFeaturesToTrack(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),maxCorners=PARAMS['max_corners'],qualityLevel=PARAMS['quality'],
            minDistance=PARAMS['min_distance_px'],mask=mask,blockSize=7)
        xy=np.rint(points[:,0]).astype(int) if points is not None else np.empty((0,2),int)
        wall=masks['wall'][xy[:,1],xy[:,0]] if len(xy) else np.zeros(0,bool)
        row=dict(t=f['t'],frame_id=f['frame_id'],corners=len(xy),known_wall_corners=int(wall.sum()),wall_fraction=float(wall.mean()) if len(wall) else None,command_turn=f['command_delta'][2]!=0)
        feature_rows.append(row)
        for (x,y),iswall in zip(xy,wall):cv2.circle(im,(x,y),3,(0,0,255) if iswall else (0,255,0),1)
        cv2.putText(im,'SIM %.1f - red=known wall: %s/%s'%(f['t'],row['known_wall_corners'],row['corners']),(6,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),2)
        pictures.append((row['wall_fraction'] or 0.,f['t'],im))
    top=sorted(pictures,key=lambda x:(-x[0],x[1]))[:6]
    if len(top)==6:cv2.imwrite(str(a.output/'wall-feature-corners.jpg'),np.vstack([np.hstack([x[2] for x in top[k:k+2]]) for k in range(0,6,2)]))
    summary=dict(raw=str(a.input),prediction=str(a.prediction),yaw_distribution=distributions,feature_frames=feature_rows,
        selected_own_frames=[x[1] for x in top],evaluation_scope='yaw residual sums are signed additive increments; XY residual sums are NOT final SE2 contributions',
        truth_to_control=0,threshold_fitting=0,calibration_sha256=sha(cal_path),reproduction=sys.argv)
    dump(a.output/'summary.json',summary);dump(a.output/'intervals.json',groups)
    print(json.dumps(dict(yaw_distribution=distributions,feature_corners=sum(r['corners'] for r in feature_rows),known_wall_corners=sum(r['known_wall_corners'] for r in feature_rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','prediction','vision','output'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
