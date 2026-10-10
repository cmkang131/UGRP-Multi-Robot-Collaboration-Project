"""Read saved RGB/commands/eval only; no world, stepping, render, or control feedback."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from harness import markerless_box as box
from harness import zone_color_boxes as colors
from harness.zone_solo_cyan_contract_v106 import ROOT, CALIBRATION
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_solo_cyan_vision_v106 import CyanVision
from harness.zone_final_pair_vision import GRASP_RADIUS_M


def read(p):
    return json.loads(p.read_text())


def rows(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def nearest(items, key, t):
    return min(items, key=lambda r: abs(r[key]-t))


def delta(a, b):
    x, y = np.asarray(b['robot_xyz_m'][:2])-a['robot_xyz_m'][:2]
    c, s = math.cos(a['robot_yaw_rad']), math.sin(a['robot_yaw_rad'])
    return dict(forward_m=c*x+s*y, left_m=-s*x+c*y,
                xy_m=math.hypot(x, y), yaw_deg=math.degrees(b['robot_yaw_rad']-a['robot_yaw_rad']))


def body_center(row, *, xyz=None, yaw=None):
    x, y = np.asarray(row['cyan_xyz_m'][:2])-np.asarray(xyz or row['robot_xyz_m'])[:2]
    theta = row['robot_yaw_rad'] if yaw is None else yaw
    c, s = math.cos(theta), math.sin(theta)
    return np.array([c*x+s*y, -s*x+c*y, row['cyan_xyz_m'][2]])


def analyze(raw):
    record=read(raw/'student_record.json')
    frames=rows(raw/'robots/r3/frames.jsonl');trace=rows(raw/'eval_only/trajectory.jsonl')
    pulses=record['real_output']['transformations'][-8:]
    calibration=camera_calibration(read(ROOT/CALIBRATION));vision=CyanVision(calibration)
    cache={}
    def observation(t, fit=False):
        f=nearest(frames,'sim_time',t);key=f['frame_id']
        if key not in cache:
            p=raw/f['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
            im=cv2.imread(str(p));mask=colors._mask(cv2.cvtColor(im,cv2.COLOR_BGR2HSV),colors.OWN_ZONE_CYAN_HSV)
            y,x=np.nonzero(mask)
            cache[key]=dict(t=f['sim_time'],frame_id=key,path=str(p),sha256=f['sha256'],
                area_px=len(x),centroid_px=[float(x.mean()),float(y.mean())] if len(x) else None,
                bbox_xyxy=[int(x.min()),int(y.min()),int(x.max()),int(y.max())] if len(x) else None,
                commanded_servo=f['commanded_servo'])
        out=dict(cache[key])
        if fit:
            found=vision.detect({'image':(raw/f['path']).read_bytes()},{int(k):v for k,v in f['commanded_servo'].items()})
            out['estimated_centers_base_m']=[d['estimated_box_center_base_m'] for d in found]
        return out
    measured=[]
    for i,p in enumerate(pulses):
        start=p['t'];end=start+p['issued']['duration_s'];after=pulses[i+1]['t'] if i+1<len(pulses) else end+.55
        a=nearest(trace,'t',start);b=nearest(trace,'t',end);c=nearest(trace,'t',after)
        measured.append(dict(**p,start=observation(start,True),powered_end=observation(end),
            next_command_or_settled=observation(after),powered_delta=delta(a,b),
            through_next_or_settled_delta=delta(a,c),eval_center_before_m=body_center(a).tolist(),
            eval_center_after_m=body_center(c).tolist()))
    last=pulses[-1];a=nearest(trace,'t',last['t']);b=nearest(trace,'t',last['t']+last['issued']['duration_s']+.55)
    servo={int(k):v for k,v in nearest(frames,'sim_time',last['t'])['commanded_servo'].items()}
    origin,axes=vision.extrinsics(servo)
    def project(pt):
        cam=(pt-origin)@axes.T
        uv,_=cv2.fisheye.projectPoints(cam.reshape(1,1,3),np.zeros(3),np.zeros(3),box.scaled_camera_matrix(640,480),np.asarray(box.CAMERA_FISHEYE_D))
        return uv.reshape(2).tolist()
    cf={name:project(center) for name,center in {
        'before':body_center(a),'actual_after':body_center(b),
        'translation_only_after':body_center(b,yaw=a['robot_yaw_rad']),
        'yaw_only_after':body_center(b,xyz=a['robot_xyz_m']),
    }.items()}
    sweep=[observation(f['sim_time']) for f in frames if last['t']-.05<=f['sim_time']<=last['t']+1.2]
    return dict(source_raw=str(raw),source_sha=read(raw/'result.json')['source_sha'],
        method='saved BGR cyan HSV masks; commanded fixed-camera projection; eval poses only for offline scoring',
        tolerance=dict(forward_m=.003,left_m=.003,grasp_radius_m=GRASP_RADIUS_M,consecutive_frames=2),
        pulses=measured,loss_window=sweep,center_projection_counterfactual_px=cf,
        limits='Projection is analytic, not counterfactual rendering/physics; commanded arm extrinsics, no measured joints. No control feedback.',
        source_file_sha256={n:hashlib.sha256((raw/n).read_bytes()).hexdigest() for n in ['student_record.json','eval_only/trajectory.jsonl','robots/r3/frames.jsonl']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=analyze(args.raw)
    with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(pulses=len(result['pulses']),projection=result['center_projection_counterfactual_px'])))
