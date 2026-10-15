"""Default-OFF MJWarp physics owner. Actor sees a JSON own-RGB lane only.

Reuses committed WarpTransport, frozen scene/port and exact ACT15 evaluator.
No teacher object or handcrafted near-field action path is constructed.
Masked reset uses the installed public mujoco_warp.reset_data API.
"""
from __future__ import annotations
import argparse
import base64
from collections import deque
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
FROZEN='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'
INTEGRATION=('qpos','qvel','act','ctrl','qacc_warmstart','qfrc_applied',
             'xfrc_applied','mocap_pos','mocap_quat','eq_active','time')


class Owner:
    def __init__(self, plans, out, *, host, actor_source, compiled_reference, compiled_geometry, training):
        import numpy as np
        import mujoco
        from warp_act_backend import WarpTransport
        spec=importlib.util.spec_from_file_location('rl1b_frozen_score',Path(actor_source)/'harness/grasp_act_rollout.py')
        score_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(score_module)
        self.np,self.mj,self.score_module=np,mujoco,score_module
        self.out,self.training=Path(out),training
        self.out.mkdir(parents=True,exist_ok=False)
        self.plans=list(plans);self.n=len(plans);self.contexts=[]
        self.generations=[0]*self.n;self.start_tick=[0]*self.n
        self.done_tick=[None]*self.n;self.active=np.ones(self.n,bool)
        self.scores=[score_module.SoloScore() for _ in plans]
        self.funnels=[{} for _ in plans];self.first_pass=[{} for _ in plans]
        self.rings=[deque(maxlen=100) for _ in plans]  # recording only:10SIMs at10Hz
        self.trace=[];self.private=[None]*self.n
        self.eval_reads=self.reward_reads=self.critic_reads=0
        self.started=time.monotonic()
        self.tick=0;self.log=(self.out/'evaluation.jsonl').open('x')
        for i,plan in enumerate(plans):self.contexts.append(self.context(plan,i))
        expected_qpos=np.stack([c['world'].data.qpos.copy() for c in self.contexts]).astype(np.float32)
        expected_qvel=np.stack([c['world'].data.qvel.copy() for c in self.contexts]).astype(np.float32)
        sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        self.hooks=WarpTransport(host,sha,'mjwarp_batch_v1',self.out)
        self.hooks.initialize(self.contexts,compiled_reference=compiled_reference,compiled_geometry=compiled_geometry)
        self.origin=self.hooks.origin
        actual_qpos=self.hooks.wd.qpos.numpy();actual_qvel=self.hooks.wd.qvel.numpy()
        model=self.contexts[0]['world'].model
        free=[j for j in range(model.njnt) if int(model.jnt_type[j])==int(mujoco.mjtJoint.mjJNT_FREE)
              and (model.joint(j).name or '').startswith('r1__')]
        if len(free)!=1:raise ValueError('one namespaced r1 free joint required')
        adr=int(model.jnt_qposadr[free[0]])
        translation_equal=bool(np.array_equal(expected_qpos[:,adr:adr+3],actual_qpos[:,adr:adr+3]))
        audit=dict(r1_translation_cast_match=translation_equal,
            qpos_cast_match=bool(np.array_equal(expected_qpos,actual_qpos)),
            qvel_cast_match=bool(np.array_equal(expected_qvel,actual_qvel)),
            max_qpos_difference=float(np.max(np.abs(expected_qpos-actual_qpos))),
            distinct_expected_translations=len({r.tobytes() for r in expected_qpos[:,adr:adr+3]}),
            actual_translations=actual_qpos[:,adr:adr+3].tolist(),
            first_rgb_sha256=[hashlib.sha256(j).hexdigest() for j in self.hooks.rgb])
        (self.out/'initial-state-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
        if not translation_equal:raise RuntimeError('per-world initial translations were not preserved')
        self.trace.append(self.hooks.wd.qpos.numpy().copy())
        self.initial=[self.initial_command(i) for i in range(self.n)]
        self.current=[self.observe(i) for i in range(self.n)]
        self.commands=(self.out/'commands.jsonl').open('x')
        for i in range(self.n):self.measure(i,sample=True)
        (self.out/'RUN_META.json').write_text(json.dumps(dict(**{'class':'dev'},task='rl1b',sha=sha,
            branch='claude/rl-act',pr=530,backend='mjwarp',training=training,
            scene='ACT15 frozen6f floor_light_v1; separate from scene-v5 ACT16w',
            shared_scene_seed_v1=plans[0].get('shared_scene_seed_v1')),indent=2)+'\n')

    def context(self, plan, i):
        from sim.grasp_act_scene import make_scene
        from sim.masterpi_drive_friction_v7 import build_world,PROFILE
        from sim.s2_realism_camera_binding import bind_camera
        from sim.grasp_act_port import DutyActPort
        np=self.np
        if (plan['scenario_id']!='s1_normal_mixed_v4' or plan['kind']!='cyan'
                or plan['item_id']!='cyan_1' or plan['robot_id']!='r1'):
            raise ValueError('rl1b short same-model cohort is S1 cyan_1 r1 only')
        scene=make_scene({**plan,'end_color_scene':'off'})
        # Exact frozen ACT15 reset: sampled poses override scene defaults.
        scene.config['setup_only']['spawns'].update(plan['spawns'])
        world=build_world(scene,drive_profile=PROFILE,seed=plan.get('shared_scene_seed_v1',plan['seed']),width=640,height=480,
            render=False,warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,
            roller_collision='mesh',idle_robot_contacts='off')
        for controller in world.controllers.values():bind_camera(controller)
        scene.setup(world)
        port=DutyActPort(world,'r1',allow_reverse=True,allow_mecanum=True)
        name=scene.config['setup_only']['objects'][plan['item_id']]['body_name']
        body=world.model.body(name).id
        gids=[g for g in range(world.model.ngeom) if world.model.geom_bodyid[g]==body and world.model.geom_contype[g]]
        if len(gids)!=1 or gids[0]==0:raise ValueError('one nonzero box collision geom required')
        fingers={world.model.geom('r1__'+s+'_finger').id:j for j,s in enumerate(('left','right'))}
        folder=self.out/f'world-{i:03d}'
        if self.generations[i]:folder=folder/f'reset-{self.generations[i]:03d}'
        folder.mkdir(parents=True,exist_ok=False)
        (folder/'scene.xml').write_text(world.scene_xml)
        (folder/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        from scripts.audit_grasp_act_visibility import BandVisibility
        from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
        eyes=object.__new__(BandVisibility)
        eyes.np=np;eyes.model=world.model;eyes.K=scaled_camera_matrix(640,480);eyes.D=np.array(CAMERA_FISHEYE_D)
        eyes.groups=np.array([1,1,1,1,0,0],dtype=np.uint8)
        eyes.near=float(world.model.vis.map.znear*world.model.stat.extent)
        eyes.cameras={'r1':world.model.camera('r1__robot_cam').id};eyes.body_gids={}
        return dict(world=world,port=port,gids=gids,finger_ids=fingers,body_name=name,body=body,
                    eyes=eyes,folder=folder)

    def initial_command(self,i):
        p=self.contexts[i]['port']
        return dict(t=self.origin+self.tick*.1,wheels=[0.]*4,duration_s=[0.]*4,
                    pwm={str(s):int(p._servo_pulses[s]) for s in (1,3,4,5,6)})

    def observe(self,i):
        jpeg=self.hooks.rgb[i];now=self.origin+self.tick*.1
        self.rings[i].append((now,jpeg))
        return dict(t=now,jpeg=base64.b64encode(jpeg).decode(),sha256=hashlib.sha256(jpeg).hexdigest())

    def centre(self,ctx):
        # Training-only annotation, using the EXISTING7-probe visibility/ray
        # convention from frozen BandVisibility. No new recognition threshold.
        import cv2
        np=self.np;w=ctx['world'];eyes=ctx['eyes'];d=w.data
        seen,probes=eyes.region_visible(d,'r1',ctx['gids'])
        if not seen:return None
        cid=eyes.cameras['r1'];point=d.geom_xpos[ctx['gids'][0]]
        p=((point-d.cam_xpos[cid])@d.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
        if p[2]<=eyes.near:return None
        uv=p[:2]/p[2]*np.diag(eyes.K)[:2]+eyes.K[:2,2]
        raw,_=cv2.fisheye.projectPoints(p.reshape(1,1,3),np.zeros(3),np.zeros(3),eyes.K,eyes.D)
        x,y=raw.reshape(2)
        if not(0<=uv[0]<640 and 0<=uv[1]<480 and 0<=x<640 and 0<=y<480):return None
        # Pixel-centre normalization with image bounds, not a central box gate.
        return [float(x/320.-1.),float(y/240.-1.)]

    def measure(self,i,*,sample):
        np,mj=self.np,self.mj;ctx=self.contexts[i];w=ctx['world'];m,d=w.model,w.data
        body=ctx['body'];rot=d.xmat[body].reshape(3,3)
        clearance=min(float(d.geom_xpos[g,2]-np.abs(d.geom_xmat[g].reshape(3,3)[2])@m.geom_size[g]) for g in ctx['gids'])
        tilt=math.degrees(math.acos(float(np.clip(rot[2,2],-1,1))))
        forces=self.hooks.contact_forces[i].tolist()
        from harness.visual_arm_v3 import MOUNT_X_M
        base=w.robot('r1').base_xyz();yaw=float(w.robot('r1').base_rpy()[2]);oyaw=math.atan2(rot[1,0],rot[0,0])
        station=d.xpos[body,:2]-(MOUNT_X_M+.152)*np.array([math.cos(oyaw),math.sin(oyaw)])
        distance=float(np.linalg.norm(station-np.asarray(base[:2])))
        angle=math.atan2(math.sin(oyaw-yaw),math.cos(oyaw-yaw))
        ev=dict(clearance=clearance,tilt=tilt,forces=forces,weld=bool(d.eq_active.any()))
        joint=int(m.body_jntadr[body]);dof=int(m.jnt_dofadr[joint])
        if joint<0 or int(m.jnt_type[joint])!=int(mj.mjtJoint.mjJNT_FREE):raise ValueError('free box required')
        speed=float(np.linalg.norm(d.qvel[dof:dof+3]))
        now=self.origin+self.tick*.1
        if sample:self.scores[i].add(now,skill='grasp',linear_speed=speed,**ev)
        score=self.scores[i].record({'grasp':self.done_tick[i]} if self.done_tick[i] is not None else {},with_release=False)
        row=dict(t=now,world=i,seed=self.plans[i]['seed'],generation=self.generations[i],
            elapsed_sim_s=(self.tick-self.start_tick[i])*.1,score_sampled=sample,
            station_error_m=distance,yaw_error_rad=abs(angle),target_object=self.plans[i]['item_id'],
            target_finger_min_gap_m=min(float(mj.mj_geomDistance(m,d,f,g,float(m.stat.extent),None))
                for f in ctx['finger_ids'] for g in ctx['gids']),**ev,**score)
        if sample:
            gates=self.score_module.evaluation_gates(row,stable_lift=score['lift_success'])
            predecessor=True
            for name,passed in gates.items():
                if predecessor and passed:self.funnels[i][name]=True;self.first_pass[i].setdefault(name,row['elapsed_sim_s'])
                predecessor=bool(self.funnels[i].get(name))
        row.update(funnel=dict(self.funnels[i]),first_pass=dict(self.first_pass[i]))
        self.log.write(json.dumps(row,allow_nan=False)+'\n');self.log.flush();self.eval_reads+=1
        if self.training:
            centre=self.centre(ctx)
            self.private[i]=dict(truth=dict(distance_m=distance,alignment_rad=angle,
                target_xy=centre,stable_lift=score['lift_success']),
                critic=[distance,math.sin(angle),math.cos(angle),clearance,tilt/180.,*forces,
                    *d.qpos.tolist(),*d.qvel.tolist(),max(0.,1.-row['elapsed_sim_s']/90.)])
            self.reward_reads+=1;self.critic_reads+=1
        return row

    def integration(self):
        return {name:getattr(self.hooks.wd,name).numpy().copy() for name in INTEGRATION
                if hasattr(self.hooks.wd,name) and hasattr(getattr(self.hooks.wd,name),'numpy')}

    def reset(self,plans,indices):
        np=self.np;h=self.hooks;wp=h.wp
        if (len(plans)!=len(indices) or not indices or len(set(indices))!=len(indices)
                or any(type(i) is not int or not 0<=i<self.n for i in indices)):
            raise ValueError('valid unique reset indices required')
        from warp_act_core import model_key
        before=self.integration();old_private=list(self.private);old_rgb=list(h.rgb)
        for i,plan in zip(indices,plans):
            if self.active[i]:
                row=self.measure(i,sample=False)
                self.trace_result(i,row,cap_end=True,prefix_cap=True,reason='curriculum_collector_reset',student_done=False)
            self.generations[i]+=1
            new=self.context(plan,i);old=self.contexts[i]
            if model_key(new['world'].scene_xml)!=model_key(old['world'].scene_xml):
                new['world'].close();raise ValueError('reset cannot change the frozen static model')
            # Reuse canonical compiled312 geometry; free-joint poses remain new.
            for name in dir(old['world'].model):
                if name.startswith(('geom_','mesh_','bvh_')):
                    value=getattr(old['world'].model,name)
                    if isinstance(value,np.ndarray):getattr(new['world'].model,name)[:]=value
            old['world'].close();self.contexts[i]=new;self.plans[i]=plan
            self.start_tick[i]=self.tick;self.done_tick[i]=None;self.active[i]=True
            self.scores[i]=self.score_module.SoloScore();self.funnels[i]={};self.first_pass[i]={}
            self.rings[i].clear();new['port']._servo_tick_time=self.origin+self.tick*.1
        mask=np.zeros(self.n,bool);mask[list(indices)]=True
        h.mjw.reset_data(h.wm,h.wd,wp.array(mask,dtype=bool))
        for name in INTEGRATION:
            target=getattr(h.wd,name,None)
            if target is None or not hasattr(target,'numpy'):continue
            values=target.numpy()
            if not values.size:continue
            for i in indices:
                value=np.asarray(getattr(self.contexts[i]['world'].data,name))
                values[i]=self.origin+self.tick*.1 if name=='time' else value
            wp.copy(target,wp.array(values,dtype=target.dtype))
        h.relay_state[list(indices)]=0
        h.sync_render(self.contexts)
        # reset_data(when world0 is reset) clears the shared contact count.
        # Preserve non-reset critic snapshots until the next real step rebuilds
        # contacts. This never supplies measurements to the policy lane.
        for i in range(self.n):
            if i not in indices:self.private[i]=old_private[i]
        after=self.integration();untouched=[i for i in range(self.n) if i not in indices]
        equal={name:bool(np.array_equal(before[name][untouched],value[untouched])) for name,value in after.items()}
        rgb_equal=all(old_rgb[i]==h.rgb[i] for i in untouched)
        audit=dict(reset_worlds=list(indices),untouched=untouched,integration_equal=equal,rgb_equal=rgb_equal,
            scope='immediate reset isolation; next-step dynamics still needs paired GPU verification')
        (self.out/f'reset-audit-{self.tick:06d}-{sum(self.generations):04d}.json').write_text(json.dumps(audit,indent=2)+'\n')
        if not all(equal.values()) or not rgb_equal:raise RuntimeError('partial reset changed another world')
        for i in indices:
            self.initial[i]=self.initial_command(i);self.current[i]=self.observe(i)
            self.measure(i,sample=True)
        return self.reply(initial=True)

    def step(self,actions):
        if len(actions)!=self.n:raise ValueError('one command per world required')
        from harness.grasp_act_contract import command as validate
        for i,action in enumerate(actions):
            if set(action)!={'command','done'} or type(action['done']) is not bool:raise ValueError('action whitelist')
            validate(action['command'])
            if not self.active[i]:continue
            now=self.origin+self.tick*.1;value=action['command'];p=self.contexts[i]['port']
            if abs(value['t']-now)>1e-5:raise ValueError('issued clock differs from frozen ACT tolerance')
            if action['done'] and self.done_tick[i] is None:self.done_tick[i]=self.tick
            p._command_expires_at=p._drive_expires_at=None
            p._set_motors(tuple(value['wheels']))
            p._wheel_deadlines=[now+d if d else None for d in value['duration_s']]
            # Exact ACT15: unchanged PWM MUST NOT restart interpolation.
            for servo,pulse in value['pwm'].items():
                s=int(servo)
                if pulse!=self.initial[i]['pwm'][servo]:
                    p.apply(dict(kind='look',pan_pulse=pulse) if s==6 else dict(kind='arm',servo_id=s,pulse=pulse),now)
            self.initial[i]=value
            self.commands.write(json.dumps(dict(world=i,t=now,**action))+'\n')
        inactive=self.np.flatnonzero(~self.active).tolist()
        frozen=self.integration() if inactive else None
        self.hooks.step(self.contexts,self.active);self.tick+=1
        if inactive:
            for name,old in frozen.items():
                target=getattr(self.hooks.wd,name);values=target.numpy()
                if not values.size:continue
                values[inactive]=old[inactive]
                self.hooks.wp.copy(target,self.hooks.wp.array(values,dtype=target.dtype))
            self.hooks.sync_render(self.contexts)
        for i in range(self.n):
            if not self.active[i]:continue
            elapsed=self.tick-self.start_tick[i]
            cap=elapsed>=900  # unchanged ACT15 90SIMs /0.1SIMs
            row=self.measure(i,sample=not cap)
            finished=self.done_tick[i] is not None and self.tick-self.done_tick[i]>=31  # ACT15 settle3.1s
            self.active[i]=not(cap or finished)
            self.current[i]=self.observe(i)
            if not self.active[i]:self.finish_world(i,row,cap=cap,finished=finished)
            if self.tick%5==0:(self.contexts[i]['folder']/f'review-{self.tick:06d}.jpg').write_bytes(self.hooks.rgb[i])
        self.trace.append(self.hooks.wd.qpos.numpy().copy())
        self.commands.flush()
        return self.reply()

    def finish_world(self,i,row,*,cap,finished):
        self.trace_result(i,row,cap_end=cap,student_done=finished)

    def trace_result(self,i,row,**extra):
        folder=self.contexts[i]['folder']
        record=dict(status='complete' if not extra.get('prefix_cap') else 'prefix_cap',**row,**extra,
            command_sequence_complete=bool(extra.get('student_done')),weld='off')
        (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        for j,(at,jpeg) in enumerate(self.rings[i]):
            path=folder/'last10s';path.mkdir(exist_ok=True)
            (path/f'{j:03d}-{at:.3f}.jpg').write_bytes(jpeg)

    def reply(self,*,initial=False):
        result=dict(frames=self.current,terminal=(~self.active).tolist())
        if initial:result['initial']=self.initial
        if self.training:result['training']=self.private
        return result

    def close(self,reason):
        for i in range(self.n):
            if self.active[i]:
                row=self.measure(i,sample=False)
                self.trace_result(i,row,cap_end=True,prefix_cap=True,reason=reason,student_done=False)
        if self.trace:self.np.savez_compressed(self.out/'warp-qpos.npz',qpos=self.np.stack(self.trace),
            sim_t=self.origin+self.np.arange(len(self.trace))*.1)
        self.log.close();self.commands.close()
        report=dict(status=reason,backend='mjwarp',training=self.training,nworld=self.n,ticks=self.tick,
            wall_s=time.monotonic()-self.started,timing=dict(self.hooks.seconds),
            actor_truth_payloads=0,evaluator_reads=self.eval_reads,
            training_privileged_reward_reads=self.reward_reads,training_privileged_critic_reads=self.critic_reads,
            recording_ring_bytes=sum(len(jpg) for ring in self.rings for _,jpg in ring))
        (self.out/'owner-summary.json').write_text(json.dumps(report,indent=2)+'\n')
        for c in self.contexts:c['world'].close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true');p.add_argument('--training',action='store_true')
    for name in ('teacher-source','actor-source','plans','out','compiled-reference','compiled-geometry'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    if not a.enabled or host['instance']!='ugrp-act-l4-gcp2':p.error('explicit gcp2 L4 opt-in required')
    if subprocess.check_output(['git','-C',str(a.teacher_source),'rev-parse','HEAD'],text=True).strip()!=FROZEN:
        p.error('frozen scene/port source required')
    for source in (a.teacher_source,a.actor_source):
        if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no']):
            p.error('clean frozen dependency source required')
    sys.path.insert(0,str(a.teacher_source))
    import os
    # Native compiler logs must not corrupt the public JSON protocol either.
    protocol=os.fdopen(os.dup(1),'w',buffering=1)
    os.dup2(2,1);sys.stdout=sys.stderr
    def send(row):protocol.write(json.dumps(row,allow_nan=False)+'\n');protocol.flush()
    env=None;reason='HOST_ERROR'
    try:
        env=Owner(json.loads(a.plans.read_text())['episodes'],a.out,host=host,actor_source=a.actor_source,
            compiled_reference=a.compiled_reference,compiled_geometry=a.compiled_geometry,training=a.training)
        send(env.reply(initial=True))
        for line in sys.stdin:
            request=json.loads(line)
            if set(request)=={'close'}:reason=str(request['close']);break
            if set(request)=={'actions'}:send(env.step(request['actions']))
            elif set(request)=={'reset','indices'}:send(env.reset(request['reset'],request['indices']))
            else:raise ValueError('owner request whitelist mismatch')
    except BaseException as exc:
        a.out.mkdir(parents=True,exist_ok=True)
        (a.out/'owner-error.json').write_text(json.dumps(dict(status='HOST_ERROR',exception=type(exc).__name__,message=str(exc)),indent=2)+'\n')
        raise
    finally:
        if env is not None:env.close(reason)


if __name__=='__main__':main()
