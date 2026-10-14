"""Finite pair release teacher run on VM3 (success measurement). Weld OFF.

Prefix: the unchanged grasp teacher (observable_v2) from grasp stations next
to the beam reaches a 1 s joint hold; prefix failures are counted separately
and never as release outcomes. Then the visible_only release teacher
(sim/grasp_act_release_teacher.py) shifts, lowers, opens in sync via code
GO/ACK, and backs off. Truth is used here only to gate what each own camera
currently shows and for the separate evaluation record.
Training RGB recording is OFF (success first, then recording; user 10/14).
"""
from __future__ import annotations
import argparse,base64,io,json,math,os,platform,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from harness.grasp_act_contract import SERVOS,command
from scripts.run_grasp_act_teacher import write,apply,snapshot,compress_logs

SUCCESS={'settle_s':2.,'on_floor_z_m':.05,'speed_m_s':.01,'tilt_deg':3.,'open_pwm':1900,'clear_m':.04}
DELIVERY_WAIT_S=4.


def zone_probes(rect,z):
    cx,cy,hx,hy=rect;inset=.012
    edges={'south':[(cx-hx+inset+(2*hx-2*inset)*k/10,cy-hy+inset,z) for k in range(11)],
           'north':[(cx-hx+inset+(2*hx-2*inset)*k/10,cy+hy-inset,z) for k in range(11)],
           'west':[(cx-hx+inset,cy-hy+inset+(2*hy-2*inset)*k/14,z) for k in range(15)],
           'east':[(cx+hx-inset,cy-hy+inset+(2*hy-2*inset)*k/14,z) for k in range(15)]}
    interior=[(cx+hx*(-.85+1.7*i/4),cy+hy*(-.92+1.84*j/10),z) for i in range(5) for j in range(11)]
    return edges,interior


class Eyes:
    """Evaluation owner: which points each own camera shows now (FOV, fisheye, mj_ray)."""
    def __init__(self,band,zone_gid):
        self.b=band;self.zone=zone_gid
    def visible(self,data,rid,point,*,target=None):
        import cv2,mujoco,numpy as np
        b=self.b;cid=b.cameras[rid];point=np.asarray(point,dtype=float)
        p=((point-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
        if p[2]<=b.near:return False
        uv=p[:2]/p[2]*np.diag(b.K)[:2]+b.K[:2,2]
        raw,_=cv2.fisheye.projectPoints(p.reshape(1,1,3),np.zeros(3),np.zeros(3),b.K,b.D)
        if not (0<=uv[0]<640 and 0<=uv[1]<480 and 0<=raw[0,0,0]<640 and 0<=raw[0,0,1]<480):return False
        delta=point-data.cam_xpos[cid];dist=float(np.linalg.norm(delta));direction=delta/dist
        skip=b.near*dist/p[2];origin=data.cam_xpos[cid]+skip*direction;hit=np.array([-1],dtype=np.int32)
        ray=mujoco.mj_ray(b.model,data,origin,direction,b.groups,True,-1,hit)
        if target is not None:return int(hit[0])==target and abs(ray-(dist-skip))<.004
        return hit[0]<0 or ray>=dist-skip-.006


def own_end_world(world,inst,end):
    import numpy as np
    b=world.data.body(inst.body);rot=b.xmat.reshape(3,3)
    return b.xpos+rot@np.array([-.30 if end=='teal' else .30,0.,0.])


def run(plan,out,*,cap_s=90.,prefix_cap_s=35.,own_pose_source='commands'):
    if platform.system()=='Darwin':raise RuntimeError('Mac physics/render disabled; use VM3')
    import numpy as np
    from PIL import Image
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_teacher import GraspTeacher
    from sim.grasp_act_release_teacher import (ReleaseTeacher,PairReleaseCode,QuantizedWheels,BACKOFF_M,
        LOWER_Z_M,RAISE_Z_M,FOLDED_BACKOFF,WHEEL)
    from sim.visible_belief import relative,AXIAL_M_PER_S_AT_035
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from sim.grasp_act_port import ContinuousActPort
    from sim.s2_realism_camera_binding import bind_camera
    from sim.zone_cargo import place,CargoInstance
    from harness.static_keepouts import keepout_rects
    from harness.zone_scenario_feasibility import landing_fits
    from scripts.audit_grasp_act_visibility import BandVisibility
    out.mkdir(parents=True,exist_ok=False);write(out/'plan.json',plan)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):raise RuntimeError('committed source required')
    write(out/'RUN_META.json',{'class':'dev','pr':484,'branch':'claude/grasp-act-release','sha':sha,'batch':plan['batch']})
    report={'status':'running','source_sha':sha,'teacher':'release_visible_only_v1','own_pose_source':own_pose_source,
        'weld':'off','recording_mode':'success_measurement','student_execution':False,'success_rule':SUCCESS,
        'loadavg_at_start':os.getloadavg(),'release_success':None,'prefix_held':None}
    write(out/'result.json',report);world=None;start=time.monotonic();streams=[];origin=0.
    try:
        os.environ['UGRP_SIM_OBSERVER_WIDTH']='320';os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
        scene=make_scene(plan)
        world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=320,height=240,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        for controller in world.controllers.values():bind_camera(controller)
        scene.setup(world)
        place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
        (out/'scene.xml').write_text(world.scene_xml);write(out/'scene.json',scene.manifest)
        static=scene.config['static_map'];zone=static['regions'][plan['destination_region']]
        rect=(*zone['center_m'],*zone['half_extents_m'])
        roles=plan['roles'];ports={rid:ContinuousActPort(world,rid,allow_reverse=True,allow_mecanum=True) for rid in roles}
        wheels={rid:QuantizedWheels(port) for rid,port in ports.items()}
        for rid,port in ports.items():port.apply({'kind':'look','pan_pulse':plan['initial_pan'][rid]},float(world.data.time))
        def advance(target):
            while float(world.data.time)<target-1e-8:
                now=float(world.data.time)
                if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                for rid,port in ports.items():port.tick(now);wheels[rid].tick(now)
                world._physics_step_for(world.robot('r1'))
        advance(float(world.data.time)+.5)
        origin=float(world.data.time);inst=next(x for x in scene.cargo if x.item_id=='beam_1')
        band=BandVisibility(world.model);eyes=Eyes(band,world.model.geom('zone_'+plan['destination_region']).id)
        edges,interior=zone_probes(rect,.0012)
        object_bodies={c.item_id:c.body for c in scene.cargo if c.item_id!='beam_1'}
        object_bodies.update({i:c['body_name'] for i,c in scene.config['setup_only']['objects'].items()})
        ev=(out/'eval-only.jsonl').open('w');streams.append(ev)
        labels={rid:(out/f'teacher-{rid}.jsonl').open('w') for rid in roles};streams+=labels.values()
        (out/'eval-overview').mkdir()
        for rid in roles:(out/'eval-own'/rid).mkdir(parents=True)
        def frames(i,tag):
            at=time.monotonic();overview=Image.new('RGB',(640,480))
            for k,camera in enumerate(static['top_cameras'][:4]):
                f=Image.open(io.BytesIO(world.render_team_jpeg(camera=camera['name'])))
                overview.paste(f.resize((320,240)),((k%2)*320,(k//2)*240))
            overview.save(out/'eval-overview'/f'{i:06d}-{tag}.jpg',quality=86)
            for rid in roles:
                jpg=base64.b64decode(ports[rid].capture()['image'])
                Image.open(io.BytesIO(jpg)).resize((320,240)).save(out/'eval-own'/rid/f'{i:06d}-{tag}.jpg',quality=86)
            timings['rgb']+=time.monotonic()-at
        timings={'rgb':0.,'eyes':0.}
        # ---------------- prefix: unchanged grasp teacher ----------------
        teachers={};previous={}
        for rid,end in roles.items():
            pwm={str(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            previous[rid]=command({'t':origin,'drive':[0.,0.,0.],'duration_s':0.,'pwm':pwm})
            teachers[rid]=GraspTeacher(rid,end,pwm,bounds=static['bounds_m'],rects=keepout_rects(static),profile='observable_v2')
        i=0;both_since=None;held=None
        while float(world.data.time)-origin<prefix_cap_s:
            now=float(world.data.time);truth=snapshot(world,inst,roles,scene)
            truth['visibility']={rid:band.measure(world.data,rid,end) for rid,end in roles.items()}
            for rid in roles:
                truth['visibility'][rid]['objects']=[k for k,b in object_bodies.items() if band.body_visible(world.data,rid,b)]
                truth['visibility'][rid]['peers']=[p for p in ('r1','r2','r3') if p!=rid and band.body_visible(world.data,rid,p+'__robot')]
            if i%10==0:frames(i,'prefix')
            ok=all(min(truth['contacts'][rid])>=.5 for rid in roles) and truth['beam']['min_z']>=.012
            both_since=(now if both_since is None else both_since) if ok else None
            if all(t.outcome=='success' for t in teachers.values()) and both_since is not None and now-both_since>=1.:held=now;break
            if any(t.outcome not in (None,'success') for t in teachers.values()):break
            permit=all(x.phase in ('ready','pick','verify','done') for x in teachers.values())
            permit=permit and all(x.phase!='ready' or truth['visibility'][rid]['visible_probes']>=3 for rid,x in teachers.items())
            for rid,t in teachers.items():
                clean,_=t.step(truth,now,permit_pick=permit);apply(ports[rid],clean,now,previous[rid]);previous[rid]=clean
            i+=1;advance(origin+i*.1)
        report['prefix_held']=held is not None
        report['prefix']={'held_sim_s':None if held is None else held-origin,'outcomes':{r:t.outcome for r,t in teachers.items()}}
        if held is None:
            report.update(status='complete',release_success=None,release_outcome='prefix_not_held');return report
        # ---------------- release: visible_only teacher ----------------
        for port in ports.values():port.stop()
        rel={}
        for rid,end in roles.items():
            pose=world.robot(rid).base_xyz();yaw=float(world.robot(rid).base_rpy()[2])
            err=plan['handoff_pose_error'][rid] if own_pose_source=='commands' else [0.,0.,0.]   # frozen map-code own-pose error
            estimate=[float(pose[0])+err[0],float(pose[1])+err[1],yaw+err[2]]
            pwm={int(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            rel[rid]=ReleaseTeacher(rid,end,pwm,handoff_pose_estimate=estimate,zone_rect=rect,own_pose_source=own_pose_source)
        code=PairReleaseCode(tuple(roles));release_t0=float(world.data.time)
        state={'phase':'look','since':release_t0,'plan':{},'arm':{},'go_at':None,'choice':None}
        report['release_start']={'beam_to_zone_center_m':float(math.dist(world.data.body(inst.body).xpos[:2],rect[:2])),
            'own_end_margin_true_m':{}}
        def observe(rid,now):
            at=time.monotonic();data=world.data
            pose=[*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])]
            obs={'edges':{},'interior':[]}
            for side,pts in edges.items():
                seen=[p for p in pts if eyes.visible(data,rid,p,target=eyes.zone)]
                if len(seen)>=2:
                    mid=np.mean(np.array(seen),axis=0)
                    normal={'south':math.pi/2,'north':-math.pi/2,'west':0.,'east':math.pi}[side]
                    point=(mid[0],mid[1]) if side in ('south','north') else (mid[0],mid[1])
                    obs['edges'][side]=relative(pose,point,normal)
            obs['interior']=[relative(pose,p[:2])[:2] for p in interior if eyes.visible(data,rid,p,target=eyes.zone)]
            e=own_end_world(world,inst,roles[rid])
            ring=[(e[0]+.06*math.cos(a),e[1]+.06*math.sin(a),.0012) for a in np.linspace(0,2*math.pi,6,endpoint=False)]
            obs['end_area_visible']=sum(eyes.visible(data,rid,p) for p in ring)>=3
            obs['own_band_visible']=band.measure(data,rid,roles[rid])['visible_probes']>=3
            obs['partner_visible']=any(band.body_visible(data,rid,p+'__robot') for p in roles if p!=rid)
            timings['eyes']+=time.monotonic()-at
            return obs
        def go_ready(tag,now):
            code.deliver(now)
            return code.ready(tag,state['since'])
        def post(tag,now):
            for rid,t in rel.items():code.post(rid,{**(t.last_report or {}),'phase':tag},now)
        k=0;outcome=None;steps=0;done_at=None
        while float(world.data.time)-origin<cap_s:
            now=float(world.data.time);tick_t=now
            for rid,t in rel.items():
                obs=observe(rid,now);t.phase=state['phase'];t.perceive(obs,now)
            ph=state['phase'];age=now-state['since']
            if ph=='look' and age>=.6:
                for t in rel.values():t.report(now)
                post('look',now);state.update(phase='await_look',since=now)
            elif ph=='await_look' and go_ready('look',now):
                choice=code.decide(now);state['choice']=choice
                if choice['action']=='lower':
                    for rid,t in rel.items():state['arm'][rid]=t.arm_waypoints(LOWER_Z_M,8)
                    state.update(phase='lower',since=now+.2,go_at=now+.2,next_arm=now+.2)
                else:
                    steps+=1
                    if steps>20:outcome='release_step_cap';break
                    state['plan']={rid:t.shift_plan(choice['shift_m'],1. if rid==tuple(roles)[0] else -1.) for rid,t in rel.items()}
                    state.update(phase='shift',since=now+.2,go_at=now+.2)
            elif ph=='shift' and now>=state['go_at']-1e-9:
                busy=False
                for rid,p in state['plan'].items():
                    if p:
                        w,d=p.pop(0);wheels[rid].command(w,d,now);busy=True
                if not busy:state.update(phase='look',since=now)
            elif ph in ('lower','raise') and now>=state['go_at']-1e-9:
                if now>=state['next_arm']-1e-9 and any(state['arm'].values()):
                    for rid,t in rel.items():
                        if not state['arm'][rid]:continue
                        pose=state['arm'][rid].pop(0)
                        for sid,v in pose.items():
                            if t.pwm[sid]!=v:
                                ports[rid].apply({'kind':'look','pan_pulse':v} if sid==6 else {'kind':'arm','servo_id':sid,'pulse':v},now);t.pwm[sid]=v
                    state['next_arm']=now+.2;state['arm_last']=now
                busy=any(state['arm'].values())
                if not busy and now-state.get('arm_last',now)>=.6:
                    if ph=='lower':
                        for t in rel.values():t.last_report={'kind':'lowered'}
                        post('lowered',now);state.update(phase='await_open',since=now)
                    else:
                        for rid,t in rel.items():state['plan'][rid]=t.shift_plan(BACKOFF_M,-1.)
                        state.update(phase='back_off',since=now,go_at=now)
            elif ph=='await_open' and go_ready('lowered',now):
                state.update(phase='open',since=now+.2,go_at=now+.2)
            elif ph=='open' and now>=state['go_at']-1e-9:
                if not state.get('opened'):
                    for rid,t in rel.items():ports[rid].apply({'kind':'arm','servo_id':1,'pulse':2000},now);t.pwm[1]=2000
                    state['opened']=True
                if now-state['go_at']>=1.2:
                    for rid,t in rel.items():state['arm'][rid]=t.arm_waypoints(RAISE_Z_M,3)
                    state.update(phase='raise',since=now,go_at=now,next_arm=now)
            elif ph=='back_off':
                busy=False
                for rid,p in state['plan'].items():
                    if p:
                        w,d=p.pop(0);wheels[rid].command(w,d,now);busy=True
                if not busy:
                    for rid,t in rel.items():
                        for s,v in FOLDED_BACKOFF.items():ports[rid].apply({'kind':'arm','servo_id':s,'pulse':v},now);t.pwm[s]=v
                    state.update(phase='done',since=now);done_at=now
            elif ph=='done' and now-state['since']>=DELIVERY_WAIT_S:
                outcome='teacher_done';break
            # labels: issued wheel levels/durations + arm, release skill
            for rid,t in rel.items():
                labels[rid].write(json.dumps({'t':now,'skill':'release','object_kind':'long_beam','role':roles[rid],
                    'teacher_phase':state['phase'],'wheels':wheels[rid].levels,'wheel_until':wheels[rid].until,
                    'pwm':{str(s):t.pwm[s] for s in SERVOS},'done':state['phase']=='done','report':t.last_report})+'\n')
            if k%10==0:frames(k,'release-'+state['phase'])
            issued={rid:(list(wheels[rid].levels),max([max(0.,min(.1,u-tick_t)) if lv else 0. for lv,u in zip(wheels[rid].levels,wheels[rid].until)]))
                    for rid in rel}
            before={rid:[*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])] for rid in rel}
            k+=1;advance(tick_t+.1)
            for rid,t in rel.items():
                if own_pose_source=='commands':
                    t.dead_reckon(*issued[rid])          # own issued commands only
                else:                                    # comparison toggle: true own motion
                    after=[*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])]
                    dx,dy,da=relative(before[rid],after[:2],after[2]);t.belief.propagate(dx,dy,da)
            truth=snapshot(world,inst,roles,scene)
            ev.write(json.dumps({'t':float(world.data.time),'phase':state['phase'],'beam':truth['beam'],'contacts':truth['contacts'],
                'robots':{r:truth['robots'][r] for r in roles}})+'\n')
        report['release_outcome']=outcome or 'release_timeout'
        # ---------------- evaluation (truth) ----------------
        held_ok=None;t_ok=None;checks=[]
        for j in range(int((SUCCESS['settle_s']+.5)/.1)):
            now=float(world.data.time);b=world.data.body(inst.body);rot=b.xmat.reshape(3,3)
            yaw=math.atan2(rot[1,0],rot[0,0])
            forces=snapshot(world,inst,roles,scene)['contacts']
            fit=landing_fits('long_beam',(float(b.xpos[0]),float(b.xpos[1]),yaw),rect)
            tilt=max(abs(math.degrees(math.asin(max(-1,min(1,rot[2,0]))))),abs(math.degrees(math.atan2(rot[2,1],rot[2,2]))))
            clear=[]
            for rid in roles:
                g=world.data.site(f'{rid}__grip_site').xpos
                a=b.xpos+rot@np.array([-.3,0,0]);c=b.xpos+rot@np.array([.3,0,0]);u=(c-a)/np.linalg.norm(c-a)
                q=a+u*max(0.,min(.6,float((g-a)@u)));clear.append(float(np.linalg.norm(g-q)))
            row={'t':now,'fit':fit,'z':float(b.xpos[2]),'tilt_deg':tilt,'contact_n':{r:list(forces[r]) for r in roles},
                 'grip_to_beam_m':clear,'open_pwm':{r:rel[r].pwm[1] for r in roles},'beam_xy_yaw':[float(b.xpos[0]),float(b.xpos[1]),yaw]}
            checks.append(row);advance(now+.1)
        def good(r,prev):
            speed=0. if prev is None else math.dist(r['beam_xy_yaw'][:2],prev['beam_xy_yaw'][:2])/.1
            return (r['fit'] and r['z']<SUCCESS['on_floor_z_m'] and r['tilt_deg']<SUCCESS['tilt_deg'] and speed<SUCCESS['speed_m_s']
                    and all(max(v)<1e-6 for v in r['contact_n'].values()) and all(p>=SUCCESS['open_pwm'] for p in r['open_pwm'].values())
                    and min(r['grip_to_beam_m'])>=SUCCESS['clear_m'])
        streak=0;best=0
        for idx,r in enumerate(checks):
            streak=streak+1 if good(r,checks[idx-1] if idx else None) else 0;best=max(best,streak)
        last=checks[-1]
        reasons=[n for n,v in (('not_in_zone',not last['fit']),('not_on_floor',last['z']>=SUCCESS['on_floor_z_m']),
            ('tilt',last['tilt_deg']>=SUCCESS['tilt_deg']),('finger_contact',any(max(v)>1e-6 for v in last['contact_n'].values())),
            ('gripper_closed',any(p<SUCCESS['open_pwm'] for p in last['open_pwm'].values())),
            ('gripper_not_clear',min(last['grip_to_beam_m'])<SUCCESS['clear_m'])) if v]
        report.update(release_success=best*.1>=SUCCESS['settle_s']-1e-6 and report['release_outcome']=='teacher_done',
            release_failure_reasons=reasons if reasons else ([] if report['release_outcome']=='teacher_done' else [report['release_outcome']]),
            evaluation_last=last,evaluation_settled_s=best*.1,code_decisions=code.log,shift_steps=steps,
            teachers={rid:t.diagnostic() for rid,t in rel.items()},release_sim_s=(done_at or float(world.data.time))-release_t0,status='complete')
        return report
    except BaseException as error:
        report.update(status='HOST_ERROR' if not isinstance(error,KeyboardInterrupt) else 'interrupted',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        report['wall_s']=time.monotonic()-start;report['sim_s']=None if world is None else float(world.data.time)-origin
        report['loadavg_at_end']=os.getloadavg()
        try:report['timings_s']=timings
        except NameError:pass
        write(out/'result.json',report)
        for s in streams:s.close()
        if world is not None:world.close()
        compress_logs(out)


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,default=0)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cap-s',type=float,default=90.)
    p.add_argument('--own-pose-source',choices=('commands','truth_comparison'),default='commands');a=p.parse_args()
    if not 0<a.cap_s<=180:raise ValueError('finite cap required')
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan,a.out,cap_s=a.cap_s,own_pose_source=a.own_pose_source),ensure_ascii=False,default=str))
if __name__=='__main__':main()
