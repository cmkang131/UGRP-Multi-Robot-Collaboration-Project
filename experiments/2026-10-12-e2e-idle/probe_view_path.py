"""Bounded saved-input controller replay: no simulator, model or referee input."""
import argparse
import base64
import hashlib
import io
from PIL import Image
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np
from harness.e2e_live_mapping import Robot
from harness.e2e_stall_odometry import Options as StallOptions
from harness.s4_event_policy import Options
from harness.range_provider import OwnUltrasonicRangeProvider
from harness.ultrasonic_model import RangeReading
from harness import e2e_boundary_views as views


def rows(p):
    data=p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
    return [json.loads(data)] if p.name.endswith('.json') else [json.loads(x) for x in data.splitlines() if x]


def probe(raw, limit):
    cv2.setNumThreads(1)
    p=raw/'robots/r1';b=rows(raw/'bundle.json')[0];opts=b['e2e_options']
    keys=('setdown_only_when_relook','goal_geometry','exploration_progress','pose_fix','path_follow',
          'mapping_budget_s','boundary_views','b_marker_detect','vo_floor_mask','vo_rotation_policy','explore_deadlock')
    kw={('relook' if k=='setdown_only_when_relook' else k):opts[k] for k in keys if k in opts}
    kw['stall_options']=StallOptions(**{k:opts.get(k,'off') for k in ('stall_odometry','stall_recovery','stall_noise')})
    root=Path.cwd();cov=json.loads((root/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot=Robot('r1',b['seed'],cov,Options(**b['study_options']),**kw)
    robot.range_provider=OwnUltrasonicRangeProvider()
    frames={f['frame_id']:f for f in rows(p/'frames.jsonl')}
    recorded=rows(p/'ownmap.jsonl')[:limit]
    origin=frames[recorded[0]['frame_id']]['sim_time']-recorded[0]['t']
    commands=[dict(c,t=round(c['t']-origin,8)) for c in rows(p/'commands.jsonl')
              if c['kind']!='initial_servo_command' and c['t']>=origin-1e-8]
    ranges=rows(p/'inputs/range.jsonl')[1:]
    ci=ri=0;checks=[];max_pose_error=0.;command_differences=0
    navigator=robot.goal.explorer.navigator;original=views.observed_path_clear
    now=0.
    def checked(costmap,pose,path,yaw):
        result=original(costmap,pose,path,yaw)
        if navigator.view_active and not result:
            strict_sweep=views.observed_sweep_clear
            first_block=[]
            def native_only(cm,a,b):
                if not strict_sweep(cm,a,b) and not first_block:
                    a,b=np.asarray(a,float),np.asarray(b,float)
                    turn=(b[2]-a[2]+np.pi)%(2*np.pi)-np.pi
                    steps=max(1,int(np.ceil(np.linalg.norm(b[:2]-a[:2])/.025)),int(np.ceil(abs(turn)/np.deg2rad(5))))
                    for u in np.linspace(0,1,steps+1):
                        pose_u=np.r_[a[:2]+u*(b[:2]-a[:2]),a[2]+u*turn]
                        if not views.Costmap.pose_clear(cm,pose_u):
                            mask,_=cm.footprint_mask(pose_u)
                            first_block.append(dict(pose=pose_u.tolist(),unknown_footprint_cells=int(np.sum(cm.raw[mask]==255)),occupied_footprint_cells=int(np.sum(cm.raw[mask]==254)),native_clear=bool(cm.pose_clear(pose_u))))
                            break
                return cm.sweep_clear(a,b)
            views.observed_sweep_clear=native_only
            try:native=original(costmap,pose,path,yaw)
            finally:views.observed_sweep_clear=strict_sweep
            samples=[]
            for xy in path:
                cell=costmap.world_to_map(xy)
                if cell is not None:samples.append(int(costmap.raw[cell[1],cell[0]]))
            checks.append(dict(t=now,path_points=len(path),strict_path_clear=result,native_path_clear=bool(native),first_strict_block=first_block,
                strict_start_clear=bool(views.Costmap.pose_clear(costmap,pose)),
                native_start_clear=bool(costmap.pose_clear(pose)),
                strict_terminal_clear=bool(views.Costmap.pose_clear(costmap,[*path[-1],yaw])) if path else None,
                native_terminal_clear=bool(costmap.pose_clear([*path[-1],yaw])) if path else None,
                unknown_path_centers=samples.count(255),occupied_path_centers=samples.count(254)))
        return result
    views.observed_path_clear=checked
    for old in recorded:
        now=old['t'];frame=frames[old['frame_id']]
        while ci<len(commands) and (commands[ci]['t']<now-1e-8 or now==0 and commands[ci]['kind'] in ('arm','look')):
            c=commands[ci];robot.commanded({k:v for k,v in c.items() if k!='t'},c['t']);ci+=1
        while ri<len(ranges) and ranges[ri]['t']<=now+1e-8:
            r=ranges[ri];robot.range_provider.on_reading(RangeReading(r['t'],r['range_m'] if r['valid'] else float('nan'),r['valid'],r['status']));ri+=1
        data=(raw/frame['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==old['sha256']==frame['sha256']
        rgb=np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
        trace=robot.receive(dict(frame_id=frame['frame_id'],sim_time=now,sha256=frame['sha256'],image=base64.b64encode(data).decode()),rgb)
        max_pose_error=max(max_pose_error,float(np.max(np.abs(robot.goal.explorer.local_pose-np.array(old['pose_own_m'])))))
        command_differences+=robot.nav_command!=old['command']
        if checks:break
    return dict(scope='saved own RGB/range/issued commands; no physics/referee/model',run=raw.parent.name,
        frames=frame['frame_id'],last_sim_s=now,max_pose_abs_difference=max_pose_error,
        navigation_command_differences=command_differences,path_checks=checks)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--frames',type=int,default=100)
    a=p.parse_args();print(json.dumps(probe(a.raw,a.frames)))
