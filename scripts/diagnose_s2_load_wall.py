"""Finite factorial plant diagnostic. No robot controller, no compensation fitting."""
import argparse, hashlib, importlib.util, json, math, os, time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'experiments/2026-10-06-s2-realism/load-wall-criteria.json'
TEMPLATE=Path('/Users/changmin/projects/ugrp/outputs/s2-stiff-cal-20261007/start/setup_bundle.json')
TIMES=(0.,.95,1.90,2.85,3.80,6.35)
ACTION=dict(kind='mecanum',forward=0.,left=.65,turn=0.,duration_s=.65)


def poses():
    from harness.zone_pair_highpose import HIGH
    from harness.zone_solo_cyan_v106 import pose_of
    from harness.zone_solo_cyan_real_carry import CARRY,LOOK_AHEAD
    return dict(search={1:2000,**pose_of('search')},high={1:1500,**HIGH},real_delivery=CARRY,look_ahead=LOOK_AHEAD)


def cases():
    return [(wall,name,load) for wall in ('far','near') for name,load in
            [('search',False),('high',False),('high',True),('look_ahead',False),('look_ahead',True),('real_delivery',False),('real_delivery',True)]]


def contact_class(names):
    wall=any('wall' in n or 'divider' in n or 'door' in n for n in names)
    own=next((n for n in names if n.startswith('r3__')),None)
    cargo=any('cargo_box_00' in n for n in names)
    if wall and own:
        return 'wall_finger' if 'finger' in own else 'wall_wheel' if 'wheel_' in own else 'wall_body'
    if wall and cargo:return 'wall_cargo'
    if own and 'wheel_' in own:return 'wheel_other'
    if own and 'finger' in own and cargo:return 'grasp'
    return None


def measurement(world,robot,cargo):
    import mujoco
    from sim.s2_eval_camera_trace import camera_row
    m,d=world.model,world.data;contacts=[];fingers=set();force=np.zeros(6)
    for i in range(d.ncon):
        con=d.contact[i];names=[m.geom(int(g)).name or '' for g in con.geom];kind=contact_class(names)
        if kind:
            mujoco.mj_contactForce(m,d,i,force)
            contacts.append(dict(geoms=names,category=kind,distance_m=float(con.dist),force_contact_frame=force.tolist()))
            if kind=='grasp':fingers.add(next(n for n in names if n.startswith('r3__')))
    mass=robot.robot_mass_kg;com=d.subtree_com[robot.robot_bid].copy();cargo_xyz=d.xpos[cargo].copy();boxmass=m.body_mass[cargo]
    return dict(t=float(d.time),xyz=robot.base_xyz().tolist(),rpy=robot.base_rpy().tolist(),
        robot_com=com.tolist(),robot_plus_box_com=((mass*com+boxmass*cargo_xyz)/(mass+boxmass)).tolist(),
        cargo_xyz=cargo_xyz.tolist(),bilateral=len(fingers)==2,contacts=contacts,
        wheel_torque_nm=d.actuator_force[robot.wheel_act].tolist(),
        camera=camera_row(world,'r3',float(d.time)),
        active_welds=sum(int(d.eq_active[i]) for i in range(m.neq) if m.eq_type[i]==mujoco.mjtEq.mjEQ_WELD))


def visibility(world,row,static,geo):
    from types import SimpleNamespace as NS
    from harness.zone_solo_cyan_visibility import pixel_rays
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D,scaled_camera_matrix
    import cv2,mujoco
    origin=np.array(row['camera']['camera_cached_xyz_m']);rotation=np.array(row['camera']['camera_cached_optical_rotation'])
    rz=geo.rz(row['rpy'][2]);base=np.r_[row['xyz'][:2],0.];cols=np.linspace(8,631,96).astype(int)
    cm=NS(origin=rz.T@(origin-base),_rot=rz.T@rotation,columns=cols)
    ys,points,depth=geo.bottom_projection(cm,np.r_[row['xyz'][:2],row['rpy'][2]],geo.wall_segments(static))
    inside=np.isfinite(ys)&(ys>=4)&(ys<=470);clear=0;occluders={}
    for k in np.flatnonzero(inside):
        # Evaluate actual collision geometry along the wall-foot ray; RGB policy never sees this.
        target=rz@points[k]+base;target[2]+=.001
        v=target-origin;length=np.linalg.norm(v);gid=np.array([-1],dtype=np.int32)
        dist=mujoco.mj_ray(world.model,world.data,origin,v/length,None,1,-1,gid)
        name=world.model.geom(int(gid[0])).name if gid[0]>=0 else 'none'
        if dist<0 or dist>=length-.012 or ('wall' in name or 'divider' in name):clear+=1
        else:occluders[name]=occluders.get(name,0)+1
    return dict(columns=96,in_view=int(inside.sum()),clear=clear,occluders=occluders)


def board_capture(world,robot,pose,out):
    """Known surveyed checkerboard geometry + RGB PnP. GT sidecar never fitted."""
    import mujoco
    from PIL import Image
    from harness import s2_extrinsic_targets as target
    from harness.s2_stiff_camera_calibration import fit
    from scripts.run_final_environment_checks import write
    rows=[]
    for board in target.boards(pose):
        mid=int(world.model.body('cal_board').mocapid[0]);quat=np.zeros(4)
        mujoco.mju_mat2Quat(quat,np.asarray(board['rotation']).ravel())
        world.data.mocap_pos[mid]=np.array(board['origin_m'])+np.array([3.,-1.,0.])
        world.data.mocap_quat[mid]=quat;s=board['square_m']
        world.model.geom('cal_border').size[:2]=[5.5*s,4*s]
        for y in range(6):
            for x in range(9):
                g=world.model.geom(f'cal_{x}_{y}');g.pos[:2]=[(x-4)*s,(y-2.5)*s];g.size[:2]=s/2
        mujoco.mj_forward(world.model,world.data)
        rgb=world.render_rgb(robot_id='r3',camera='robot_cam');path=out/f'board-{board["index"]}.png';Image.fromarray(rgb).save(path)
        row=dict(**board,path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        try:row.update(corners_px=target.detect(rgb).tolist(),status='detected')
        except ValueError as exc:row['status']=str(exc)
        rows.append(row)
    write(out/'board-observations.json',rows)
    world.data.mocap_pos[mid]=[0,0,3];mujoco.mj_forward(world.model,world.data)
    if any(r['status']!='detected' for r in rows):return dict(status='TARGET_MISSING')
    rec,quality=target.fit(rows)
    return dict(status='FIT',record=rec,normal=fit(rows),quality=quality,fit_uses_gt=False)


def run_case(out,wall,name,loaded,sha,geo):
    import mujoco
    from PIL import Image
    from sim.s2_realism import make_scene
    from sim.s2_realism_camera_binding import bound_world
    from sim.s2_servo_stiffness import transform_xml
    from sim.s2_extrinsic_capture import board_xml
    from sim.s2_align_pulse import FinePulsePort
    from sim.masterpi_drive_friction_v7 import PROFILE
    from harness.zone_pair_highpose import HIGH
    from harness.zone_solo_cyan_real_carry import transition
    from scripts.run_final_environment_checks import write
    out.mkdir();start=time.monotonic();world=None;rows=[];frames=[];staging=[];commands=[]
    result=dict(case=out.name,wall=wall,pose=name,loaded=loaded,source_sha=sha,status='HOST_ERROR',physical_success=None,task_run=False,model_calls=0,loadavg_start=os.getloadavg())
    try:
        bundle=json.loads(TEMPLATE.read_text());scene=make_scene(bundle,1051)
        xyz=[3.,-1. if wall=='far' else 1.3495,.0325]
        scene.config['setup_only']['spawns']['r3']=[*xyz,0.]
        item=next(iter(scene.config['setup_only']['objects'].values()));item['position_m']=[.5,-.5,.016]
        original=scene.robot_transform;scene.robot_transform=lambda xml,**kw:transform_xml(original(xml,**kw),servo_stiffness='real_v1')
        original_world=scene.transform;scene.transform=lambda xml:board_xml(original_world(xml))
        world=bound_world(scene,drive_profile=PROFILE,idle_robot_contacts='freeze_v1',seed=1051,width=640,height=480,render=True,warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None)
        scene.setup(world);robot=world.robot('r3');m,d=world.model,world.data;dt=m.opt.timestep
        (out/'scene.xml').write_text(world.scene_xml)
        target=poses()[name].copy();target[1]=1500 if loaded else 2000
        initial={1:2000,**HIGH} if loaded else target
        robot.set_servo_pulses(initial,forward_only=True);robot.set_base_pose_for_test(xyz,0.)
        cargo=m.body(item['body_name']).id;q=int(m.jnt_qposadr[m.body_jntadr[cargo]])
        if loaded:
            d.qpos[q:q+3]=robot.site_xyz('grip_site');d.qpos[q+3:q+7]=d.xquat[robot.gripper_bid]
            for jid in robot.gripper_joint:d.qpos[int(m.jnt_qposadr[jid])]=(.0467-.040)/2
            robot.set_servo_pulses({1:1500})
        mujoco.mj_forward(m,d)
        port=FinePulsePort(world,'r3',allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        lost=None
        def step(seconds,monitor=True):
            nonlocal lost
            for i in range(round(seconds/dt)):
                port.tick(float(d.time));world._physics_step_for(robot)
                if i%max(1,round(.05/dt))==0:
                    row=measurement(world,robot,cargo);staging.append(row)
                    if row['active_welds']:raise RuntimeError('WELD_FORBIDDEN')
                    if max(abs(x) for x in row['rpy'][:2])>math.radians(15):raise RuntimeError('ROBOT_TILT_LIMIT')
                    if loaded and monitor:
                        if not row['bilateral']:
                            if lost is None:lost=row['t']
                            if row['t']-lost>=.3:raise RuntimeError('GRIP_LOSS')
                        else:lost=None
                        if row['cargo_xyz'][2]<.06:raise RuntimeError('LOAD_DROP')
        step(.8,False)
        if loaded and not measurement(world,robot,cargo)['bilateral']:raise RuntimeError('STAGING_GRIP_ABSENT')
        for p,duration,settle in transition({1:1500,**HIGH},target) if loaded else []:
            for sid,pulse in p.items():
                action=dict(kind='look',pan_pulse=pulse,duration_s=duration) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pulse,duration_s=duration)
                port.apply(action,float(d.time));commands.append(dict(t=float(d.time),**action))
            step(duration+settle)
        step(2.)
        first=measurement(world,robot,cargo)
        result.update(robot_mass_kg=float(robot.robot_mass_kg),box_mass_kg=float(m.body_mass[cargo]),initial=first,
                      pose_command=target,setup='one-time manual placement in HIGH; normal contacts only, no clamp/weld; sequential real servo transition')
        if wall=='far' and name=='look_ahead':result['calibration']=board_capture(world,robot,target,out)
        t0=float(d.time);pulse_starts={};pulse_ends={};next_frame=0.
        for i in range(round(7.15/dt)+1):
            rel=round(i*dt,9)
            for j,t in enumerate(TIMES):
                if abs(rel-t)<dt/2:
                    pulse_starts[j]=measurement(world,robot,cargo);port.apply(ACTION,float(d.time));commands.append(dict(t=float(d.time),relative_t=rel,**ACTION))
                if abs(rel-(t+.75))<dt/2:pulse_ends[j]=measurement(world,robot,cargo)
            port.tick(float(d.time));world._physics_step_for(robot)
            if i%max(1,round(.05/dt))==0:
                row=measurement(world,robot,cargo);row['relative_t']=rel;rows.append(row)
                if loaded:
                    if not row['bilateral']:
                        if lost is None:lost=row['t']
                        if row['t']-lost>=.3:raise RuntimeError('GRIP_LOSS')
                    else:lost=None
                    if row['cargo_xyz'][2]<.06:raise RuntimeError('LOAD_DROP')
            if rel+1e-8>=next_frame:
                row=rows[-1];rgb=world.render_rgb(robot_id='r3',camera='robot_cam');path=out/f'{len(frames):03d}.png';Image.fromarray(rgb).save(path)
                frames.append(dict(path=path.name,t=row['t'],sha256=hashlib.sha256(path.read_bytes()).hexdigest(),visibility=visibility(world,row,scene.config['static_map'],geo)))
                next_frame+=.5
        pulses=[]
        for j in range(6):
            a,b=pulse_starts[j],pulse_ends[j];yaw=a['rpy'][2];rot=np.array([[np.cos(yaw),np.sin(yaw)],[-np.sin(yaw),np.cos(yaw)]])
            delta=rot@(np.array(b['xyz'][:2])-a['xyz'][:2]);dyaw=math.atan2(math.sin(b['rpy'][2]-yaw),math.cos(b['rpy'][2]-yaw))
            pulses.append(dict(index=j,start_t=a['t'],end_t=b['t'],delta_body_m=delta.tolist(),yaw_deg=math.degrees(dyaw)))
        result.update(status='MEASURED',pulses=pulses,sim_s=float(d.time),pulse_sim_s=7.15,
            mean_lateral_m=float(np.mean([p['delta_body_m'][1] for p in pulses])),mean_abs_yaw_deg=float(np.mean([abs(p['yaw_deg']) for p in pulses])),
            clear_wall_fraction=sum(f['visibility']['clear'] for f in frames)/(96*len(frames)),
            bilateral_fraction=float(np.mean([r['bilateral'] for r in rows])),final=rows[-1])
    except Exception as exc:
        result.update(status='PHYSICAL_FAILURE' if str(exc) in ('GRIP_LOSS','LOAD_DROP','ROBOT_TILT_LIMIT','STAGING_GRIP_ABSENT') else 'HOST_ERROR',error=f'{type(exc).__name__}: {exc}')
        if result['status']=='HOST_ERROR':raise
    finally:
        write(out/'commands.json',commands);write(out/'frames.json',frames)
        for name_,data_ in [('eval-only.jsonl',rows),('staging-eval-only.jsonl',staging)]:
            (out/name_).write_text(''.join(json.dumps(r)+'\n' for r in data_))
        result['wall_s']=time.monotonic()-start;write(out/'result.json',result)
        if world is not None:world.close()
    print(json.dumps({k:result.get(k) for k in ('case','status','mean_lateral_m','clear_wall_fraction','error')}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not a.execute:print(json.dumps(dict(execution_started=False,cases=cases(),pulse=ACTION,times=TIMES)));return
    from scripts.run_final_environment_checks import check_source,write
    from scripts import agent_lock
    check_source(a.expected_source_sha)
    if not a.output or not a.output.is_absolute() or a.output.exists():raise ValueError('new absolute output required')
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',purpose='s2v36 controlled pose/load/wall ablation',pid=os.getpid(),expected_minutes=15,timing_sensitive=True)
    a.output.mkdir();results=[];failures={}
    try:
        path=ROOT/'experiments/2026-10-06-s2-realism/analyze_visibility.py';spec=importlib.util.spec_from_file_location('posthoc_visibility',path);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
        write(a.output/'configuration.json',dict(source_sha=a.expected_source_sha,criteria=json.loads(PLAN.read_text()),criteria_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),options=dict(servo_stiffness='real_v1',idle_robot_contacts='freeze_v1',drive_profile='masterpi_drive_friction_v7',camera='v3',roller_collision='mesh'),loadavg_start=os.getloadavg()))
        for wall,name,loaded in cases():
            result=run_case(a.output/f'{wall}-{name}-{"loaded" if loaded else "empty"}',wall,name,loaded,a.expected_source_sha,geo);results.append(result)
            if result['status']!='MEASURED':
                cause=result['error'];failures[cause]=failures.get(cause,0)+1
                if failures[cause]>=2:break
    finally:
        write(a.output/'result.json',dict(schema='ugrp.s2.load_wall.v1',source_sha=a.expected_source_sha,results=results,requested_cases=len(cases()),completed_cases=len(results),same_cause_failures=failures,model_calls=0,gt_use='staging and evaluation only; no controller'))
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex');write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))

if __name__=='__main__':main()
