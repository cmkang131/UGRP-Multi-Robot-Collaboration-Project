"""Offline saved-frame audit. No MuJoCo import, world, rendering, or stepping.

Archived settled-command camera extrinsics + eval-only body yaw/block pose.
Pixel rays intersect a cuboid analytically; no gripper/scene occlusion is assumed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from harness.zone_solo_cyan_contract_v106 import CALIBRATION
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_pair_highpose_contract import camera_record
from harness.zone_solo_cyan_scene_change import lens_valid
from harness.zone_color_boxes import _mask, OWN_ZONE_CYAN_HSV
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def rows(p):
    return [json.loads(s) for s in p.read_text().splitlines()]


def project(trace, rec):
    yaw = trace['robot_yaw_rad']
    c, s = np.cos(yaw), np.sin(yaw)
    heading = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    center = heading @ (np.array(trace['cyan_xyz_m'])-np.r_[trace['robot_xyz_m'][:2], 0])
    rotation = heading @ np.array(trace['cyan_rotation']).reshape(3, 3)
    half = np.array(trace['box_half_m'])
    origin, camera = np.array(rec['origin_m']), np.array(rec['rotation'])
    corners = np.array([[x,y,z] for x in (-1,1) for y in (-1,1) for z in (-1,1)])*half
    optical = (center+corners@rotation.T-origin)@camera
    assert np.all(optical[:, 2] > 0), 'behind-camera cuboid requires separate clipping'
    k, d = scaled_camera_matrix(640,480), np.array(CAMERA_FISHEYE_D)
    uv = cv2.fisheye.projectPoints(optical.reshape(-1,1,3), np.zeros(3), np.zeros(3), k, d)[0].reshape(-1,2)
    yy, xx = np.mgrid[:480,:640]
    norm = cv2.fisheye.undistortPoints(np.stack((xx,yy),-1).astype(float).reshape(-1,1,2), k, d).reshape(-1,2)
    rays = np.c_[norm,np.ones(len(norm))]@camera.T@rotation
    local_origin = (origin-center)@rotation
    with np.errstate(divide='ignore'):
        a, b = (-half-local_origin)/rays, (half-local_origin)/rays
    near, far = np.minimum(a,b).max(1), np.maximum(a,b).min(1)
    hit = (far >= np.maximum(near,0)).reshape(480,640)
    visible = hit & lens_valid()
    ys, xs = np.nonzero(visible)
    return dict(camera_origin_floor_heading_m=origin.tolist(), camera_rotation=camera.tolist(),
        optical_forward_floor_heading=camera[:,2].tolist(), block_center_floor_heading_m=center.tolist(),
        corner_uv=uv.tolist(), corner_bbox_xyxy=np.r_[uv.min(0),uv.max(0)].tolist(),
        positive_depth_min_m=float(optical[:,2].min()), rectangular_ray_pixels=int(hit.sum()),
        valid_ray_pixels=int(visible.sum()), in_valid_image=bool(visible.any()),
        valid_bbox_xyxy=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None)


def audit(raw):
    record=read(raw/'student_record.json');trace=rows(raw/'eval_only/trajectory.jsonl');frames=rows(raw/'robots/r3/frames.jsonl')
    hover=next(e['t'] for e in record['events'] if e['event']=='state' and e['state']=='hover')
    check=next(e['t'] for e in record['events'] if e['event']=='cyan_hover_check')
    cal=read(Path(CALIBRATION)); nearest=lambda rs,key,t:min(rs,key=lambda r:abs(r[key]-t))
    images=[]
    for f in [f for f in frames if hover <= f['sim_time'] <= check]:
        p=raw/f['path'];assert sha(p)==f['sha256']
        mask=_mask(cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2HSV),OWN_ZONE_CYAN_HSV)
        ys,xs=np.nonzero(mask)
        images.append(dict(t=f['sim_time'],path=str(p),sha256=f['sha256'],area_px=len(xs),
            bbox_xyxy=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None))
    poses=[]
    for label,t in [('aligned',hover),('settled_hover',check)]:
        f=nearest(frames,'sim_time',t);tr=nearest(trace,'t',t)
        servo={int(k):v for k,v in f['commanded_servo'].items()}
        poses.append(dict(label=label,t=t,eval_sample_t=tr['t'],eval_pose=tr,commanded_servo=servo,
            variants={name:project(tr,camera_record(table,'unloaded',servo)) for name,table in
                [('previous',cal),('v3',camera_calibration(cal))]}))
    return dict(raw=str(raw),seed=read(raw/'bundle.json')['task']['seed'],
        source_sha=read(raw/'result.json')['source_sha'],frames=images,poses=poses,
        first_zero_t=next(i['t'] for i in images if i['area_px']==0),
        source_sha256={n:sha(raw/n) for n in ('result.json','student_record.json','eval_only/trajectory.jsonl','robots/r3/frames.jsonl')})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=dict(scope='offline geometry, not a physical counterfactual or runtime input',
        method='OpenCV fisheye projection + analytic pixel-ray/cuboid intersection + actual raw-remap valid mask',
        limitation='settled commanded calibration; per-frame measured joints/roll/pitch not logged; no scene occlusion',
        calibration=dict(path=CALIBRATION,sha256=sha(Path(CALIBRATION))),
        sources=['https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html'],
        runs=[audit(raw) for raw in args.raw])
    with args.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps([dict(seed=r['seed'],first_zero_t=r['first_zero_t'],
        hover={k:v['valid_ray_pixels'] for k,v in r['poses'][1]['variants'].items()}) for r in out['runs']]))
