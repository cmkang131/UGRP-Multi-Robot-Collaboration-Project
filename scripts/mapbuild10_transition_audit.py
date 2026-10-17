"""Saved-state camera FK audit on original VM CPU, no integration/render."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('ORIGINAL_VM_ONLY')
    sys.path.insert(0,str(a.source));os.chdir(a.assets)
    import numpy as np
    import mujoco
    from harness.servo_camera_fk import transform_from_commands,CARRY_OPTION
    from harness.e2e_rgb_vo import K
    from harness.mapbuild_static_registration import wall_segments
    from harness.self_odom_grid import transform
    read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,h in read(a.prediction/'prediction-seal.json').items():
        if sha(a.input/name)!=h:raise ValueError('SEALED_INPUT_CHANGED')
    m=mujoco.MjModel.from_xml_string((a.input/'scene.xml').read_text());d=mujoco.MjData(m);cid=m.camera('r1__robot_cam').id
    own=read(a.input/'own.json')['frames'];gt=read(a.input/'eval-only.json')['frames'];scans=read(a.input/'scans.json');tr=read(a.input/'online-trajectory.json');qpos=np.load(a.input/'eval-state.npz')['qpos']
    if not len(own)==len(gt)==len(scans)==len(tr)==len(qpos):raise ValueError('FRAME_JOIN_REQUIRED')
    walls=np.asarray(wall_segments(read(a.input/'static-map.json')));u,v=walls[:,0],walls[:,1]-walls[:,0];inv=np.linalg.inv(K)
    def nearest(p):
        q=np.clip(np.einsum('nsi,si->ns',p[:,None]-u,v)/(v*v).sum(1),0,1)
        return np.linalg.norm(p[:,None]-(u+q[...,None]*v),axis=2).min(1)
    rows=[]
    for f,g,scan,r,qp in zip(own,gt,scans,tr,qpos):
        if f['t']!=g['t'] or f['t']!=r['t']:raise ValueError('TIME_JOIN_REQUIRED')
        fk,reason=transform_from_commands({int(k):z for k,z in f['servo'].items()},camera_pose=CARRY_OPTION)
        if fk is None:continue
        d.qpos[:]=qp;mujoco.mj_forward(m,d)
        yaw=g['pose'][2];c,s=math.cos(yaw),math.sin(yaw);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        actual_o=R.T@(d.cam_xpos[cid]-np.r_[g['pose'][:2],0]);actual_r=R.T@d.cam_xmat[cid].reshape(3,3)@np.diag([1,-1,-1]);no,nr=fk
        points=[]
        for col in scan['columns']:
            if col['status']!='hit':continue
            ray=actual_r@(inv@[col['column'],col['row'],1.])
            if ray[2]<0:points.append((actual_o-actual_o[2]/ray[2]*ray)[:2])
        residual=nearest(transform(points,g['pose'])) if points else []
        rows.append(dict(t=f['t'],stage=r['stage'],lk_status=r['lk']['status'],motion_source=f['command_motion_source'],
            position_error_m=float(np.linalg.norm(no-actual_o)),rotation_error_deg=math.degrees(math.acos(float(np.clip((np.trace(nr.T@actual_r)-1)/2,-1,1)))),
            nominal_height_m=float(no[2]),actual_height_m=float(actual_o[2]),actual_camera_reprojection_wall_p95_m=float(np.percentile(residual,95)) if len(residual) else None,
            issued_servo=f['servo']))
    a.output.mkdir(exist_ok=False);(a.output/'rows.json').write_text(json.dumps(rows,indent=2)+'\n')
    result=dict(frames=len(rows),cpu_integrations=0,render_calls=0,truth_to_controller=0,scope='evaluation FK only; actual camera never supplied to controller',
        position_p50_p95_max_m=np.percentile([r['position_error_m'] for r in rows],[50,95,100]).tolist(),rotation_p50_p95_max_deg=np.percentile([r['rotation_error_deg'] for r in rows],[50,95,100]).tolist(),
        last_second=[r for r in rows if r['t']>=rows[-1]['t']-1.],high_residual_frames=[r for r in rows if r['t'] in (.1,31.7)],
        source_sha256={str(p):sha(p) for p in [Path(__file__),a.input/'scene.xml',a.input/'eval-state.npz',a.prediction/'prediction-seal.json']},reproduction=sys.argv)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','assets','input','prediction','output'):p.add_argument('--'+n,type=Path,required=True)
    main(p.parse_args())
