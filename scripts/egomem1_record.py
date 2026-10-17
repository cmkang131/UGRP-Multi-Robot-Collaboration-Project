"""One GCP5 MJWarp DEV record, own RGB/commands -> egocentric memory return.

Scene/model and spawn are setup-only. The controller receives no scene,
world pose, static layout, evaluation labels, contacts or measured joints.
All frames are recorded at10Hz, including the final10SIM seconds.
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


def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def duty(drive):
    f,l,t=drive;desired=[f-l-t,f+l+t,f+l-t,f-l+t];scale=max(.35,max(map(abs,desired)))
    duration=[.1*abs(v)/scale for v in desired]
    return [0. if dt<.001 else math.copysign(.35,v) for v,dt in zip(desired,duration)],[0. if dt<.001 else dt for dt in duration]


def command_delta(command,dt):
    a,b,c,d=[w*min(dt,t) for w,t in zip(command['wheels'],command['duration_s'])]
    gain=.0325*150*2*math.pi/60  # unchanged mapbuild6 / frozen wheel model
    return [gain*(a+b+c+d)/4,gain*(-a+b+c-d)/4,gain*(-a+b-c+d)/(4*.1255)]


def run(a):
    if not a.enabled or not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('EXPLICIT_GCP5_ONLY')
    if not (Path('/home/ugrp/ugrp-sim/leases')/(a.lease_name+'.json')).is_file():raise ValueError('OWN_LEASE_REQUIRED')
    q=json.loads(a.queue.read_text())
    import subprocess
    if subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()!=q['source_sha']:raise ValueError('PINNED_SOURCE_REQUIRED')
    if not Path(q['rejection_table']).is_file():raise ValueError('PRIOR_FUNNEL_REQUIRED')
    for name,expected in q.get('input_sha256',{}).items():
        if sha(name)!=expected:raise ValueError('PINNED_INPUT_CHANGED:'+name)
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'own-rgb').mkdir()
    dump(a.output/'queue.json',q)
    # Explicit frozen scene/renderer dependencies; never edit their source.
    sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(a.renderer),str(a.renderer/'scripts'),str(a.legacy)]
    import sim,harness,scripts
    sim.__path__[:0]=[str(a.renderer/'sim'),str(a.legacy/'sim')]
    harness.__path__.extend([str(a.legacy/'harness'),str(a.renderer/'harness')]);scripts.__path__.append(str(a.renderer/'scripts'))
    os.chdir(a.renderer)
    import numpy as np
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from types import SimpleNamespace
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_dynamics_v2 import load_fitted_hardware,MasterPiDynamicsV2
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_drive_friction_v7 import transform_xml,DriveParameters
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic,raw_fisheye_remap
    from sim import masterpi_camera_review_v3 as camera
    from sim.zone_cargo_contact import apply as cargo_contact
    from scripts.warp5_render import Renderer
    from scripts.simalt_physics_compare import unused_efm
    from scripts import probe_scene_tex2 as st
    from harness.mapbuild_camera import CommandCamera
    from harness.mapbuild_command_prior import CommandPrior,OPTION as PRIOR
    from harness.servo_camera_fk import CARRY_OPTION
    from harness.rbpf_rejection import motion_variance
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from harness.active_camera import SEARCH
    from harness.egomem_vision import EgocentricDetector,colour_component_pixels
    from harness.egocentric_landmark_memory import MemoryOptions, LandmarkMemory,OPTION
    from harness.egomem_navigation import MemoryReturn
    from harness.floor_goal_self_mask import body_envelopes
    cv2.setNumThreads(1)
    vendor=ROOT/'experiments/2026-10-17-egomem1/vendor'
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    scene_factory=module('egomem_scene',vendor/'warp_act_scene.py')
    core=module('egomem_core',vendor/'warp_act_core.py')
    control_tape,runtime_sleep_policy=core.control_tape,core.runtime_sleep_policy
    native=module('egomem_native',vendor/'warp_native_contact.py')
    if sha(vendor/'warp_native_contact.py')!='a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':raise ValueError('NATIVE_OWNER_BYTES_REQUIRED')
    # SETUP ONLY: this object is never passed to MemoryReturn or LandmarkMemory.
    plan=json.loads(a.setup.read_text());plan={**plan,'scenario_id':'s1_normal_mixed_v7','end_color_scene':'grasp_act_teal_blue_v1'}
    scene=scene_factory.make_scene(plan);hardware,_=load_fitted_hardware()
    xml=cargo_contact(scene.transform(build_multi_robot_xml(hardware)),'cargo_noslip_v1')
    xml=scene.robot_transform(xml,hardware=hardware,calibrated_keys=hardware)
    xml=native.apply(transform_xml(xml,DriveParameters(),'mesh','off'),'warp_native_contact_v1')
    m=mujoco.MjModel.from_xml_string(xml)
    en=mujoco.mjtSleepPolicy;m.tree_sleep_policy[:]=runtime_sleep_policy(m.tree_sleep_policy.copy(),auto=int(en.mjSLEEP_AUTO),auto_never=int(en.mjSLEEP_AUTO_NEVER),auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),never=int(en.mjSLEEP_NEVER),allowed=int(en.mjSLEEP_ALLOWED))
    for rid in ('r1','r2','r3'):
        cid=m.camera(rid+'__robot_cam').id;m.cam_pos[cid]=camera.POSITION_M;m.cam_quat[cid]=camera.QUAT_WXYZ
        m.cam_resolution[cid]=(640,480);m.cam_sensorsize[cid]=(640,480);m.cam_intrinsic[cid]=mujoco_pixel_intrinsic(640,480)
    hardware=v3_hardware(hardware);hardware.setdefault('servo6_center_pwm',1500.)
    d=mujoco.MjData(m);mujoco.mj_resetData(m,d)
    for rid,spawn in plan['spawns'].items():
        st._free_pose(m,d,rid+'__robot',spawn[:3],spawn[3]);st.set_arm(m,d,rid,SEARCH,hardware)
    mujoco.mj_forward(m,d)
    from sim.spawn_overlap_check import check,OPTION as OVERLAP
    floor={m.geom(i).name for i in range(m.ngeom) if int(m.geom_type[i])==int(mujoco.mjtGeom.mjGEOM_PLANE) and any(word in m.geom(i).name.lower() for word in ('floor','ground'))}
    cargo={m.body(i).name for i in range(1,m.nbody) if int(m.body_jntnum[i]) and int(m.jnt_type[int(m.body_jntadr[i])])==int(mujoco.mjtJoint.mjJNT_FREE) and not m.body(i).name.startswith(('r1__','r2__','r3__'))}
    wall={m.geom(i).name for i in range(m.ngeom) if 'wall' in m.geom(i).name.lower()}
    admission=check(m,d,floor_geoms=floor,cargo_bodies=cargo,wall_geoms=wall,option=OVERLAP)
    dump(a.output/'admission.json',admission)
    if not admission['accepted']:raise ValueError('START_PENETRATING')
    (a.output/'scene.xml').write_text(xml);dump(a.output/'scene.json',scene.manifest)
    dump(a.output/'setup-eval-only.json',dict(evaluation_only=True,spawns=plan['spawns']))
    # Static labels remain in evaluator artifact, never controller arguments.
    dump(a.output/'static-map-eval-only.json',scene.config['static_map'])
    if a.preflight:
        dump(a.output/'preflight.json',dict(accepted=True,cpu_physics_steps=0,mjwarp_physics_steps=0,memory_implementation=a.implementation,noslip_iterations=int(m.opt.noslip_iterations),source_sha=q['source_sha']))
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
    applied=np.array([[SEARCH[s] for s in servos]],float);relay=np.zeros((1,4),int);drive=DriveParameters()
    color=json.loads(a.colour.read_text());state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',color,option=RELOC16_OPTION)
    camera_stream=CommandCamera(camera_pose=CARRY_OPTION);detector=EgocentricDetector();memory=LandmarkMemory(option=OPTION,options=MemoryOptions(implementation=a.implementation,statistics_library=str(a.rovio_library) if a.rovio_library else None))
    own_prior=CommandPrior(json.loads(a.own_motion.read_text()),option=PRIOR)
    sweep=json.loads(a.sweep.read_text())
    diameter=2*max(float(np.linalg.norm(vertices[:,:2],axis=1).max()) for _,vertices in body_envelopes(SEARCH,'camera_v3'))
    from harness.e2e_rgb_vo import K
    controller=MemoryReturn(sweep_steps=sweep['step_budget'],footprint_diameter_m=diameter,horizontal_half_fov_rad=math.atan(320/K[0,0]),strict_return=a.strict_reacquisition,translated_return=a.translated_return)
    own=[];trace=[];labels=[];commands=[];old=None;previous=None;last_servo=None;next_sensor=0.;ring=deque(maxlen=101)
    status='cap_end';error=None;start=time.monotonic();first30=None;would_stop=[]
    body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    try:
        for tick in range(4*sweep['step_budget']+1):
            t=tick/10
            if (a.output/'SUPERVISOR_STOP.json').exists():status='SUPERVISOR_STOP';break
            qp=wd.qpos.numpy()[0].copy()
            if not np.isfinite(qp).all() or np.any(wd.overflow.numpy()):raise RuntimeError('NONFINITE_OR_CAPACITY')
            images=rc.render();rgb={}
            for rid in ('r1','r2'):
                im=cv2.remap(np.clip(images[rid][0][0],0,255).astype(np.uint8),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                file=a.output/'own-rgb'/f'{rid}-{tick:05d}.jpg';cv2.imwrite(str(file),cv2.cvtColor(im,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
                rgb[rid]=cv2.cvtColor(cv2.imread(str(file)),cv2.COLOR_BGR2RGB)
            servo={s:int(v) for s,v in zip(servos,np.rint(applied[0]))}
            delta=np.asarray(command_delta(previous,.1)) if previous else np.zeros(3);cov=np.diag(motion_variance(delta))
            prior=own_prior.predict(delta,cov,previous,servo,last_servo,.1);delta=np.asarray(prior['delta']);cov=np.asarray(prior['covariance'])
            flow,scan=camera_stream.observe(t,old,rgb['r1'],servo,state)
            increment=np.asarray(flow['delta']) if flow['status']=='measured' else delta
            c=np.asarray(flow['covariance']) if flow['status']=='measured' else cov
            obs=[];diagnostic=None
            if t+1e-8>=next_sensor:
                next_sensor=t+1.
                if not any(x in flow['status'] for x in ('camera_unsettled','servo_change','bootstrap')):
                    obs,diagnostic=detector.observe(rgb['r1'],servo,scan)
            result=memory.step(t,increment,c,obs,observation_tick=diagnostic is not None)
            colour_pixels=colour_component_pixels(rgb['r1'],controller.goal_hue) if controller.goal_hue is not None else None
            before=controller.stage;action=controller.step(t,increment,result['memories'],obs,colour_pixels=colour_pixels)
            if any(m['radius95_m']>m['range_m'] for m in result['memories']) and not any(e['stage']==before for e in would_stop):
                would_stop.append(dict(t=t,stage=before,category='uncertainty',reason='95pct_radius_exceeds_target_range',blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',record_only=True))
            file=a.output/'own-rgb'/f'r1-{tick:05d}.jpg'
            own.append(dict(frame_id=tick,t=t,rgb=str(file.relative_to(a.output)),sha256=sha(file),servo=servo,command_delta=delta.tolist(),command_covariance=cov.tolist()))
            trace.append(dict(t=t,frame_id=tick,stage=before,lk=flow,motion_delta=increment.tolist(),motion_covariance=c.tolist(),observations=obs,detector=diagnostic,memory=result,action=action,command_motion_source=prior['source'],colour_component_pixels=colour_pixels))
            # EVALUATION ONLY. Its values never enter step()/memory.step().
            w,x,y,z=qp[adr+3:adr+7];yaw=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
            labels.append(dict(t=t,frame_id=tick,pose=[float(qp[adr]),float(qp[adr+1]),yaw]));ring.append(tick)
            old=rgb['r1'];last_servo=servo
            if tick==300:first30=(time.monotonic()-start)/30.
            if controller.done:
                status='RGB_SIGNATURE_REACQUIRED_EVAL_PENDING' if controller.events[-1]['reason']=='rgb_signature_reacquired' else 'cap_end';break
            if action[2]:
                # Exact prior signature: +turn .027857142857s on R2, never a
                # gain/extrapolation to .1s or mirrored negative rotation.
                wheels=own_prior.calibration['wheels'];duration=own_prior.calibration['duration_s']
            else:wheels,duration=duty(action)
            cmd=dict(t=t,wheels=wheels,duration_s=duration,pwm=SEARCH)
            commands.append(cmd);previous=cmd
            values,cmd_state=control_tape([dict(ctrl=ctrl[0],wheels=wheels,deadlines=[t+v if v else -1 for v in duration],applied=applied[0],target=[SEARCH[s] for s in servos],servo_active=[False]*5,now=t,servo_time=t)],relay,dt=float(m.opt.timestep),steps=round(.1/m.opt.timestep),lookup=lookup,wheel_ids=wheel_ids,servo_ids=servo_ids,start_fraction=drive.start_fraction,kinetic_fraction=drive.kinetic_fraction,torque_cap_nm=drive.torque_cap_nm)
            applied=cmd_state['applied'];relay=cmd_state['relay'];wp.copy(tape,wp.array(values,dtype=float));step_index.zero_();wp.capture_launch(cap.graph)
            if tick%100==0:
                progress=dict(t=t,stage=controller.stage,memories=len(result['memories']),source_sha=q['source_sha'],wall_s=time.monotonic()-start)
                dump(a.output/'progress.json',progress);print(json.dumps(progress),flush=True)
    except BaseException as exc:
        error=repr(exc);status='HOST_ERROR';raise
    finally:
        dump(a.output/'own.json',dict(frames=own));dump(a.output/'online-trajectory.json',trace);dump(a.output/'eval-only.json',dict(evaluation_only=True,frames=labels));dump(a.output/'commands.json',commands)
        dump(a.output/'events.json',controller.events+would_stop);dump(a.output/'llm-input-example.json',controller.context(memory.snapshot(trace[-1]['t']) if trace else []))
        dump(a.output/'summary.json',dict(status=status,error=error,source_sha=q['source_sha'],frames=len(own),sim_s=(len(own)-1)/10,wall_s=time.monotonic()-start,
            physical_success=False,actual_return_reacquisition_rate=None,student_success=False,llm_success=False,model_calls=0,
            memory_implementation=a.implementation,noslip_iterations=int(m.opt.noslip_iterations),gpu_noslip_iterations=int(wm.opt.noslip_iterations),cpu_physics_steps=0,
            strict_reacquisition=a.strict_reacquisition,translated_return=a.translated_return,own_return_path_m=controller.return_path,
            static_map_control=0,spawn_control=0,truth_control=0,top_camera_frames=0,held_world_reads=0,initial_prior='none',
            terminal_ring=dict(hz=10,indices=list(ring),bytes=sum((a.output/'own-rgb'/f'{rid}-{i:05d}.jpg').stat().st_size for rid in ('r1','r2') for i in ring)),
            first30_wall_sim=first30,work_cap=dict(phase_steps=sweep['step_budget'],total_steps=4*sweep['step_budget'],wall_cap=None),
            geometric_departure_distance_floor_m=diameter,dev_light=True,would_stop=would_stop,rejection_table=str(a.output/'rejection_table.json')))
        reasons={}
        for e in controller.events+would_stop:reasons[e['reason']]=reasons.get(e['reason'],0)+1
        gates=[];left=1
        for gate,passed in [('rgb_recorded',bool(own)),('visual_zone_remembered',controller.goal is not None),('departed',controller.departed),('rgb_signature_reacquired',status=='RGB_SIGNATURE_REACQUIRED_EVAL_PENDING')]:
            passed=left*bool(passed);gates.append(dict(stage=gate,input_n=left,cumulative_pass_n=passed,rejected_n=left-passed));left=passed
        dump(a.output/'rejection_table.json',dict(unit='recording',funnel=gates,reasons=reasons,raw=str(a.output),reproduction=sys.argv,blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured'))
        dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})
        dump(a.output/'EXIT',dict(status=status,error=error))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true')
    p.add_argument('--implementation',choices=['legacy_v1','rovio_local_v1','rovio_object_gnn_v1'],default='legacy_v1')
    p.add_argument('--rovio-library',type=Path)
    p.add_argument('--lease-name',choices=['egomem1','egomem2'],default='egomem1')
    p.add_argument('--preflight',action='store_true')
    p.add_argument('--strict-reacquisition',action='store_true',help='default off; outward normal departure + actual color disappearance before memory-facing reacquisition')
    p.add_argument('--translated-return',action='store_true',help='default off; require one robot envelope diameter of own-motion translation during return before accepting RGB reacquisition')
    for key in ('queue','renderer','legacy','setup','colour','own-motion','sweep','output'):p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
