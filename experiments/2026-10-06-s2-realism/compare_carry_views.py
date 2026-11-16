"""Saved RGB/commands/eval geometry only; never builds or steps a simulator."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from harness.zone_solo_cyan_contract_v106 import CALIBRATION
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_pair_highpose_contract import camera_record
from harness.zone_pair_highpose import HIGH
from harness.zone_solo_cyan_scene_change import lens_valid
from harness.zone_color_boxes import _mask, OWN_ZONE_CYAN_HSV
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D

PRIMARY=Path('/Users/changmin/projects/ugrp/outputs')
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def geometry(tr,rec):
    y=tr['robot_yaw_rad'];c,s=np.cos(y),np.sin(y)
    heading=np.array([[c,s,0],[-s,c,0],[0,0,1.]])
    center=heading@(np.array(tr['cyan_xyz_m'])-np.r_[tr['robot_xyz_m'][:2],0])
    rot=heading@np.array(tr['cyan_rotation']).reshape(3,3)
    origin,cam=np.array(rec['origin_m']),np.array(rec['rotation'])
    yy,xx=np.mgrid[:480,:640]
    norm=cv2.fisheye.undistortPoints(np.stack((xx,yy),-1).astype(float).reshape(-1,1,2),
        scaled_camera_matrix(640,480),np.array(CAMERA_FISHEYE_D)).reshape(-1,2)
    rays=np.c_[norm,np.ones(len(norm))]@cam.T@rot
    local=(origin-center)@rot;half=np.array(tr['box_half_m'])
    with np.errstate(divide='ignore'):
        a,b=(-half-local)/rays,(half-local)/rays
    hit=(np.minimum(a,b).max(1)<=np.maximum(a,b).min(1)) & (np.maximum(a,b).min(1)>=0)
    mask=hit.reshape(480,640)&lens_valid();ys,xs=np.nonzero(mask)
    return dict(block_floor_heading_m=center.tolist(),block_rotation_heading=rot.tolist(),
        camera_origin_m=origin.tolist(),optical_forward=cam[:,2].tolist(),
        optical_pitch_deg=float(np.degrees(np.arcsin(cam[2,2]))),
        unobstructed_ray_pixels=int(mask.sum()),bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None)


def audit(seed):
    p=next(PRIMARY.glob(f's2-realism-*-s{seed}-P1-2-pick'))
    r=read(p/'student_record.json');fs=rows(p/'robots/r3/frames.jsonl');tr=rows(p/'eval_only/trajectory.jsonl')
    start=next(e['t'] for e in r['events'] if e['event']=='state' and e['state']=='lift')
    carry=next(e['t'] for e in r['events'] if e['event']=='high_carry_pose')
    samples=[]
    for f in fs:
        if f['sim_time']<start:continue
        path=p/f['path'];assert sha(path)==f['sha256']
        mask=_mask(cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2HSV),OWN_ZONE_CYAN_HSV)&lens_valid()
        ys,xs=np.nonzero(mask)
        samples.append(dict(t=f['sim_time'],path=f['path'],sha256=f['sha256'],area_px=int(mask.sum()),
            commanded_servo=f['commanded_servo'],bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None))
    near=min(tr,key=lambda t:abs(t['t']-carry));f=min(fs,key=lambda f:abs(f['sim_time']-carry))
    cal=read(Path(CALIBRATION));variants={n:geometry(near,camera_record(c,'loaded',HIGH))
        for n,c in [('previous_camera',cal),('v3',camera_calibration(cal))]}
    high=[x for x in samples if all(x['commanded_servo'].get(str(k))==v for k,v in HIGH.items()) and x['t']>=carry-.5]
    areas=[x['area_px'] for x in high]
    return dict(seed=seed,raw=str(p),lift_t=start,carry_t=carry,
        carry_command=f['commanded_servo'],evaluation_only=near,calibrated_geometry=variants,
        carry_area=dict(n=len(areas),min=min(areas),median=float(np.median(areas)),max=max(areas)),
        selected_frames=[samples[0],high[0],samples[-1]],
        unique_lift_command_poses=[dict(t=x['t'],servo=x['commanded_servo']) for i,x in enumerate(samples)
            if i==0 or x['commanded_servo']!=samples[i-1]['commanded_servo']],
        source_sha256={n:sha(p/n) for n in ['student_record.json','robots/r3/frames.jsonl','eval_only/trajectory.jsonl']},
        wall_per_sim=read(p/'result.json')['wall_per_sim'])


if __name__=='__main__':
    rs=[audit(s) for s in (1042,1043,1044)];base=rs[0]['calibrated_geometry']['v3']
    for r in rs:
        g=r['calibrated_geometry']['v3'];d=np.array(g['block_floor_heading_m'])-base['block_floor_heading_m']
        rot=np.array(base['block_rotation_heading']).T@np.array(g['block_rotation_heading'])
        r['relative_to_s1042']=dict(block_center_delta_mm=(1000*d).tolist(),distance_mm=float(1000*np.linalg.norm(d)),
            rotation_delta_deg=float(np.degrees(np.arccos(np.clip((np.trace(rot)-1)/2,-1,1)))))
    out=dict(scope='OFFLINE_EXPLORATION, GT evaluation only; no simulation',runs=rs,
        finding='Same issued HIGH, block relative displacement <=1.58 mm. Nominal calibrated rays predict cyan in all three; actual images disagree. Command pose or block pose alone does not establish cause.',
        limitation='Actual measured arm joints, gripper pose, camera xpose and sleep/cache state were not logged. Wall/ceiling-like RGB is not proof of upward optical axis. Camera/renderer state remains unresolved; do not call the gray region cyan occlusion.',
        sources=['scripts/red_block/physical_state_machine_reference.py:103-111','scripts/red_block/pick.py:393-400','scripts/red_block/poses.py:12-20','https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html'])
    Path('experiments/2026-10-06-s2-realism/carry-view-comparison.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('seed','carry_area','relative_to_s1042')} for r in rs],indent=2))
