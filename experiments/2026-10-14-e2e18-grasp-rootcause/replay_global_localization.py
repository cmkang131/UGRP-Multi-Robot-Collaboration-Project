"""Saved-detection and native 320x240 review-image replay. No physics/render.

Ground truth is joined AFTER matcher.fit, for evaluation only. No plan spawn,
destination, or truth is passed to the global matcher.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from types import SimpleNamespace

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness import zone_pair_highpose_contract as contract
from sim.global_landmark_localization import GlobalLandmarkMatcher, PARAMS
from sim.lookaround_localization import LookaroundLocalizer, Camera
from sim.active_lookaround import OwnPose
from sim.visible_belief import odometry


def stats(xs):
    return dict(n=len(xs),min=min(xs),median=statistics.median(xs),max=max(xs)) if xs else dict(n=0)


def read(path):
    blob=path.read_bytes()
    if path.suffix=='.zst':blob=subprocess.check_output(['zstd','-dc'],input=blob)
    return blob.decode()


def find(raw,name):
    p=raw/name
    return p if p.exists() else raw/(name+'.zst')


def evaluate(dec,truth):
    p=dec.get('proposed')
    return dict(position_m=None if p is None else math.dist(p[:2],truth[:2]),
                yaw_deg=None if p is None else abs(math.degrees((p[2]-truth[2]+math.pi)%(2*math.pi)-math.pi)))


def summarize(rows):
    accepted=[r for r in rows if r['decision']['accepted']]
    return dict(n=len(rows),accepted=len(accepted),reasons=dict(Counter(r['decision']['reason'] for r in rows)),
                accepted_segment_rms_m=stats([r['decision']['inlier_segment_rms_m'] for r in accepted]),
                accepted_inlier_lines=stats([r['decision']['inliers'] for r in accepted]),
                hypothesis_count=stats([r['decision']['hypotheses'] for r in rows if 'hypotheses' in r['decision']]),
                accepted_position_m=stats([r['evaluation']['position_m'] for r in accepted]),
                accepted_yaw_deg=stats([r['evaluation']['yaw_deg'] for r in accepted]),
                accepted_over_15cm=sum(r['evaluation']['position_m']>.15 for r in accepted),
                rejected=[dict(case=r['case'],robot=r['robot'],reason=r['decision']['reason']) for r in rows if not r['decision']['accepted']])


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,default=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs'))
    p.add_argument('--out',type=Path,default=Path(__file__).with_name('release-global-replay.json'));a=p.parse_args()
    static=contract.resolve('zone_wide_two_doors_final_v3')[0];matcher=GlobalLandmarkMatcher(static)
    evidence={};rows=[];baseline=Counter();old={}
    def verified(path):
        rel=path.relative_to(a.raw_root);manifest=a.raw_root/rel.parts[0]/'SHA256SUMS'
        entries={line.split(maxsplit=1)[1]:line.split(maxsplit=1)[0] for line in manifest.read_text().splitlines()}
        sha=hashlib.sha256(path.read_bytes()).hexdigest();remote='/home/ugrp/ugrp-sim/runs/'+str(rel)
        if entries.get(remote)!=sha:raise ValueError('HASH_MISMATCH '+str(path))
        evidence[str(rel)]=sha;return None if path.suffix=='.jpg' else read(path)
    # Fixed original denominator: last decision for both robots in all 40 runs.
    for i in range(40):
        name=f'release-command-gate-{i:02d}-cdace35e';raw=a.raw_root/name/'raw'
        result=json.loads(verified(find(raw,'result.json')));old[name]=result
        for rid,item in result['lookaround_result'].items():
            saved=item['localizer'];baseline[saved['decision']['reason']]+=1
            loc=LookaroundLocalizer.__new__(LookaroundLocalizer)
            loc.global_matcher=matcher;loc.views=saved['views'];loc.command_own=OwnPose(saved['final_estimate'])
            loc.own=OwnPose(saved['final_estimate']);loc.map_pose_known=False
            dec=loc.finalize()
            # Evaluation starts here; never sent to finalize/matcher.
            error=evaluate(dec,item['evaluation']['after']['truth'])
            rows.append(dict(case=name,robot=rid,decision=dec,evaluation=error))
    diagnostics=[]
    for i in range(7):
        name=f'release-center-diagnostic-{i:02d}-e14fa729';raw=a.raw_root/name/'raw'
        result=json.loads(verified(find(raw,'result.json')))
        for rid,item in result['lookaround_result'].items():
            saved=item['localizer'];dec=matcher.fit(saved['views'],saved['final_estimate'])
            diagnostics.append(dict(case=name,robot=rid,decision=dec,evaluation=evaluate(dec,item['evaluation']['after']['truth'])))
    # Separate review-RGB experiment. Keep 320x240 pixels; scale K, not images.
    # Floor-line pixel thresholds are unchanged, hence more conservative in
    # angular support than native 640x480. This is NOT exact live-RGB replay.
    from harness import vision_loc_protocol as vp
    from harness.zone_solo_cyan_landmarks import MapFeatures,floor_features,ground
    mp=vp.load_vis3()[0].mp;camera=Camera();mapped=MapFeatures(static)
    K=mp.K.copy();K[:2]*=.5;Kinv=np.linalg.inv(K)
    remap=cv2.fisheye.initUndistortRectifyMap(K,np.asarray(mp.CAMERA_FISHEYE_D,float).reshape(4,1),np.eye(3),K,(320,240),cv2.CV_32FC1)
    yy,xx=np.indices((240,320));rgbrows=[];inventory=Counter();frame_records=[]
    for run in sorted(a.raw_root.glob('release-command-*-cdace35e')):
        if not list((run/'raw/eval-own').glob('*/*.jpg')):continue
        result=old.get(run.name) or json.loads(verified(find(run/'raw','result.json')))
        evals=[json.loads(s) for s in verified(find(run/'raw','eval-only.jsonl')).splitlines()]
        evals=[e for e in evals if 'robots' in e]
        for rid in ('r1','r2'):
            labels=[json.loads(s) for s in verified(find(run/'raw',f'teacher-{rid}.jsonl')).splitlines()]
            pose=OwnPose(result['handoff_estimates'][rid]);commands=[];last_change=-math.inf;last=None;settled=[]
            for row in labels:
                if row['pwm']!=last:last_change=row['t'];last=row['pwm']
                settled.append(row['t']-last_change>=.8-1e-6);commands.append(pose.x.copy())
                seconds=max(max(0.,min(.1,u-row['t'])) if level else 0. for level,u in zip(row['wheels'],row['wheel_until']))
                pose.propagate(*odometry(row['wheels'],seconds))
            views=[];target=None;at=None
            for path in sorted((run/'raw/eval-own'/rid).glob('*.jpg')):
                inventory['all_review_own_frames']+=1;verified(path)
                if '-release-' not in path.name:inventory['prefix_excluded']+=1;continue
                idx=int(path.name.split('-')[0]);row=labels[idx]
                servo={int(k):v for k,v in row['pwm'].items()};cam,reason=camera.pose(servo)
                if cam is None:inventory['camera_unqualified']+=1;continue
                if not settled[idx]:inventory['unsettled_commands']+=1;continue
                rgb=cv2.imread(str(path));assert rgb.shape==(240,320,3)
                und=cv2.remap(rgb,*remap,cv2.INTER_LINEAR);cm=SimpleNamespace(origin=cam[0],_rot=cam[1])
                _,valid,_=ground(cm,np.c_[xx.ravel(),yy.ravel()],Kinv)
                features=floor_features(und,cm,Kinv,mapped,valid.reshape(240,320))
                inventory['processed']+=1;inventory['floor_lines']+=len(features)
                view=dict(t=row['t'],prior=commands[idx].tolist(),command_pose=commands[idx].tolist(),features=features,wall_points_body=[])
                views.append(view);at=commands[idx]
                target=min(evals,key=lambda e:abs(e['t']-row['t']))
                frame_records.append(dict(path=str(path.relative_to(a.raw_root)),time=row['t'],features=len(features),size=[320,240]))
            if not views:
                rgbrows.append(dict(case=run.name,robot=rid,decision=dict(accepted=False,reason='no_qualified_review_frame'),evaluation=dict(position_m=None,yaw_deg=None)))
                continue
            dec=matcher.fit(views,at)
            truth=target['robots'][rid]['pose']
            rgbrows.append(dict(case=run.name,robot=rid,decision=dec,evaluation=evaluate(dec,truth)))
    detail=dict(detections=rows,e14_diagnostics=diagnostics,review_rgb=rgbrows,review_frames=frame_records,files=evidence)
    detailpath=a.out.with_name(a.out.stem+'-detail.json.zst')
    detailpath.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=json.dumps(detail,ensure_ascii=False).encode()))
    summary=dict(scope='offline saved detections + separate native 320x240 review floor-line replay; no simulation/render/model',
                 source_parent_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),parameters=PARAMS,
                 baseline=dict(n=80,accepted=0,reasons=dict(baseline),map_error_m=None),
                 saved_detections=summarize(rows),e14_saved_detections=summarize(diagnostics),
                 review_rgb=summarize(rgbrows),review_inventory=dict(inventory),
                 comparison='Baseline map pose is undefined; no numeric before/after map-error reduction claim. Command-frame 9.65 mm error is a different quantity.',
                 input_resolution='Saved detections came from 640x480; review RGB is 320x240, different times, floor-only with scaled calibration and unchanged pixel thresholds.',
                 evidence=dict(path=detailpath.name,sha256=hashlib.sha256(detailpath.read_bytes()).hexdigest(),verified_files=len(evidence)),
                 source_hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('sim/global_landmark_localization.py','sim/lookaround_localization.py','sim/release_global_observation.py','scripts/run_grasp_act_release.py')})
    a.out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
