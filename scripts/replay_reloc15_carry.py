"""GCP fixed-issued-command physics replay for evaluation video/contact audit.

No feedback to any controller. Original source and scene must match. A replay
is diagnostic, never a fresh autonomous success or a substitute for missing RGB.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

import cv2
import mujoco
import numpy as np
from scripts.analyze_reloc11_selfmap import rows
from scripts.run_grasp_act_teacher import apply
from sim.grasp_act_scene import make_scene
from sim.grasp_act_port import DutyActPort
from sim.masterpi_drive_friction_v7 import build_world, PROFILE
from sim.s2_realism_camera_binding import bind_camera


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-video',action='store_true');p.add_argument('--end-s',type=float);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    raw=a.run/'raw';plan=json.loads((raw/'plan.json').read_text());commands=rows(raw/'teacher-commands.jsonl')
    if a.end_s is not None:commands=[r for r in commands if r['t']<=a.end_s]
    ev={round(r['t'],5):r for r in rows(raw/'eval-only.jsonl') if 'base_xyz' in r}
    os.environ['UGRP_SIM_OBSERVER_WIDTH']='320';os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
    scene=make_scene({**plan,'end_color_scene':'off'});scene.config['setup_only']['spawns'].update(plan['spawns'])
    world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=640,height=480,render=True,
        warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
    for c in world.controllers.values():bind_camera(c)
    scene.setup(world);m,d=world.model,world.data;rid=plan['robot_id'];origin=float(d.time)
    scene_equal=world.scene_xml==(raw/'scene.xml').read_text()
    if not scene_equal:raise RuntimeError('original scene XML differs')
    port=DutyActPort(world,rid,allow_reverse=True,allow_mecanum=True)
    previous=dict(pwm={str(s):int(port._servo_pulses[s]) for s in (1,3,4,5,6)})
    body=scene.config['setup_only']['objects'][plan['item_id']]['body_name']
    bid=m.body(body).id
    for name in ('full','tail'): (a.out/name).mkdir()
    probes=[];frames=[];max_xy=0.;xml_hash=hashlib.sha256(world.scene_xml.encode()).hexdigest()
    robot_bodies=[i for i in range(m.nbody) if (m.body(i).name or '').startswith(rid+'__')]
    robot_geoms={g for g in range(m.ngeom) if m.geom_bodyid[g] in robot_bodies}
    physical=dict(robot_mass_kg=float(m.body_mass[robot_bodies].sum()),cargo_mass_kg=float(m.body_mass[bid]),
        drive=world.drive_parameters.record(),scene_xml_sha256=xml_hash,
        cargo_geoms=[dict(name=m.geom(g).name,friction=m.geom_friction[g].tolist(),size=m.geom_size[g].tolist())
            for g in range(m.ngeom) if m.geom_bodyid[g]==bid],
        wheel_friction={m.geom(g).name:m.geom_friction[g].tolist() for g in robot_geoms if 'roller' in (m.geom(g).name or '')})
    ff=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgr24','-s','960x260','-r','8','-i','-',
        '-an','-c:v','libx264','-threads','2','-preset','fast','-crf','27','-pix_fmt','yuv420p',str(a.out/'overview-own.mp4')],stdin=subprocess.PIPE)
    if a.no_video:ff.stdin.write(np.zeros((260,960,3),np.uint8).tobytes())
    try:
        for i,r in enumerate(commands):
            now=float(d.time);assert abs(now-r['t'])<1e-6,(i,now,r['t'])
            base=np.array(world.robot(rid).base_xyz());yaw=float(world.robot(rid).base_rpy()[2]);e=ev.get(round(now,5))
            xy=math.dist(base,e['base_xyz']) if e else None
            if xy is not None:max_xy=max(max_xy,xy)
            # Per-contact forces/lever arms from the evaluator only.
            contacts=[];force=np.zeros(6)
            for k in range(d.ncon):
                c=d.contact[k];g1,g2=int(c.geom1),int(c.geom2)
                if g1 not in robot_geoms and g2 not in robot_geoms and bid not in (m.geom_bodyid[g1],m.geom_bodyid[g2]):continue
                mujoco.mj_contactForce(m,d,k,force)
                names=[m.geom(g1).name,m.geom(g2).name]
                vec=c.frame.reshape(3,3).T@force[:3]
                slip=None
                roller=next((g for g in (g1,g2) if (m.geom(g).name or '').startswith(rid+'__') and 'roller' in (m.geom(g).name or '')),None)
                if roller is not None and 'floor' in names:
                    velocity=np.zeros(6)
                    mujoco.mj_objectVelocity(m,d,mujoco.mjtObj.mjOBJ_GEOM,roller,velocity,0)
                    v=velocity[3:]+np.cross(velocity[:3],c.pos-d.geom_xpos[roller])
                    slip=float(np.linalg.norm(v[:2]))
                contacts.append(dict(names=names,slip_xy_m_s=slip,normal_N=float(force[0]),tangent_N=float(np.linalg.norm(force[1:3])),
                    moment_z_Nm=float(np.cross(c.pos-base,vec)[2]),pos=c.pos.tolist()))
            probes.append(dict(t=now,phase=r['phase'],base_xyz=base.tolist(),yaw_rad=yaw,
                replay_xyz_error_m=xy,cargo_xyz=d.body(body).xpos.tolist(),contacts=contacts,
                wheel_ctrl=d.ctrl[world.controllers[rid].wheel_act].tolist(),
                wheel_qvel=d.qvel[m.jnt_dofadr[m.actuator_trnid[world.controllers[rid].wheel_act,0]]].tolist()))
            tail=now>=commands[-1]['t']-10
            if not a.no_video and (i%5==0 or tail):
                own=cv2.imdecode(np.frombuffer(base64.b64decode(port.capture()['image']),np.uint8),cv2.IMREAD_COLOR)
                top=cv2.imdecode(np.frombuffer(world.render_team_jpeg(camera=scene.config['static_map']['top_cameras'][0]['name']),np.uint8),cv2.IMREAD_COLOR)
                r2=cv2.imdecode(np.frombuffer(base64.b64decode(DutyActPort(world,'r2',allow_reverse=True,allow_mecanum=True).capture()['image']),np.uint8),cv2.IMREAD_COLOR)
                im=np.concatenate([cv2.resize(x,(320,240)) for x in (top,own,r2)],axis=1)
                im=np.pad(im,((20,0),(0,0),(0,0)));cv2.putText(im,f'{now:.1f}s {r["phase"]} yaw={math.degrees(yaw):.2f} replay; overview(eval) | r1 | r2 idle', (3,15),cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1)
                if i%5==0:
                    cv2.imwrite(str(a.out/'full'/f'{i:06d}.jpg'),im);ff.stdin.write(im.tobytes())
                if tail:cv2.imwrite(str(a.out/'tail'/f'{i:06d}.jpg'),im)
                frames.append(dict(t=now,tick=i,tail=tail))
            apply(port,r['command'],now,previous);previous=r['command']
            until=origin+(i+1)*.1
            while float(d.time)<until-1e-8:
                port.tick(float(d.time));world._physics_step_for(world.robot(rid))
        ff.stdin.close();assert ff.wait()==0
        if not a.no_video:subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size','-of','json',str(a.out/'overview-own.mp4')],check=True,stdout=(a.out/'ffprobe.json').open('w'))
        if not a.no_video:assert (a.out/'overview-own.mp4').stat().st_size<=8*1024**2
        (a.out/'physics.json').write_text(json.dumps(physical,indent=2)+'\n')
        with (a.out/'evaluation.jsonl').open('w') as f:
            for r in probes:f.write(json.dumps(r)+'\n')
        report=dict(run=str(a.run),scope='fixed command diagnostic physical replay',scene_equal=scene_equal,
            replay_xyz_max_error_m=max_xy,rows=len(probes),frames=frames,original_capture_hz=1,
            full_replay_hz=2,tail_replay_hz=10,playback_speed=4,physical=physical,
            original_sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.glob('*.jsonl*')})
        (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('frames','physical','original_sources')}))
    finally:
        if ff.poll() is None:ff.kill()
        world.close()


if __name__=='__main__':main()
