"""Evaluation-only saved-state geometry and interval-error distribution on gcp5."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess


def run(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    import numpy as np
    import mujoco
    seal=json.loads((a.prediction/'prediction-seal.json').read_text())
    for name,h in seal['prediction_sha256'].items():
        if hashlib.sha256((a.prediction/name).read_bytes()).hexdigest()!=h:raise ValueError('SEALED_PREDICTION_CHANGED')
    os.chdir(a.renderer);m=mujoco.MjModel.from_xml_string((a.input/'scene.xml').read_text());d=mujoco.MjData(m)
    states=np.load(a.input/'eval-state.npz')['qpos'];rows=json.loads((a.prediction/'trajectory.json').read_text())
    history=json.loads(subprocess.check_output(['zstd','-dc',str(a.commands)]))['pickup']
    own=json.loads((a.input/'own.json').read_text())['frames'];commands=json.loads((a.input/'commands.json').read_text())
    obj=m.geom('cargo_cyan_2_geom').id;finger=[m.geom('r1__'+x+'_finger').id for x in ('left','right')]
    physical=[];groups=defaultdict(list)
    world=np.array([r['pose'] for r in json.loads((a.input/'eval-only.json').read_text())['frames']])
    for k,q in enumerate(states):
        d.qpos[:]=q;mujoco.mj_forward(m,d)  # kinematics/contact geometry only, zero integration
        center=d.geom_xpos[obj].copy();rotation=d.geom_xmat[obj].reshape(3,3);half=m.geom_size[obj]
        corners=np.array([center+rotation@(half*[x,y,z]) for x in (-1,1) for y in (-1,1) for z in (-1,1)])
        gaps=[]
        for gid in finger:
            local=(d.geom_xpos[gid]-center)@rotation
            point_box=float(np.linalg.norm(np.maximum(abs(local)-half,0)))
            # Distance from finger bounding sphere to the box is a geometric
            # lower bound. Positive proves separation; zero does NOT prove contact.
            gaps.append(max(0.,point_box-float(m.geom_rbound[gid])))
        phase=history[k]['phase'] if k<len(history) else 'after_pickup_prefix'
        physical.append(dict(t=k/10,phase=phase,minimum_box_z_m=float(corners[:,2].min()),cargo_xyz=center.tolist(),
            gripper_midpoint_xyz=((d.geom_xpos[finger[0]]+d.geom_xpos[finger[1]])/2).tolist(),
            left_right_surface_gap_lower_bound_m=gaps,blocked_object='cargo_cyan_2',
            minimum_gap_m=float(min(gaps)),gap_status='original geometry bounding-sphere lower bound; zero means inconclusive'))
        if k:
            dx,dy=world[k,:2]-world[k-1,:2];c,s=math.cos(world[k-1,2]),math.sin(world[k-1,2])
            gt=np.array([c*dx+s*dy,-s*dx+c*dy,math.atan2(math.sin(world[k,2]-world[k-1,2]),math.cos(world[k,2]-world[k-1,2]))])
            e=np.asarray(rows[k]['motion_delta'])-gt;e[2]=math.atan2(math.sin(e[2]),math.cos(e[2]))
            groups[rows[k]['lk']['status']].append([float(np.linalg.norm(e[:2])),float(abs(e[2]))])
    dist=[]
    for reason,values in groups.items():
        x=np.array(values);dist.append(dict(reason=reason,n=len(x),xy_residual_sum_m=float(x[:,0].sum()),
            xy_residual_p95_m=float(np.percentile(x[:,0],95)),yaw_residual_sum_deg=float(np.degrees(x[:,1].sum())),
            category='interval_motion_residual',blocked_object='own_camera_support',minimum_gap_m=None,gap_status='not_measured'))
    dist.sort(key=lambda r:r['xy_residual_sum_m'],reverse=True)
    lift=[r for r in physical if r['phase'] in ('lift','lift_settle','lookback_pose','lookback','lookback_settle','verify_lift','hold')]
    close=[r for r in physical if r['phase']=='close']
    result=dict(status='PHYSICAL_REPLAY_FAILURE',frames=len(states),source='saved native states after prediction seal',
        lift=dict(n=len(lift),max_minimum_box_z_m=max(r['minimum_box_z_m'] for r in lift),
            original_teacher_required_clearance_m=.012,qualifying_frames=sum(r['minimum_box_z_m']>=.012 for r in lift)),
        close=dict(n=len(close),minimum_surface_gap_lower_bound_m=min(r['minimum_gap_m'] for r in close),
            provably_separated_both_fingers_frames=sum(all(v>0 for v in r['left_right_surface_gap_lower_bound_m']) for r in close)),
        intervals=dist,interpretation='residual sums diagnose intervals, not an additive decomposition of final SE2 error',
        physical_rows=physical,cpu_physics_steps=0,control_feedback=0,parameter_fitting=0,
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.input/'eval-state.npz',a.input/'scene.xml',a.prediction/'prediction-seal.json',a.commands)})
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='physical_rows'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','prediction','renderer','commands','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
