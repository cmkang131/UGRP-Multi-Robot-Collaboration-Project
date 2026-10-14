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
from harness.grasp_act_contract import SCHEMA,HISTORY,SERVOS,validate_observation,command


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def apply(port,value,now,previous):
    """Zero drive means no new pulse; native lease expires on every substep."""
    if any(value['drive']):
        port.apply(dict(kind='mecanum',**dict(zip(('forward','left','turn'),value['drive'])),duration_s=value['duration_s']),now)
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
            'radius':math.hypot(*c.spec().landing_half_extents_m)}
    for iid,c in scene.config['setup_only']['objects'].items():
        objects[iid]={'xy':list(map(float,world.data.body(c['body_name']).xpos[:2])),
            'radius':math.hypot(*c['half_extents_m'][:2])}
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


def run(plan,out,*,cap_s=120.,noise=False):
    if platform.system()=='Darwin':raise RuntimeError('Mac physics/render disabled; use released VM3')
    import mujoco
    import numpy as np
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_teacher import GraspTeacher
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from sim.s2_align_pulse import FinePulsePort
    from harness.static_keepouts import keepout_rects
    rng=np.random.default_rng(plan['seed']);out.mkdir(parents=True,exist_ok=False)
    write(out/'plan.json',plan)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):
        raise RuntimeError('committed source required')
    write(out/'RUN_META.json',{'class':'dev','pr':484,'branch':'claude/e2e18-grasp-rootcause','sha':sha,'batch':plan['batch']})
    scene=make_scene(plan);world=None;streams=[];start=time.monotonic()
    report={'status':'running','source_sha':sha,'teacher_success_n':0,'teacher_N':len(plan['roles']),
        'joint_held':None,'data_admitted':False,'assignment_source':plan['assignment_source'],
        'student_execution':False,'loadavg_at_start':os.getloadavg(),'noise':'DART-inspired_fixed_pilot' if noise else 'off'}
    write(out/'result.json',report)
    try:
        world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=640,height=480,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        scene.setup(world)
        # All remaining scenario cargo stays present. Only authorized randomized
        # initial placement changes, before the trial clock and any teacher step.
        from sim.zone_cargo import place, CargoInstance
        place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
        (out/'scene.xml').write_text(world.scene_xml);write(out/'scene.json',scene.manifest)
        ports={rid:FinePulsePort(world,rid,allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1') for rid in plan['roles']}
        # Setup-only pan target: no model/camera changes. All later motion is issued commands.
        for rid,port in ports.items():port.apply({'kind':'look','pan_pulse':plan['initial_pan'][rid]},float(world.data.time))
        until=float(world.data.time)+.5
        def advance(target):
            while float(world.data.time)<target-1e-8:
                now=float(world.data.time)
                if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                for port in ports.values():port.tick(now)
                world._physics_step_for(world.robot('r1'))
        advance(until)
        origin=float(world.data.time);previous={};history={};images={};writers={};teachers={}
        for rid,end in plan['roles'].items():
            pwm={str(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            initial=command({'t':origin,'drive':[0.,0.,0.],'duration_s':0.,'pwm':pwm})
            previous[rid]=initial;history[rid]=deque([initial]*HISTORY,maxlen=HISTORY)
            teachers[rid]=GraspTeacher(rid,end,pwm,bounds=scene.config['static_map']['bounds_m'],rects=keepout_rects(scene.config['static_map']))
            (out/'rgb'/rid).mkdir(parents=True)
            student=(out/f'student-{rid}.jsonl').open('w');label=(out/f'teacher-{rid}.jsonl').open('w');streams.extend([student,label]);writers[rid]=(student,label)
        ev=(out/'eval-only.jsonl').open('w');streams.append(ev)
        (out/'eval-overview').mkdir()
        inst=next(x for x in scene.cargo if x.item_id=='beam_1');i=0;both_since=None;all_done_since=None
        while float(world.data.time)-origin < cap_s-1e-8:
            now=float(world.data.time);truth=snapshot(world,inst,plan['roles'],scene);ev.write(json.dumps(truth)+'\n')
            if i % 10 == 0:
                # Reviewer evidence only; never referenced by a student observation.
                (out/'eval-overview'/f'{i:06d}.jpg').write_bytes(world.render_team_jpeg())
                write(out/'progress.json',{'sim_s':now-origin,'wall_s':time.monotonic()-start,
                    'phases':{rid:t.phase for rid,t in teachers.items()},'sample':i})
                for stream in streams:stream.flush()
            both=all(min(truth['contacts'][rid])>=.5 for rid in plan['roles']) and truth['beam']['min_z']>=.012
            both_since=(now if both_since is None else both_since) if both else None
            if len(plan['roles'])==2 and both_since is not None and now-both_since>=1.:report['joint_held']=True
            permit=all(x.phase in ('ready','pick','verify','done') for x in teachers.values())
            for rid,t in teachers.items():
                capture=ports[rid].capture();jpg=base64.b64decode(capture['image']);path=f'rgb/{rid}/{i:06d}.jpg';(out/path).write_bytes(jpg)
                ref={'path':path,'sha256':hashlib.sha256(jpg).hexdigest(),'t':now,'robot_id':rid}
                obs={'schema':SCHEMA,'robot_id':rid,'sample_id':f"{plan['episode_id']}:{i}:{rid}",'t':now,
                    'object_kind':'long_beam','skill':'grasp','role':t.end,'rgb':[images.get(rid,ref),ref],'issued':list(history[rid])}
                validate_observation(obs);images[rid]=ref
                clean,done=t.step(truth,now,permit_pick=permit)
                # Privileged navigation samples remain in raw but are excluded by the data admission loader.
                phase=t.phase;applied=json.loads(json.dumps(clean));perturbed=False
                if noise and phase not in ('done','ready') and rng.random()<.05:
                    perturbed=True
                    if any(applied['drive']):applied.update(drive=[0.,0.,0.],duration_s=0.)
                    else:
                        sid=str(rng.choice([3,4,5]));applied['pwm'][sid]=int(np.clip(applied['pwm'][sid]+rng.normal(0,8),500,2500))
                command(applied)
                label={'sample_id':obs['sample_id'],'object_kind':'long_beam','skill':obs['skill'],'done':done,
                    'terminal_reason':'skill_success' if done else None,'clean_teacher_command':clean,
                    'applied_command':applied,'perturbed':perturbed,'teacher_phase':phase,
                    'local_skill_sample':phase!='approach','assignment_source':plan['assignment_source']}
                writers[rid][0].write(json.dumps(obs)+'\n');writers[rid][1].write(json.dumps(label)+'\n')
                apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
            if all(t.outcome is not None for t in teachers.values()):
                all_done_since=now if all_done_since is None else all_done_since
                if len(teachers)==1 or report['joint_held'] is True or now-all_done_since>=3.:break
            if any(t.outcome not in (None,'success') for t in teachers.values()):break
            i+=1;advance(origin+i*.1)
        for t in teachers.values():
            if t.outcome is None:t.outcome='episode_timeout'
        if len(plan['roles'])==2 and report['joint_held'] is None:report['joint_held']=False
        report.update(status='complete',sim_s=float(world.data.time)-origin,wall_s=time.monotonic()-start,
            teacher_success_n=sum(t.outcome=='success' for t in teachers.values()),
            teachers={rid:t.diagnostic() for rid,t in teachers.items()},samples_per_robot=i+1,
            first_attempt=True,weld='off',loadavg_at_end=os.getloadavg())
        report['data_admitted']=report['teacher_success_n']==report['teacher_N'] and (len(plan['roles'])==1 or report['joint_held'] is True)
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
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cap-s',type=float,default=120.)
    p.add_argument('--noise',action='store_true');a=p.parse_args()
    if not 0<a.cap_s<=180:raise ValueError('finite cap required')
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan,a.out,cap_s=a.cap_s,noise=a.noise),ensure_ascii=False))
if __name__=='__main__':main()
