"""Default-off gcp5 native closed-loop teacher -> own-map v7 route recording.

Demonstration only, never ACT/LLM success. Static registration is own RGB only;
spawn and held truth are isolated in setup/evaluation. No CPU integration.
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
TEACHER='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'

def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(a):
    if not a.enabled or not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('EXPLICIT_GCP5_ONLY')
    q=json.loads(a.queue.read_text())
    if (ROOT/'SOURCE_SHA').read_text().strip()!=q['source_sha']:raise ValueError('SOURCE_PIN_CHANGED')
    for name,h in json.loads((ROOT/'SOURCE_FILES.json').read_text()).items():
        if sha(ROOT/name)!=h:raise ValueError('SOURCE_BYTES_CHANGED:'+name)
    if not Path(q['rejection_table']).is_file():raise ValueError('PRIOR_FUNNEL_REQUIRED')
    if not Path('/home/ugrp/ugrp-sim/leases/mapbuild7.json').is_file():raise ValueError('OWN_LEASE_REQUIRED')
    vendor=ROOT/'experiments/2026-10-17-mapbuild7/vendor'
    sys.path[:0]=[str(vendor),str(ROOT),str(a.teacher_source/'scripts'),str(ROOT/'scripts'),str(a.teacher_source),str(a.renderer),str(a.renderer/'scripts')]
    import sim,harness,scripts
    for package,name in ((sim,'sim'),(harness,'harness'),(scripts,'scripts')):
        package.__path__.extend([str(a.teacher_source/name),str(a.renderer/name)])
    sim.__path__.insert(0,str(a.teacher_source/'sim'));scripts.__path__.insert(0,str(a.teacher_source/'scripts'))
    os.chdir(a.renderer)
    import numpy as np
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from types import SimpleNamespace
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_dynamics_v2 import load_fitted_hardware,MasterPiDynamicsV2
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_drive_friction_v7 import transform_xml,DriveParameters
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic,raw_fisheye_remap
    from sim import masterpi_camera_review_v3 as camera
    from sim.zone_cargo_contact import apply as cargo_contact
    core_spec=importlib.util.spec_from_file_location('mapbuild7_warp_core',vendor/'warp_act_core.py')
    core=importlib.util.module_from_spec(core_spec);core_spec.loader.exec_module(core)
    control_tape,runtime_sleep_policy=core.control_tape,core.runtime_sleep_policy
    from scripts.warp5_render import Renderer
    from scripts.simalt_physics_compare import unused_efm
    from scripts import probe_scene_tex2 as st
    from scripts.mapbuild3_prepare import named_sets
    from scripts.mapbuild2_capture import quaternion_heading
    from scripts.mapbuild6_capture import command_delta,duty
    from harness.rbpf_rejection import motion_variance
    from harness.mapbuild_camera import adapters,CommandCamera
    from harness.servo_camera_fk import CARRY_OPTION
    from harness.mapbuild_rbpf import MapbuildRBPF,OPTION as RBPF
    from harness.mapbuild_static_registration import StaticRegistration,OPTION as STATIC
    from harness.e2e_rgb_vo import compose
    from harness.self_odom_grid import transform
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from sim.spawn_overlap_check import check,OPTION as OVERLAP
    from scripts.zone_teacher import plan_path,proportional_drive,FOLDED
    from sim.grasp_act_solo_lookaround import SoloLookaround
    from scripts.mapbuild7_teacher import VisibleTeacher
    from warp_act_scene import make_scene
    cv2.setNumThreads(1);plan=json.loads(a.pickup.read_text());plan={**plan,'scenario_id':'s1_normal_mixed_v7','end_color_scene':'off'}
    if plan['kind']!='cyan' or plan['item_id']!='cyan_2':raise ValueError('REGISTERED_CYAN2_ONLY')
    import sim.grasp_act_solo_teacher
    expected=q['teacher_class_sha256'];module=Path(sys.modules['sim.grasp_act_solo_teacher'].__file__)
    if sha(module)!=expected:raise ValueError('FROZEN_TEACHER_CLASS_REQUIRED')
    scene=make_scene(plan);hardware,_=load_fitted_hardware()
    xml=cargo_contact(scene.transform(build_multi_robot_xml(hardware)),'cargo_noslip_v1')
    xml=scene.robot_transform(xml,hardware=hardware,calibrated_keys=hardware)
    xml=transform_xml(xml,DriveParameters(),'mesh','off')
    owner=ROOT/'experiments/2026-10-16-mapbuild4/vendor/warp_native_contact.py'
    if sha(owner)!='a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':raise ValueError('OWNER_BYTES_CHANGED')
    spec=importlib.util.spec_from_file_location('native_owner',owner);native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    xml=native.apply(xml,'warp_native_contact_v1');m=mujoco.MjModel.from_xml_string(xml)
    en=mujoco.mjtSleepPolicy;m.tree_sleep_policy[:]=runtime_sleep_policy(m.tree_sleep_policy.copy(),auto=int(en.mjSLEEP_AUTO),auto_never=int(en.mjSLEEP_AUTO_NEVER),auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),never=int(en.mjSLEEP_NEVER),allowed=int(en.mjSLEEP_ALLOWED))
    for rid in ('r1','r2','r3'):
        cid=m.camera(rid+'__robot_cam').id;m.cam_pos[cid]=camera.POSITION_M;m.cam_quat[cid]=camera.QUAT_WXYZ
        m.cam_resolution[cid]=(640,480);m.cam_sensorsize[cid]=(640,480);m.cam_intrinsic[cid]=mujoco_pixel_intrinsic(640,480)
    hardware=v3_hardware(hardware);hardware.setdefault('servo6_center_pwm',1500.)
    d=mujoco.MjData(m);mujoco.mj_resetData(m,d)
    # Setup-only spawns never become a localization anchor.
    for rid,spawn in plan['spawns'].items():
        st._free_pose(m,d,rid+'__robot',spawn[:3],spawn[3]);st.set_arm(m,d,rid,FOLDED,hardware)
    mujoco.mj_forward(m,d);admission=check(m,d,**named_sets(m),option=OVERLAP)
    if not admission['accepted']:raise ValueError('START_PENETRATING')
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'own-rgb').mkdir()
    static=scene.config['static_map'];dump(a.output/'static-map.json',static);(a.output/'scene.xml').write_text(xml);dump(a.output/'admission.json',admission)
    dump(a.output/'scene.json',scene.manifest)
    if a.preflight:
        dump(a.output/'preflight.json',dict(accepted=True,cpu_physics_steps=0,mjwarp_physics_steps=0,teacher_class_sha256=sha(module),native_noslip=int(m.opt.noslip_iterations),scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest()))
        return
    ctrl=np.zeros((1,m.nu))
    for i in range(m.nu):
        if '__servo_' in m.actuator(i).name:ctrl[0,i]=d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i,0])])]
    d.ctrl[:]=ctrl[0];wp.init();wm=mjw.put_model(m)
    if m.opt.noslip_iterations!=0 or wm.opt.noslip_iterations!=0:raise ValueError('NOSLIP0_REQUIRED')
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
    mx,my=raw_fisheye_remap(640,480);servos=(1,3,4,5,6)
    jointnames={1:('left_gripper_close','right_gripper_close'),3:('wrist_pitch',),4:('elbow',),5:('shoulder',),6:('arm_yaw',)}
    sidnames={1:'gripper',3:'wrist',4:'elbow',5:'shoulder',6:'yaw'};lookup=np.empty((5,2001));servo_ids=[]
    for k,sid in enumerate(servos):
        joints=[m.joint('r1__'+j).id for j in jointnames[sid]];ids=[i for i in range(m.nu) if int(m.actuator_trnid[i,0]) in joints];servo_ids.append(ids)
        for pwm in range(500,2501):
            targets=MasterPiDynamicsV2.pulse_to_joint_targets(SimpleNamespace(physical_params=hardware),{sid:pwm});jid=joints[0];v=targets[sidnames[sid]]
            lookup[k,pwm-500]=float(np.clip(v,*m.jnt_range[jid])) if m.jnt_limited[jid] else v
    wheel_ids=[m.actuator('r1__wheel_'+n+'_drive').id for n in ('fl','fr','rl','rr')]
    applied=np.array([[FOLDED[s] for s in servos]],float);relay=np.zeros((1,4),int);drive=DriveParameters()
    teacher=VisibleTeacher(m,plan,FOLDED,a.output,scene);prescan=SoloLookaround({},ops=teacher.teacher.ops,truth_free_v1=True);prescan.arm();prescan.start(0.,1500)
    camera_stream=CommandCamera(camera_pose=CARRY_OPTION);colour=a.vision/'experiments/2026-10-16-reloc16/colour-calibration.json'
    if sha(colour)!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':raise ValueError('COLOUR_CHANGED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',json.loads(colour.read_text()),option=RELOC16_OPTION)
    registration=StaticRegistration(static,option=STATIC);rbpf=MapbuildRBPF(FOLDED,option=RBPF)
    own=[];labels=[];saved=[];issued=[];trace=[];events=[];teacher_rows=[];wall_ledger=[];ring=deque(maxlen=101)
    pose=np.zeros(3);anchor=None;old=None;previous=None;last_servo=None;stage='prescan';route=None;goal=None;start_return=None;status='cap_end';error=None;source_sha=q['source_sha'];start=time.monotonic();next_scan=0.
    d_eval=mujoco.MjData(m)
    body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    region=static['regions']['zone_A'];from harness.visual_arm_v3 import MOUNT_X_M
    destination=(region['center_m'][0]-(MOUNT_X_M+.152),region['center_m'][1])
    rects=[(*o['center_m'],*o['half_extents_m'],o.get('yaw_rad',0.)) for o in static['obstacles']]
    def try_register(t,label):
        nonlocal anchor
        result=registration.register(wall_ledger);events.append(dict(t=t,event=label,**result))
        if result['status']=='accepted':anchor=np.asarray(result['static_from_own'])
        dump(a.output/('registration-'+label+'.json'),result)
        return result
    try:
        for tick in range(round(a.sim_budget*10)+1):
            t=tick/10
            if (a.output/'SUPERVISOR_STOP.json').exists():status='SUPERVISOR_STOP';break
            qp=wd.qpos.numpy()[0].copy()
            if np.any(wd.overflow.numpy()) or not np.isfinite(qp).all():raise RuntimeError('CAPACITY_OR_NONFINITE')
            images=rc.render();rgb={}
            for rid in ('r1','r2'):
                im=cv2.remap(np.clip(images[rid][0][0],0,255).astype(np.uint8),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                file=a.output/'own-rgb'/f'{rid}-{tick:05d}.jpg';cv2.imwrite(str(file),cv2.cvtColor(im,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
                rgb[rid]=cv2.cvtColor(cv2.imread(str(file)),cv2.COLOR_BGR2RGB)
            servo={s:int(v) for s,v in zip(servos,np.rint(applied[0]))};flow={'status':'bootstrap'}
            delta=np.asarray(command_delta(previous,.1)) if previous else np.zeros(3);cov=np.diag(motion_variance(delta))
            flow,scan=camera_stream.observe(t,old,rgb['r1'],servo,state)
            increment=np.asarray(flow['delta']) if flow['status']=='measured' else delta;C=np.asarray(flow['covariance']) if flow['status']=='measured' else cov;pose=compose(pose,increment)
            estimate,wall_event=rbpf.step(t,tick,increment,C,scan,servo=servo)
            if scan['segments'] and t>=next_scan:
                wall_ledger.extend([transform(s,pose).tolist() for s in scan['segments']]);next_scan=t+1.
            file=a.output/'own-rgb'/f'r1-{tick:05d}.jpg'
            own.append(dict(sequence='actual-v7-route',robot_id='r1',frame_id=tick,t=t,rgb=str(file.relative_to(a.output)),sha256=sha(file),servo={str(s):v for s,v in servo.items()},command_delta=delta.tolist(),command_covariance=cov.tolist()))
            trace.append(dict(t=t,frame_id=tick,lk_pose=pose.tolist(),rbpf_pose=estimate,lk=flow,motion_delta=increment.tolist(),motion_covariance=C.tolist(),wall_event=wall_event))
            # Separate evaluation channel. Only the visible-only teacher below
            # gets a perception mirror; mapper, FK and route never see it.
            labels.append(dict(frame_id=tick,t=t,pose=np.r_[qp[adr:adr+2],quaternion_heading(qp[adr+3:adr+7])].tolist()));saved.append(qp);ring.append(tick)
            old=rgb['r1'];last_servo=servo
            if tick==round(a.sim_budget*10):break
            if stage=='prescan':
                cmd,done=prescan.step(t,servo,lambda:rgb['r1'])
                if done:
                    try_register(t,'prescan');stage='pickup';events.append(dict(t=t,event='map_to_teacher_handoff',student=False))
            elif stage in ('pickup','release'):
                # Own-camera visible demonstration teacher exception, not an
                # input to visual odometry or static registration.
                d.qpos[:]=qp;d.time=t;mujoco.mj_forward(m,d)
                cmd,done,detail=teacher.step(t,rgb['r1'],d);teacher_rows.append(dict(t=t,**detail))
                if stage=='pickup' and teacher.ready_to_carry:
                    stage='carry';events.append(dict(t=t,event='own_rgb_pickup_hold_confirmed',physical_success='evaluation_only'))
                    result=try_register(t,'postpickup')
                    if anchor is None:status='MAP_REGISTRATION_REQUIRED';break
                    start_return=compose(anchor,pose).copy();goal=destination;route=None;cmd=teacher.pause(t)
                if teacher.teacher.result not in (None,'command_complete'):status='TEACHER_FAILURE';break
                if stage=='release' and done:
                    events.append(dict(t=t,event='post_setdown_lookaround_end',views=teacher.look.record()))
                    try_register(t,'postsetdown');stage='return';goal=tuple(start_return[:2]);route=None;cmd=teacher.pause(t)
            else:
                if anchor is None:raise RuntimeError('NO_REGISTERED_STATIC_FRAME')
                absolute=compose(anchor,pose)
                if route is None or tick%10==0:route=plan_path(tuple(absolute[:2]),goal,tuple(static['bounds_m']),[],rects=rects)
                if not route:
                    events.append(dict(t=t,event='no_static_route',category='map_planner',reason='40000_node_search_no_route',blocked_object='static_walls',minimum_gap_m=None,gap_status='not_measured'));status='NO_ROUTE';break
                target=next((p for p in route if math.dist(p,absolute[:2])>=.06),goal)
                action=proportional_drive(absolute,goal,target,0.);wheels,durations=duty([3*action['forward'],3*action['left'],.65*action['turn']])
                cmd=teacher.pause(t);cmd={**cmd,'wheels':wheels,'duration_s':durations}
                if math.dist(absolute[:2],goal)<=.025 and abs(math.atan2(math.sin(absolute[2]),math.cos(absolute[2])))<=.04:
                    if stage=='return':events.append(dict(t=t,event='estimated_return_arrival'));status='ROUTE_COMMAND_COMPLETE';break
                    events.append(dict(t=t,event='estimated_zone_arrival'));events.append(dict(t=t,event='post_setdown_lookaround_start'))
                    teacher.release(t+.1);stage='release';cmd=teacher.pause(t)
            issued.append(cmd);previous=cmd
            values,state_cmd=control_tape([dict(ctrl=ctrl[0],wheels=cmd['wheels'],deadlines=[t+v if v else -1. for v in cmd['duration_s']],applied=applied[0],target=[cmd['pwm'][str(s)] for s in servos],servo_active=np.ones(5,bool),now=t,servo_time=t)],relay,dt=float(m.opt.timestep),steps=round(.1/m.opt.timestep),lookup=lookup,wheel_ids=wheel_ids,servo_ids=servo_ids,start_fraction=drive.start_fraction,kinetic_fraction=drive.kinetic_fraction,torque_cap_nm=drive.torque_cap_nm)
            applied=state_cmd['applied'];relay=state_cmd['relay'];wp.copy(tape,wp.array(values,dtype=float));step_index.zero_();wp.capture_launch(cap.graph)
            if tick%10==0:
                progress=dict(sim_s=t,stage=stage,phase=teacher.teacher.phase,wall_s=time.monotonic()-start,frames=len(own),own_lk_pose=pose.tolist(),registered=anchor is not None)
                dump(a.output/'progress.json',progress)
                d_eval.qpos[:]=qp;mujoco.mj_forward(m,d_eval)
                from sim.grasp_act_solo_evaluation import bottom_z
                minimum=min(bottom_z('box',d_eval.geom_xpos[g],d_eval.geom_xmat[g].reshape(3,3),m.geom_size[g]) for g in teacher.gids)
                dump(a.output/'eval-progress.json',dict(evaluation_only=True,t=t,stage=stage,phase=teacher.teacher.phase,cargo_min_z_m=minimum,cargo_xyz=d_eval.xpos[teacher.body].tolist()))
                print(json.dumps(progress),flush=True)
    except BaseException as exc:error=repr(exc);status='HOST_ERROR';raise
    finally:
        dump(a.output/'own.json',dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',physics_backend='mjwarp',frames=own));dump(a.output/'commands.json',issued);dump(a.output/'online-trajectory.json',trace)
        dump(a.output/'eval-only.json',dict(evaluation_only=True,frames=labels));np.savez_compressed(a.output/'eval-state.npz',qpos=np.asarray(saved));dump(a.output/'events.json',events);dump(a.output/'teacher-input-audit.json',teacher.audit.record());dump(a.output/'teacher-ledger.json',teacher_rows)
        dump(a.output/'teacher-result.json',teacher.teacher.diagnostic());dump(a.output/'wall-ledger.json',wall_ledger)
        dump(a.output/'summary.json',dict(status=status,error=error,frames=len(own),sim_s=(len(own)-1)/10,wall_s=time.monotonic()-start,source_sha=source_sha,teacher_sha=TEACHER,scene='walls_floor_contrast_v5_indigo110_s80',physics_backend='mjwarp',contact_profile=dict(profile='warp_native_contact_v1',noslip_iterations=int(m.opt.noslip_iterations),gpu_noslip_iterations=int(wm.opt.noslip_iterations)),cpu_physics_steps=0,top_camera_frames=0,terminal_ring=dict(indices=list(ring),hz=10),required_route_complete=status=='ROUTE_COMMAND_COMPLETE',input_audit=teacher.audit.record(),student_success=False,llm_success=False,wall_cap=None))
        dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for n in ('queue','renderer','teacher-source','vision','pickup','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--sim-budget',type=float,default=1800.);p.add_argument('--preflight',action='store_true')
    run(p.parse_args())
