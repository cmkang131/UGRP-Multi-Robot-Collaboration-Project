"""Finite teacher demonstration on VM3; no LLM/API keys, weld always OFF.

Run only after VM3 release and storage/speed gates. The optional noise is
DART-inspired until its covariance is estimated from a trained student's
residuals. Teacher labels and simulator truth never share the student file.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,math,os,platform,subprocess,sys,time
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from harness.grasp_act_contract import SCHEMA,HISTORY,SERVOS,validate_observation,command,image_history


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def apply(port,value,now,previous):
    """Same continuous actuator path for teacher and student; zero stops wheels."""
    if any(value['drive']):
        port.apply(dict(kind='mecanum',**dict(zip(('forward','left','turn'),value['drive'])),duration_s=value['duration_s']),now)
    else:port.stop()
    for s in SERVOS:
        p=value['pwm'][str(s)]
        if p != previous['pwm'][str(s)]:
            port.apply({'kind':'look','pan_pulse':p} if s==6 else {'kind':'arm','servo_id':s,'pulse':p},now)


def snapshot(world,inst,roles,scene):
    import numpy as np
    from types import SimpleNamespace
    from scripts.cargo_formation_teacher import FormationTeacher
    body=world.data.body(inst.body);rot=body.xmat.reshape(3,3);pos=body.xpos
    yaw=math.atan2(rot[1,0],rot[0,0])
    ends={end:(pos+rot@np.array([x,0.,.024])).tolist() for end,x in (('teal',-.27),('blue',.27))}
    holder=SimpleNamespace(world=world,inst=inst,roles=roles)
    min_z=min(float((world.data.geom(inst.geom(p.name)).xpos +
        world.data.geom(inst.geom(p.name)).xmat.reshape(3,3)@np.array([sx*p.size[0],sy*p.size[1],sz*p.size[2]]))[2])
        for p in inst.spec().parts if p.collision for sx in (-1,1) for sy in (-1,1) for sz in (-1,1))
    objects={}
    for c in scene.cargo:
        b=world.data.body(c.body)
        objects[c.item_id]={'xy':list(map(float,b.xpos[:2])),
            'radius':math.hypot(*c.spec().landing_half_extents_m),
            'top_z_bound_m':max(float(world.data.geom(c.geom(p.name)).xpos[2])+float(world.model.geom_rbound[world.model.geom(c.geom(p.name)).id]) for p in c.spec().parts if p.collision)}
    for iid,c in scene.config['setup_only']['objects'].items():
        objects[iid]={'xy':list(map(float,world.data.body(c['body_name']).xpos[:2])),
            'radius':math.hypot(*c['half_extents_m'][:2]),
            'top_z_bound_m':float(world.data.body(c['body_name']).xpos[2])+math.sqrt(sum(float(x)**2 for x in c['half_extents_m']))}
    return {'objects':objects,'t':float(world.data.time),'beam':{'pose':[float(pos[0]),float(pos[1]),yaw],'ends':ends,
        'qpos':body.xquat.tolist(),'min_z':min_z},'robots':{rid:{'pose':[*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])],
        'xyz':list(map(float,world.robot(rid).base_xyz()))} for rid in ('r1','r2','r3')},
        'contacts':FormationTeacher.finger_forces(holder),'joints':world.data.qpos.tolist()}


def compress_logs(out):
    manifest={}
    for path in sorted(out.rglob('*')):
        if not path.is_file():continue
        b=path.read_bytes();entry={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
        if path.suffix in ('.json','.jsonl') and len(b)>65536:
            z=subprocess.check_output(['zstd','-q','-c'],input=b)
            assert subprocess.check_output(['zstd','-qdc'],input=z)==b
            target=Path(str(path)+'.zst');target.write_bytes(z);path.unlink();path=target
            entry={'sha256':hashlib.sha256(z).hexdigest(),'bytes':len(z),'decoded_sha256':entry['sha256']}
        manifest[str(path.relative_to(out))]=entry
    write(out/'manifest.json',manifest)
    path=out/'manifest.json';raw=path.read_bytes()
    if len(raw)>65536:
        compressed=subprocess.check_output(['zstd','-q','-c'],input=raw)
        assert subprocess.check_output(['zstd','-qdc'],input=compressed)==raw
        target=out/'manifest.json.zst';target.write_bytes(compressed);path.unlink()
        write(out/'manifest-compression.json',{'path':target.name,'bytes':len(compressed),
            'sha256':hashlib.sha256(compressed).hexdigest(),'decoded_sha256':hashlib.sha256(raw).hexdigest()})


def run(plan,out,*,cap_s=60.,noise=False,record_training=False,probe=False,teacher_profile="legacy"):
    if platform.system()=='Darwin':raise RuntimeError('Mac physics/render disabled; use released VM3')
    import mujoco
    import numpy as np
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_teacher import GraspTeacher
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from sim.grasp_act_port import ContinuousActPort
    from harness.static_keepouts import keepout_rects
    rng=np.random.default_rng(plan['seed']);out.mkdir(parents=True,exist_ok=False)
    write(out/'plan.json',plan)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):
        raise RuntimeError('committed source required')
    write(out/'RUN_META.json',{'class':'dev','pr':484,'branch':'claude/e2e18-grasp-rootcause','sha':sha,'batch':plan['batch']})
    scene=make_scene(plan);world=None;streams=[];start=time.monotonic()
    timings={k:0. for k in ('physics','rgb','evaluation','teacher','io')}
    report={'status':'running','source_sha':sha,'teacher_success_n':0,'teacher_N':len(plan['roles']),
        'joint_held':None,'data_admitted':False,'assignment_source':plan['assignment_source'],
        'student_execution':False,'recording_mode':'training' if record_training else 'success_measurement',
        'physical_success':False,'teacher_profile':teacher_profile,'action_contract':SCHEMA,'loadavg_at_start':os.getloadavg(),'noise':'DART-inspired_fixed_pilot' if noise else 'off'}
    write(out/'result.json',report)
    try:
        os.environ['UGRP_SIM_OBSERVER_WIDTH']='320'
        os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
        world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=640 if record_training else 320,height=480 if record_training else 240,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        scene.setup(world)
        # All remaining scenario cargo stays present. Only authorized randomized
        # initial placement changes, before the trial clock and any teacher step.
        from sim.zone_cargo import place, CargoInstance
        place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
        (out/'scene.xml').write_text(world.scene_xml);write(out/'scene.json',scene.manifest)
        report['observation_sampling']={'rgb_size':[640,480] if record_training else None,'rgb_hz':10 if record_training else 0,
            'review_tile_size':[320,240],'review_cameras':'four authored static top views','review_hz':1,'control_hz':10,
            'aspect_ratio_unchanged':True,'camera_fov_and_pose_unchanged':True}
        ports={rid:ContinuousActPort(world,rid,allow_reverse=True,allow_mecanum=True) for rid in plan['roles']}
        # Setup-only pan target: no model/camera changes. All later motion is issued commands.
        for rid,port in ports.items():port.apply({'kind':'look','pan_pulse':plan['initial_pan'][rid]},float(world.data.time))
        until=float(world.data.time)+.5
        def advance(target):
            at=time.monotonic()
            while float(world.data.time)<target-1e-8:
                now=float(world.data.time)
                if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                for port in ports.values():port.tick(now)
                world._physics_step_for(world.robot('r1'))
            timings['physics']+=time.monotonic()-at
        advance(until)
        origin=float(world.data.time);previous={};history={};images={};writers={};teachers={}
        from scripts.audit_grasp_act_visibility import BandVisibility
        visibility=BandVisibility(world.model)
        object_bodies={c.item_id:c.body for c in scene.cargo}
        object_bodies.update({i:c['body_name'] for i,c in scene.config['setup_only']['objects'].items()})
        write(out/'camera-runtime.json',{'scope':'evaluation-only; actual runtime values, not XML assumptions',
            'cameras':{rid:{'pos':world.model.cam_pos[cid].tolist(),'quat':world.model.cam_quat[cid].tolist(),
                'intrinsic':world.model.cam_intrinsic[cid].tolist(),'resolution':world.model.cam_resolution[cid].tolist()}
                for rid,cid in visibility.cameras.items()}})
        for rid,end in plan['roles'].items():
            pwm={str(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            initial=command({'t':origin,'drive':[0.,0.,0.],'duration_s':0.,'pwm':pwm})
            previous[rid]=initial;history[rid]=deque([initial]*HISTORY,maxlen=HISTORY)
            teachers[rid]=GraspTeacher(rid,end,pwm,bounds=scene.config['static_map']['bounds_m'],rects=keepout_rects(scene.config['static_map']),profile=teacher_profile)
            student=None
            if record_training:
                (out/'rgb'/rid).mkdir(parents=True)
                student=(out/f'student-{rid}.jsonl').open('w');streams.append(student)
            label=(out/f'teacher-{rid}.jsonl').open('w');streams.append(label);writers[rid]=(student,label)
        ev=(out/'eval-only.jsonl').open('w');streams.append(ev)
        (out/'eval-overview').mkdir()
        inst=next(x for x in scene.cargo if x.item_id=='beam_1');i=0;written=0;both_since=None;all_done_since=None
        while float(world.data.time)-origin < cap_s-1e-8:
            now=float(world.data.time);at=time.monotonic()
            truth=snapshot(world,inst,plan['roles'],scene)
            truth['visibility']={rid:visibility.measure(world.data,rid,end) for rid,end in plan['roles'].items()}
            if teacher_profile=='observable_v2':
                for rid in plan['roles']:
                    truth['visibility'][rid]['objects']=[iid for iid,b in object_bodies.items() if visibility.body_visible(world.data,rid,b)]
                    truth['visibility'][rid]['peers']=[peer for peer in ('r1','r2','r3') if peer!=rid and visibility.body_visible(world.data,rid,peer+'__robot')]
            ev.write(json.dumps(truth)+'\n')
            timings['evaluation']+=time.monotonic()-at
            if i % 10 == 0:
                # Reviewer evidence only; never referenced by a student observation.
                import io
                from PIL import Image
                at=time.monotonic();overview=Image.new('RGB',(640,480))
                for k,camera in enumerate(scene.config['static_map']['top_cameras']):
                    frame=Image.open(io.BytesIO(world.render_team_jpeg(camera=camera['name'])))
                    overview.paste(frame.resize((320,240)),((k%2)*320,(k//2)*240))
                overview.save(out/'eval-overview'/f'{i:06d}.jpg',quality=86)
                timings['rgb']+=time.monotonic()-at
                write(out/'progress.json',{'sim_s':now-origin,'wall_s':time.monotonic()-start,
                    'phases':{rid:t.phase for rid,t in teachers.items()},'sample':i,'timings_s':timings})
                for stream in streams:stream.flush()
            both=all(min(truth['contacts'][rid])>=.5 for rid in plan['roles']) and truth['beam']['min_z']>=.012
            both_since=(now if both_since is None else both_since) if both else None
            if len(plan['roles'])==2 and both_since is not None and now-both_since>=1.:report['joint_held']=True
            permit=all(x.phase in ('ready','pick','verify','done') for x in teachers.values())
            for rid,t in teachers.items():
                at=time.monotonic()
                sample_id=f"{plan['episode_id']}:{i}:{rid}"
                # Demonstration supervisor supplies the discrete wait command;
                # hidden peer readiness must not change a grasp action label
                # under an identical student instruction.
                skill='wait' if t.phase=='ready' and not permit else 'grasp'
                if record_training:
                    capture=ports[rid].capture();jpg=base64.b64decode(capture['image']);path=f'rgb/{rid}/{i:06d}.jpg';(out/path).write_bytes(jpg)
                    ref={'path':path,'sha256':hashlib.sha256(jpg).hexdigest(),'t':now,'robot_id':rid}
                    images.setdefault(rid,deque(maxlen=HISTORY+1)).append(ref)
                    obs={'schema':SCHEMA,'robot_id':rid,'sample_id':sample_id,'t':now,
                        'object_kind':'long_beam','skill':skill,'role':t.end,'rgb':image_history(list(images[rid]),now),'issued':list(history[rid])}
                    validate_observation(obs)
                    writers[rid][0].write(json.dumps(obs)+'\n')
                timings['rgb']+=time.monotonic()-at
                at=time.monotonic()
                clean,done=t.step(truth,now,permit_pick=permit)
                timings['teacher']+=time.monotonic()-at
                # Privileged navigation samples remain in raw but are excluded by the data admission loader.
                phase=t.phase;applied=json.loads(json.dumps(clean));perturbed=False
                if noise and phase not in ('done','ready') and rng.random()<.05:
                    perturbed=True
                    if any(applied['drive']):applied.update(drive=[0.,0.,0.],duration_s=0.)
                    else:
                        sid=str(rng.choice([3,4,5]));applied['pwm'][sid]=int(np.clip(applied['pwm'][sid]+rng.normal(0,8),500,2500))
                command(applied)
                label={'sample_id':sample_id,'object_kind':'long_beam','skill':skill,'done':done,
                    'terminal_reason':'skill_success' if done else None,'clean_teacher_command':clean,
                    'applied_command':applied,'perturbed':perturbed,'teacher_phase':phase,
                    'local_skill_sample':teacher_profile=='observable_v2' or phase!='approach','assignment_source':plan['assignment_source'],
                    'skill_instruction_source':'demo_privileged_pair_supervisor; student runtime instruction must come from LLM'}
                apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
                label['issued_native_wheels']=list(ports[rid]._motor_commands)
                writers[rid][1].write(json.dumps(label)+'\n')
            written+=1
            if not probe and all(t.outcome is not None for t in teachers.values()):
                all_done_since=now if all_done_since is None else all_done_since
                if len(teachers)==1 or report['joint_held'] is True or now-all_done_since>=3.:break
            if not probe and any(t.outcome not in (None,'success') for t in teachers.values()):break
            i+=1;advance(origin+i*.1)
        for t in teachers.values():
            if t.outcome is None:t.outcome='episode_timeout'
        if len(plan['roles'])==2 and report['joint_held'] is None:report['joint_held']=False
        report.update(status='complete',sim_s=float(world.data.time)-origin,wall_s=time.monotonic()-start,
            teacher_success_n=sum(t.outcome=='success' for t in teachers.values()),
            teachers={rid:t.diagnostic() for rid,t in teachers.items()},samples_per_robot=written,
            first_attempt=True,weld='off',loadavg_at_end=os.getloadavg(),timings_s=timings)
        report['physical_success']=report['teacher_success_n']==report['teacher_N'] and (len(plan['roles'])==1 or report['joint_held'] is True)
        report['data_admitted']=bool(record_training and report['physical_success'])
        report['wall_per_sim']=report['wall_s']/max(.001,report['sim_s'])
        # Pair whole-beam clearance is deliberately a separate, not-yet-evaluated metric.
        write(out/'result.json',report)
    except BaseException as error:
        report.update(status='HOST_ERROR' if not isinstance(error,KeyboardInterrupt) else 'interrupted',error_type=type(error).__name__,error=str(error),wall_s=time.monotonic()-start)
        write(out/'result.json',report);raise
    finally:
        for stream in streams:stream.close()
        if world is not None:world.close()
        compress_logs(out)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,default=0)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cap-s',type=float,default=60.)
    p.add_argument('--noise',action='store_true');p.add_argument('--probe',action='store_true')
    p.add_argument('--teacher-profile',choices=('legacy','pi_geometry_v1','observable_v2'),default='legacy')
    p.add_argument('--record-training',action='store_true');p.add_argument('--teacher-gate',type=Path);a=p.parse_args()
    if a.record_training:
        if a.teacher_gate is None:raise ValueError('verified >=38/40 teacher gate required before recording')
        gate=json.loads(a.teacher_gate.read_text())
        if gate.get('N',0)<40 or gate.get('n',0)/gate['N']<.95 or gate.get('object_kind')!='long_beam':
            raise ValueError('verified >=95% with N>=40 required')
    if not 0<a.cap_s<=180:raise ValueError('finite cap required')
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan,a.out,cap_s=a.cap_s,noise=a.noise,record_training=a.record_training,probe=a.probe,teacher_profile=a.teacher_profile),ensure_ascii=False))
if __name__=='__main__':main()
