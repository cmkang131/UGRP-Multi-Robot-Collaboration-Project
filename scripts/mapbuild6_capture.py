"""gcp5 native MJWarp task-route attempt, own camera/commands only.

Replay an archived successful teacher's issued pickup commands, then run the
existing map planner/pursuit toward its v7 delivery region. This is a replay
attempt, not a new teacher/student/LLM success. A separate evaluator may stop
an actually failed pickup; no evaluator value changes an action.
"""
import argparse
from collections import deque
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrap(x):
    return math.atan2(math.sin(x),math.cos(x))


def command_delta(command,dt):
    # Exact 6f057f7e:harness/grasp_act_visible_world.py:11-14. Historical
    # nominal wheel kinematics, NOT fitted native contact odometry. Keep this
    # limitation visible in every fallback frame and the final comparison.
    a,b,c,d=[w*min(dt,t) for w,t in zip(command['wheels'],command['duration_s'])]
    gain=.0325*150*2*math.pi/60
    return [gain*(a+b+c+d)/4,gain*(-a+b+c-d)/4,gain*(-a+b-c+d)/(4*.1255)]


def duty(drive):
    # Exact 6f057f7e:sim/grasp_act_port.py:duty_wheels, 10Hz period.
    f,l,t=drive;desired=[f-l-t,f+l+t,f+l-t,f-l+t]
    scale=max(.35,max(map(abs,desired)));w=[];duration=[]
    for v in desired:
        dt=.1*abs(v)/scale
        w.append(0. if dt<.001 else math.copysign(.35,v));duration.append(0. if dt<.001 else dt)
    return w,duration


def build(a):
    sys.path[:0]=[str(a.renderer),str(a.renderer/'scripts'),str(ROOT),str(ROOT/'scripts')]
    os.chdir(a.renderer)
    import sim,scripts,harness
    sim.__path__.append(str(ROOT/'sim'));scripts.__path__.append(str(ROOT/'scripts'));harness.__path__.append(str(ROOT/'harness'))
    import mujoco
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_dynamics_v2 import load_fitted_hardware
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_drive_friction_v7 import transform_xml,DriveParameters
    from sim import masterpi_camera_review_v3 as camera
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
    from sim.render_profile_selection import for_name
    from sim.final_pair_highpose_nearclip import wrap as near_wrap
    from scripts.warp_act_core import runtime_sleep_policy
    scene=ScenarioFinalV3Scene.from_scenario('s1_normal_mixed_v7',601)
    # Existing pinned gatesv5_release_extension contains the longer v7 divider
    # (zone_wall_divider_1_250_14750_2000). Do not synthesize/reassign materials.
    scene=near_wrap(for_name(a.scene).install(scene,a.scene,extension=a.texture_extension))
    hardware,_=load_fitted_hardware()
    xml=scene.robot_transform(scene.transform(build_multi_robot_xml(hardware)),hardware=hardware,calibrated_keys=hardware)
    xml=camera.transform_xml(xml,profile_id=camera.PROFILE_ID)
    xml=transform_xml(xml,DriveParameters(),'mesh','off')
    owner=ROOT/'experiments/2026-10-16-mapbuild4/vendor/warp_native_contact.py'
    if sha(owner)!='a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':
        raise ValueError('NATIVE_OWNER_BYTES_REQUIRED')
    spec=importlib.util.spec_from_file_location('native_owner',owner);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    xml=mod.apply(xml,'warp_native_contact_v1');m=mujoco.MjModel.from_xml_string(xml)
    en=mujoco.mjtSleepPolicy
    m.tree_sleep_policy[:]=runtime_sleep_policy(m.tree_sleep_policy.copy(),auto=int(en.mjSLEEP_AUTO),auto_never=int(en.mjSLEEP_AUTO_NEVER),
        auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),never=int(en.mjSLEEP_NEVER),allowed=int(en.mjSLEEP_ALLOWED))
    for rid in ('r1','r2','r3'):
        cid=m.camera(rid+'__robot_cam').id;m.cam_pos[cid]=camera.POSITION_M;m.cam_quat[cid]=camera.QUAT_WXYZ
        m.cam_resolution[cid]=(640,480);m.cam_sensorsize[cid]=(640,480);m.cam_intrinsic[cid]=mujoco_pixel_intrinsic(640,480)
    hardware=v3_hardware(hardware);hardware.setdefault('servo6_center_pwm',1500.)
    return m,scene,hardware,xml


def run(a):
    if not a.enabled or platform.system()!='Linux' or not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('EXPLICIT_GCP5_ONLY')
    queue=json.loads(a.queue.read_text())
    if a.sim_budget!=1800.:
        raise ValueError('S1_V7_REGISTERED_SIM_BUDGET_1800_REQUIRED')
    if not Path(queue['rejection_table']).is_file() or not Path(queue['requirements']).is_file():
        raise ValueError('PREREGISTERED_REQUIREMENTS_AND_FUNNEL_REQUIRED')
    if sha(queue['requirements'])!=queue['requirements_sha256']:raise ValueError('REQUIREMENTS_CHANGED')
    for p,h in json.loads((ROOT/'SOURCE_FILES.json').read_text()).items():
        if sha(ROOT/p)!=h:raise ValueError('SOURCE_BYTES_CHANGED:'+p)
    if (ROOT/'SOURCE_SHA').read_text().strip()!=queue['source_sha']:raise ValueError('SOURCE_SHA_MISMATCH')
    if not Path('/home/ugrp/ugrp-sim/leases/mapbuild6.json').is_file():raise ValueError('OWN_LEASE_REQUIRED')
    import numpy as np
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    m,scene,hardware,xml=build(a)
    from scripts import probe_scene_tex2 as st
    from scripts.warp5_render import Renderer
    from scripts.warp_act_core import control_tape
    from scripts.simalt_physics_compare import unused_efm
    from scripts.mapbuild2_capture import quaternion_heading
    from scripts.mapbuild3_prepare import named_sets
    from sim.spawn_overlap_check import check,OPTION
    from sim.masterpi_camera_profile import raw_fisheye_remap
    from sim.masterpi_drive_friction_v7 import DriveParameters
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from types import SimpleNamespace
    from harness.e2e_rgb_vo import ground_pair,compose,between,K,D
    from harness.rbpf_rejection import motion_variance
    from scripts.zone_teacher import plan_path,proportional_drive
    cv2.setNumThreads(1)
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'own-rgb').mkdir()
    import subprocess
    history_bytes=(subprocess.check_output(['zstd','-dc',str(a.commands)]) if a.commands.suffix=='.zst' else a.commands.read_bytes())
    plan=json.loads(a.pickup.read_text());history=json.loads(history_bytes)
    commands=history['pickup'];release=history['release']
    if plan['kind']!='cyan' or plan['item_id']!='cyan_2':raise ValueError('PINNED_CYAN2_REPLAY_ONLY')
    if commands[-1]['phase']!='hold':raise ValueError('PICKUP_HOLD_PREFIX_REQUIRED')
    static=scene.config['static_map'];dump(a.output/'static-map.json',static)
    d=mujoco.MjData(m);mujoco.mj_resetData(m,d)
    # These are declared setup conditions only. The estimator starts at zero;
    # no runtime pose, qpos, contact or success value enters it/the planner.
    for rid,spawn in plan['spawns'].items():
        st._free_pose(m,d,rid+'__robot',spawn[:3],spawn[3])
        st.set_arm(m,d,rid,{int(k):v for k,v in commands[0]['command']['pwm'].items()},hardware)
    mujoco.mj_forward(m,d);admission=check(m,d,**named_sets(m),option=OPTION)
    dump(a.output/'admission.json',admission)
    if not admission['accepted']:raise ValueError('REPLAY_START_PENETRATING')
    ctrl=np.zeros((1,m.nu))
    for i in range(m.nu):
        if '__servo_' in m.actuator(i).name:ctrl[0,i]=d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i,0])])]
    d.ctrl[:]=ctrl[0];wp.init();wm=mjw.put_model(m)
    if m.opt.noslip_iterations!=0 or wm.opt.noslip_iterations!=0:raise ValueError('NOSLIP_MUST_BE_ZERO')
    q0=d.qpos.copy()
    with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=1,nconmax=512,njmax=2048)
    mjw.step(wm,wd);wp.synchronize()
    with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=1,nconmax=512,njmax=2048)
    tape=wp.zeros((round(.1/m.opt.timestep),1,m.nu),dtype=float);step_index=wp.zeros(1,dtype=int)
    @wp.kernel
    def issue(tape:wp.array3d(dtype=float),index:wp.array(dtype=int),out:wp.array2d(dtype=float)):
        i,j=wp.tid();out[i,j]=tape[index[0],i,j]
    @wp.kernel
    def advance(index:wp.array(dtype=int)):
        index[0]=index[0]+1
    with wp.ScopedCapture() as cap:
        for _ in range(round(.1/m.opt.timestep)):
            wp.launch(issue,dim=(1,m.nu),inputs=[tape,step_index,wd.ctrl]);mjw.step(wm,wd);wp.launch(advance,dim=1,inputs=[step_index])
    rc=Renderer(m,wm,wd,[('r1','r1__robot_cam',(640,480)),('r2','r2__robot_cam',(640,480))],enabled=True,texture_after_lighting=True)
    mx,my=raw_fisheye_remap(640,480)
    servos=(1,3,4,5,6);jointnames={'yaw':('arm_yaw',),'shoulder':('shoulder',),'elbow':('elbow',),
        'wrist':('wrist_pitch',),'gripper':('left_gripper_close','right_gripper_close')}
    sidnames={1:'gripper',3:'wrist',4:'elbow',5:'shoulder',6:'yaw'}
    lookup=np.empty((5,2001));servo_ids=[]
    for k,sid in enumerate(servos):
        joints=[m.joint('r1__'+j).id for j in jointnames[sidnames[sid]]]
        ids=[i for i in range(m.nu) if int(m.actuator_trnid[i,0]) in joints];servo_ids.append(ids)
        for p in range(500,2501):
            targets=MasterPiDynamicsV2.pulse_to_joint_targets(SimpleNamespace(physical_params=hardware),{sid:p})
            value=targets[sidnames[sid]];jid=joints[0]
            lookup[k,p-500]=float(np.clip(value,*m.jnt_range[jid])) if m.jnt_limited[jid] else value
    wheel_ids=[m.actuator('r1__wheel_'+n+'_drive').id for n in ('fl','fr','rl','rr')]
    applied=np.array([[commands[0]['command']['pwm'][str(s)] for s in servos]],float);relay=np.zeros((1,4),int)
    drive=DriveParameters();own=[];labels=[];saved=[];issued=[];trace=[];ring=deque(maxlen=101)
    old=None;previous=None;pose=np.zeros(3);origin=plan['spawns']['r1'];start_pose=[origin[0],origin[1],origin[3]]
    dump(a.output/'recording-plan.json',dict(queue=queue,source_commands=str(a.commands),source_commands_sha256=sha(a.commands),
        source_plan=str(a.pickup),source_plan_sha256=sha(a.pickup),scenario='s1_normal_mixed_v7',
        changed_setup='archived successful solo teacher diagnostic spawns; v7 original cargo/geometry unchanged',
        texture_extension='gatesv5_release_extension' if a.texture_extension else 'off',
        absolute_route_prior='declared diagnostic start only; estimator remains zero-gauge; no runtime GT',
        route_stage='existing zone_teacher plan_path/proportional_drive; no LLM/student success claim',
        controls='own RGB LK / issued-command fallback; static map; archived pickup PWM/wheel prefix',
        sim_budget_s=a.sim_budget,source_budget='s1 v7 eval.budget.sim_seconds=1800; no host wall cap',
        required_full_transport=True,forbidden_inputs=dict(top=0,live_truth=0,measured_joints=0,held_world_reads=0)))
    dump(a.output/'scene.json',dict(scene=scene.manifest,xml_sha256=hashlib.sha256(xml.encode()).hexdigest()))
    dump(a.output/'contact-profile.json',dict(profile='warp_native_contact_v1',noslip_iterations=int(m.opt.noslip_iterations),
        gpu_noslip_iterations=int(wm.opt.noslip_iterations),effective_tolerance=float(wm.opt.tolerance.numpy().item())))
    (a.output/'scene.xml').write_text(xml)
    from scripts.mapbuild5_manifest import fixed_floor_calibration
    dump(a.output/'fixed-floor-calibration.json',fixed_floor_calibration({int(k):v for k,v in commands[0]['command']['pwm'].items()}))
    t0=time.monotonic();status='cap_end';route=None;route_started=False;release_tick=None;returning=False
    # Cargo grip/standoff comes from the original teacher's fixed low-pose
    # station geometry (.0482 mount + .152 calibrated arm radius), not GT.
    from harness.visual_arm_v3 import MOUNT_X_M
    region=static['regions']['zone_A'];goal=(region['center_m'][0]-(MOUNT_X_M+.152),region['center_m'][1])
    events=[];error=None;body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    try:
        for tick in range(round(a.sim_budget*10)+1):
            t=tick/10
            if (a.output/'SUPERVISOR_STOP.json').exists():status='SUPERVISOR_STOP';break
            q=wd.qpos.numpy()[0].copy()
            if np.any(wd.overflow.numpy()) or not np.isfinite(q).all():raise RuntimeError('CAPACITY_OR_NONFINITE')
            images=rc.render();rgb={}
            for camera in ('r1','r2'):
                rgb[camera]=cv2.remap(np.clip(images[camera][0][0],0,255).astype(np.uint8),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                path=a.output/'own-rgb'/f'{camera}-{tick:05d}.jpg';cv2.imwrite(str(path),cv2.cvtColor(rgb[camera],cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
            pwm={str(s):int(v) for s,v in zip(servos,np.rint(applied[0]).astype(int))}
            jpg=a.output/'own-rgb'/f'r1-{tick:05d}.jpg'
            # Estimator consumes the actual saved JPEG bytes, exactly as offline.
            rgb1=cv2.cvtColor(cv2.imread(str(jpg)),cv2.COLOR_BGR2RGB)
            delta=np.array(command_delta(previous,.1)) if previous else np.zeros(3)
            covariance=np.diag(motion_variance(delta));flow=dict(status='bootstrap')
            if old is not None:
                flow=ground_pair(old,rgb1,{int(k):v for k,v in pwm.items()}) if pwm==own[-1]['servo'] else dict(status='unknown_servo_change')
            increment=np.array(flow['delta']) if flow['status']=='measured' else delta
            pose=compose(pose,increment)
            own.append(dict(sequence='task-route',robot_id='r1',frame_id=tick,t=t,rgb=str(jpg.relative_to(a.output)),sha256=sha(jpg),
                servo=pwm,command_delta=delta.tolist(),command_covariance=covariance.tolist()))
            trace.append(dict(t=t,lk_pose=pose.tolist(),flow=flow));old=rgb1
            # Separate evaluation writer. None of these values is passed above
            # or to the planner/action generator below.
            gt=np.r_[q[adr:adr+2],quaternion_heading(q[adr+3:adr+7])]
            labels.append(dict(frame_id=tick,t=t,pose=gt.tolist()));saved.append(q);ring.append(tick)
            if tick==round(a.sim_budget*10):break
            if tick<len(commands):
                cmd={**commands[tick]['command'],'t':t};phase=commands[tick]['phase']
            elif release_tick is not None and tick-release_tick<len(release):
                item=release[tick-release_tick];cmd={**item['command'],'t':t};phase=item['phase']
                if phase=='lookaround' and (tick==release_tick or release[tick-release_tick-1]['phase']!='lookaround'):
                    events.append(dict(t=t,event='post_setdown_lookaround_start'))
            else:
                if not route_started:
                    route_started=True;events.append(dict(t=t,event='pickup_prefix_end',physical_success='evaluation_only'))
                if release_tick is not None and not returning:
                    returning=True;route=None;goal=tuple(start_pose[:2])
                    events.append(dict(t=t,event='post_setdown_lookaround_end'))
                    events.append(dict(t=t,event='return_route_start'))
                absolute=compose(start_pose,pose)
                # All obstacles here are STATIC authored walls. Other cargo and
                # peers are not supplied by their live simulator coordinates.
                rects=[(*v['center_m'],*v['half_extents_m'],v.get('yaw_rad',0.)) for v in static['obstacles']]
                if tick%10==0 or route is None:
                    route=plan_path(tuple(absolute[:2]),goal,tuple(static['bounds_m']),[],rects=rects)
                if not route:
                    events.append(dict(t=t,event='no_static_route',category='map_planner',reason='no_static_route',
                        blocked_object='unresolved_static_geometry',minimum_gap_m=None,gap_status='not_measured'))
                    status='NO_ROUTE';break
                # c15d9c539:sim/solo_carry_to_zone.py uses the original
                # visible-route waypoint distance .06 and arrival .025/.04.
                # Retain them; these are controller constants, not new task
                # acceptance tolerances or fits to this recording.
                target=next((p for p in route if math.dist(p,absolute[:2])>=.06),goal)
                action=proportional_drive(absolute,goal,target,0.)
                wheels,durations=duty([3*action['forward'],3*action['left'],.65*action['turn']])
                target_pwm=(release[-1] if returning else commands[-1])['command']['pwm']
                cmd=dict(t=t,wheels=wheels,duration_s=durations,pwm=target_pwm);phase='return_route' if returning else 'carry_to_zone'
                if math.dist(absolute[:2],goal)<=.025 and abs(wrap(absolute[2]))<=.04:
                    if returning:
                        events.append(dict(t=t,event='estimated_return_arrival'));status='ROUTE_COMMAND_COMPLETE';break
                    events.append(dict(t=t,event='estimated_zone_arrival'));release_tick=tick+1
                    cmd=dict(t=t,wheels=[0.]*4,duration_s=[0.]*4,pwm=target_pwm)
            issued.append(cmd);previous=cmd
            rows=[dict(ctrl=ctrl[0],wheels=cmd['wheels'],deadlines=[t+v if v else -1. for v in cmd['duration_s']],
                applied=applied[0],target=[cmd['pwm'][str(s)] for s in servos],servo_active=np.ones(5,bool),now=t,servo_time=t)]
            values,state=control_tape(rows,relay,dt=float(m.opt.timestep),steps=len(tape.numpy()),lookup=lookup,
                wheel_ids=wheel_ids,servo_ids=servo_ids,start_fraction=drive.start_fraction,kinetic_fraction=drive.kinetic_fraction,torque_cap_nm=drive.torque_cap_nm)
            applied=state['applied'];relay=state['relay'];wp.copy(tape,wp.array(values,dtype=float));step_index.zero_();wp.capture_launch(cap.graph)
            if tick%10==0:
                dump(a.output/'progress.json',dict(sim_s=t,phase=phase,frames=len(own),wall_s=time.monotonic()-t0,own_lk_pose=pose.tolist()))
                dump(a.output/'eval-progress.json',dict(evaluation_only=True,sim_s=t,phase=phase,
                    cargo_xyz=wd.xpos.numpy()[0,m.body('cargo_cyan_2').id].tolist()))
                print('recording',t,phase,flush=True)
    except BaseException as exc:
        error=repr(exc);status='HOST_ERROR';raise
    finally:
        dump(a.output/'own.json',dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',physics_backend='mjwarp',frames=own))
        dump(a.output/'commands.json',issued);dump(a.output/'online-trajectory.json',trace)
        dump(a.output/'eval-only.json',dict(evaluation_only=True,first_origin=[labels[0]['pose']] if labels else [],frames=labels))
        np.savez_compressed(a.output/'eval-state.npz',qpos=np.asarray(saved))
        dump(a.output/'events.json',events)
        dump(a.output/'summary.json',dict(status=status,error=error,frames=len(own),sim_s=(len(own)-1)/10,wall_s=time.monotonic()-t0,
            scene=a.scene,physics_backend='mjwarp',contact_profile=dict(profile='warp_native_contact_v1',noslip_iterations=0),
            cpu_physics_steps=0,top_camera_frames=0,terminal_ring=dict(indices=list(ring),hz=10),
            required_route_complete=status=='ROUTE_COMMAND_COMPLETE',
            release_and_lookaround='issued' if returning else 'not reached / separate mandatory gate',
            source_sha=queue['source_sha'],input_audit=dict(truth_inputs=0,held_world_reads=0,top_actor_reads=0,measured_joint_inputs=0)))
        dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    for name in ('renderer','queue','pickup','commands','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--scene',default='walls_floor_contrast_v5_indigo110_s80')
    p.add_argument('--texture-extension',action='store_true')
    p.add_argument('--sim-budget',type=float,required=True)
    run(p.parse_args())
