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
import argparse,base64,copy,hashlib,io,json,math,os,platform,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from harness.grasp_act_contract_v4 import SERVOS,command   # prefix uses the preserved v4 observable_v2 teacher
from scripts.run_grasp_act_teacher import write,apply,snapshot,compress_logs
from sim.grasp_act_release_teacher import OBSERVE_MODES,REACH_MODES
from sim.release_zone_servo import MODES as PLACEMENT_MODES, OPTION as RGB_CENTER
from sim.release_global_observation import LATERAL_MODES
from sim.release_nbv_observation import MODES as ACTIVE_RECOVERY_MODES
from sim.release_regrasp import MODES as REGRASP_CHECK_MODES
from sim.release_regrasp_recovery import MODES as REGRASP_RECOVERY_MODES
from sim import release14, release15, release16
ZONE_SLOT_MODES=("floor","zone")   # zone: destination slot squares (static map, inside the zone) read as zone
# User 2026-10-14: "빔을 들고 옮길 때에도 빔의 위치를 아나? ... 그럴 때에는 모르게 하는 게 어때".
# hidden_v1: while the own gripper holds the cargo, its world pose never enters teacher/map-code inputs.
HELD_OBJECT_MODES=("visible_v0","hidden_v1")
# setdown_lookaround_v1 (user 2026-10-14 "둘러보기 위해서 아래에 뒀으면, 진짜 좀 둘러봐야 할듯"): after the backoff step the
# robot looks toward static-map landmarks chosen from its own pose estimate (sim/lookaround_localization.py).
LOOKAROUND_MODES=("off","setdown_lookaround_v1","setdown_lookaround_v2","setdown_global_v1")
LOOK_RES=(640,480)          # own camera size for the existing OpenCV localisation modules
ARM_MOVE_BACK_S=1.0         # look arm pose -> gaze pose
POSE_ANCHOR_MODES=('legacy_truth_v0','command_relative_v1')


class CommandPose:
    """Own issued-wheel odometry in an arbitrary start frame, never a map pose."""
    def __init__(self, profile='off'):self.x=[0.,0.,0.];self.profile=profile
    def propagate(self,wheels,seconds):
        from sim.visible_belief import odometry
        dx,dy,da=odometry(wheels,seconds,self.profile);c,s=math.cos(self.x[2]),math.sin(self.x[2])
        self.x=[self.x[0]+c*dx-s*dy,self.x[1]+s*dx+c*dy,self.x[2]+da]


def handoff_estimate(plan,rid,issued,*,pose_anchor,own_pose_source,truth_pose=None):
    """Legacy comparison is explicit; command_relative_v1 never reads plan coordinates."""
    if pose_anchor not in POSE_ANCHOR_MODES:raise ValueError(pose_anchor)
    if pose_anchor=='command_relative_v1':
        if own_pose_source!='commands':raise ValueError('command_relative_v1 requires own commands')
        return list(issued.x)
    err=plan['handoff_pose_error'][rid] if own_pose_source=='commands' else [0.,0.,0.]
    return [float(v)+e for v,e in zip(truth_pose,err)]


class HeldAudit:
    """Counts reads of the held cargo's world pose feeding decisions; hidden_v1 refuses them."""
    def __init__(self,mode):
        if mode not in HELD_OBJECT_MODES:raise ValueError(mode)
        self.mode=mode;self.reads={};self.meas={};self.picks=[];self.visibility={};self.blind={};self.longest={};self.last_phase={}
    def measurement(self,phase,kind,visible,count=1):
        """Each truth-derived measurement handed to a teacher, with its own visibility gate re-checked."""
        if not count:return
        row=self.meas.setdefault(phase,{}).setdefault(kind,[0,0]);row[0]+=count;row[1]+=0 if visible else count
    def assigned_end(self,phase,rid,visible,dt=.1):
        """Evaluation-only assigned-end samples, including every non-visible release phase."""
        row=self.visibility.setdefault(rid,{}).setdefault(phase,{'N':0,'visible':0,'blind_s':0.,'max_blind_s':0.})
        if self.last_phase.get(rid)!=phase:row['blind_s']=0.
        self.last_phase[rid]=phase
        row['N']+=1;row['visible']+=bool(visible)
        row['blind_s']=0. if visible else row['blind_s']+dt
        row['max_blind_s']=max(row['max_blind_s'],row['blind_s'])
        # Across phase boundaries, keep the continuous streak as well.
        self.blind[rid]=0. if visible else self.blind.get(rid,0.)+dt
        self.longest[rid]=max(self.longest.get(rid,0.),self.blind[rid])
    def pick(self,phase,rid,now,teacher,*,xy=None):
        if xy is not None:
            self.picks.append({'phase':phase,'robot':rid,'t':now,'source':'commanded_station','xy':list(xy),'age_s':0.})
            return
        item=teacher.belief.get('band',now) or teacher.belief.get('released_band',now)
        self.picks.append({'phase':phase,'robot':rid,'t':now,'source':item['source'],'age_s':now-item['seen_t']})
    def read(self,holding,site):
        if not holding:return
        if self.mode=='hidden_v1':raise RuntimeError(f'HELD_WORLD_READ:{site}')
        self.reads[site]=self.reads.get(site,0)+1
    def record(self):
        return {'held_object':self.mode,'held_world_reads':sum(self.reads.values()),'held_world_reads_by_site':dict(self.reads),
                'invisible_measurements':sum(v[1] for ph in self.meas.values() for v in ph.values()),
                'measurements_by_phase':{ph:{k:{'n':v[0],'invisible':v[1]} for k,v in kinds.items()} for ph,kinds in self.meas.items()},
                'pick_target_uses':self.picks,
                'assigned_end_visibility_by_phase':{rid:{ph:{'N':v['N'],'visible':v['visible'],
                    'visible_fraction':v['visible']/v['N'],'max_blind_s':v['max_blind_s']} for ph,v in phases.items()} for rid,phases in self.visibility.items()},
                'max_assigned_end_blind_s':dict(self.longest),
                'scope':'decision inputs from release start to release complete; truth stays in evaluation-only outputs; '
                        'prefix grasp teacher stops at the held check'}

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
    def __init__(self,band,zone_gid,slot_gids=()):
        self.b=band;self.zone=zone_gid;self.slots=frozenset(int(g) for g in slot_gids)
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
    def classify(self,data,rid,point):
        """None if not visible; 'zone' if the destination colour is what the camera sees there, else 'floor'."""
        import cv2,mujoco,numpy as np
        b=self.b;cid=b.cameras[rid];point=np.asarray(point,dtype=float)
        p=((point-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
        if p[2]<=b.near:return None
        uv=p[:2]/p[2]*np.diag(b.K)[:2]+b.K[:2,2]
        if not (0<=uv[0]<640 and 0<=uv[1]<480):return None
        raw,_=cv2.fisheye.projectPoints(p.reshape(1,1,3),np.zeros(3),np.zeros(3),b.K,b.D)
        if not (0<=raw[0,0,0]<640 and 0<=raw[0,0,1]<480):return None
        delta=point-data.cam_xpos[cid];dist=float(np.linalg.norm(delta));direction=delta/dist
        skip=b.near*dist/p[2];origin=data.cam_xpos[cid]+skip*direction;hit=np.array([-1],dtype=np.int32)
        ray=mujoco.mj_ray(b.model,data,origin,direction,b.groups,True,-1,hit)
        if hit[0]<0 or abs(ray-(dist-skip))>.015:return None      # occluded (e.g. own beam/gripper)
        return 'zone' if int(hit[0])==self.zone or int(hit[0]) in self.slots else 'floor'


def destination_slot_geoms(names,region):
    """Indices of the destination's slot squares (zone_slot_<letter><n>); they lie inside the zone on the static map."""
    letter=region.split('_')[-1];pre='zone_slot_'+letter
    return [i for i,n in enumerate(names) if n and n.startswith(pre) and n[len(pre):].isdigit()]


def position_error(beam_xy_yaw,rect,half_len=.30):
    """Evaluation only: landed beam vs the destination rectangle (axis-aligned, centre cx,cy, half hx,hy)."""
    x,y,yaw=beam_xy_yaw;cx,cy,hx,hy=rect
    long_axis=math.pi/2 if hy>=hx else 0.
    err=(yaw-long_axis+math.pi/2)%math.pi-math.pi/2          # beam has no head/tail
    ends=[(x+k*half_len*math.cos(yaw),y+k*half_len*math.sin(yaw)) for k in (-1,1)]
    margin=min(min(hx-abs(ex-cx),hy-abs(ey-cy)) for ex,ey in ends)
    return {'center_offset_m':[x-cx,y-cy],'center_distance_m':math.hypot(x-cx,y-cy),'yaw_error_deg':math.degrees(err),
            'min_end_margin_m':margin,'zone_long_axis':'y' if hy>=hx else 'x'}


def own_end_world(world,inst,end):
    import numpy as np
    b=world.data.body(inst.body);rot=b.xmat.reshape(3,3)
    return b.xpos+rot@np.array([-.30 if end=='teal' else .30,0.,0.])


def run(plan,out,*,cap_s=90.,prefix_cap_s=35.,own_pose_source='commands',observe_mode='gaze_v2',render_dr='off',
        zone_slots='floor',reach_mode='calibrated_mid_v1',held_object='visible_v0',lookaround='off',pose_anchor='legacy_truth_v0',placement='margin_v0',lateral_recovery='off',active_recovery='off',command_motion='off',localization_support='off',regrasp_check='off',regrasp_recovery='off',release_profile='off',record_training=False):
    release16.validate(release_profile,record_training,locals(),plan)
    line_guard=release_profile in (release14.PROFILE, release15.PROFILE, release16.PROFILE)
    fov_guard=release_profile in (release15.PROFILE, release16.PROFILE)
    line_control=release16 if release_profile==release16.PROFILE else (release15 if fov_guard else release14)
    if observe_mode not in OBSERVE_MODES:raise ValueError(observe_mode)
    if lookaround not in LOOKAROUND_MODES:raise ValueError(lookaround)
    if lookaround!='off' and observe_mode!='backoff_v3':raise ValueError('lookaround runs after the backoff_v3 step back')
    if zone_slots not in ZONE_SLOT_MODES:raise ValueError(zone_slots)
    if pose_anchor not in POSE_ANCHOR_MODES:raise ValueError(pose_anchor)
    relative_pose=pose_anchor=='command_relative_v1'
    if relative_pose and own_pose_source!='commands':raise ValueError('command_relative_v1 requires own commands')
    if placement not in PLACEMENT_MODES:raise ValueError(placement)
    rgb_center=placement==RGB_CENTER
    global_release=placement=='global_localized_release_v1'
    if regrasp_check not in REGRASP_CHECK_MODES:raise ValueError(regrasp_check)
    checked_regrasp=regrasp_check!='off'
    if checked_regrasp and not global_release:raise ValueError('regrasp check requires global RGB release')
    if regrasp_recovery not in REGRASP_RECOVERY_MODES:raise ValueError(regrasp_recovery)
    if regrasp_recovery!='off' and (not checked_regrasp or command_motion!='native_yaw_v1' or not relative_pose or held_object!='hidden_v1'):
        raise ValueError('RGB realign requires checked RGB release, command-relative native motion and hidden held object')
    from sim.global_landmark_localization import SUPPORT_MODES
    if localization_support not in SUPPORT_MODES:raise ValueError(localization_support)
    if localization_support!='off' and not global_release:raise ValueError('localization support requires global RGB release')
    if command_motion not in ('off','native_yaw_v1'):raise ValueError(command_motion)
    if command_motion!='off' and not global_release:raise ValueError('native command motion requires global RGB release')
    if lateral_recovery not in LATERAL_MODES:raise ValueError(lateral_recovery)
    if lateral_recovery!='off' and not global_release:raise ValueError('lateral recovery requires global release')
    if active_recovery not in ACTIVE_RECOVERY_MODES:raise ValueError(active_recovery)
    if active_recovery!='off' and not global_release:raise ValueError('active recovery requires global release')
    rgb_only=rgb_center or global_release
    if global_release and not (relative_pose and held_object=='hidden_v1' and lookaround=='setdown_global_v1' and observe_mode=='backoff_v3'):
        raise ValueError('global_localized_release_v1 requires command_relative_v1, hidden_v1, setdown_global_v1, backoff_v3')
    if lookaround=='setdown_global_v1' and not global_release:
        raise ValueError('setdown_global_v1 release integration requires global_localized_release_v1')
    if rgb_center and not (relative_pose and held_object=='hidden_v1' and lookaround=='setdown_lookaround_v2' and observe_mode=='backoff_v3'):
        raise ValueError('zone_center_rgb_v1 requires command_relative_v1, hidden_v1, setdown_lookaround_v2, backoff_v3')
    audit=HeldAudit(held_object)
    if platform.system()=='Darwin':raise RuntimeError('Mac physics/render disabled; use VM3')
    import numpy as np
    from PIL import Image
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_teacher import GraspTeacher
    from sim.grasp_act_release_teacher import (ReleaseTeacher,PairReleaseCode,QuantizedWheels,BACKOFF_M,
        LOWER_Z_M,RAISE_Z_M,FOLDED_BACKOFF,OBSERVE_BACKOFF_M)
    from harness.visual_arm_v3 import solve_grip_site_ik,MOUNT_X_M
    from sim.visible_belief import relative
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
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    write(out/'RUN_META.json',{'class':'dev','pr':491,'branch':branch,'sha':sha,'batch':plan['batch']})
    report={'status':'running','source_sha':sha,'teacher':'release_visible_only_v1','own_pose_source':own_pose_source,'observe_mode':observe_mode,'zone_slots':zone_slots,'reach_mode':reach_mode,'held_object':held_object,'lateral_recovery':lateral_recovery,'active_recovery':active_recovery,
        'lookaround':lookaround,'pose_anchor':pose_anchor,'placement':placement,'command_motion':command_motion,'localization_support':localization_support,'regrasp_check':regrasp_check,'regrasp_recovery':regrasp_recovery,'release_profile':release_profile,'map_pose_known':not relative_pose,
        'release_decision_inputs':'own RGB, own issued commands, static map only' if rgb_only else 'legacy visible-only teacher',
        'pose_estimate_source':'own issued wheels from arbitrary zero; map pose unknown' if relative_pose else 'legacy truth at release handoff plus frozen plan error',
        'own_camera_px':list(LOOK_RES if lookaround!='off' else (320,240)),'weld':'off','recording_mode':'success_measurement','student_execution':False,'success_rule':SUCCESS,
        'training_exclusions':{'prefix':{'included':False,'reason':'truth contact/height termination; scene preparation only'},
            'release':{'included':False,'reason':'success measurement; no student writer or gate admission'}},
        'loadavg_at_start':os.getloadavg(),'release_success':None,'prefix_held':None}
    if not line_guard:
        report.pop('release_profile');report.pop('training_exclusions')
    write(out/'result.json',report);world=None;start=time.monotonic();streams=[];origin=0.
    try:
        os.environ['UGRP_SIM_OBSERVER_WIDTH']='320';os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
        scene=make_scene(plan)
        cw,ch=LOOK_RES if lookaround!='off' else (320,240)   # existing OpenCV localisation modules work at 640x480 only
        world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=cw,height=ch,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        for controller in world.controllers.values():bind_camera(controller)
        scene.setup(world)
        from harness.render_randomization import draw as dr_draw,apply as dr_apply
        report['render_randomization']=dr_apply(world.model,None if render_dr=='off' else dr_draw(plan['seed'],world.model.nlight))
        place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
        (out/'scene.xml').write_text(world.scene_xml);write(out/'scene.json',scene.manifest)
        static=scene.config['static_map'];zone=static['regions'][plan['destination_region']]
        rect=(*zone['center_m'],*zone['half_extents_m'])
        roles=plan['roles'];ports={rid:ContinuousActPort(world,rid,allow_reverse=True,allow_mecanum=True) for rid in roles}
        wheels={rid:QuantizedWheels(port) for rid,port in ports.items()}
        issued_pose={rid:CommandPose(command_motion) for rid in roles}
        # These frame origins are used only by look_truth(), never by the teachers/localizers.
        eval_origin={rid:[*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])] for rid in roles} if relative_pose else {}
        for rid,port in ports.items():port.apply({'kind':'look','pan_pulse':plan['initial_pan'][rid]},float(world.data.time))
        def advance(target):
            while float(world.data.time)<target-1e-8:
                now=float(world.data.time)
                if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                for rid,port in ports.items():port.tick(now);wheels[rid].tick(now)
                issued={rid:tuple(port._motor_commands) for rid,port in ports.items()} if relative_pose else {}
                world._physics_step_for(world.robot('r1'))
                for rid,levels in issued.items():issued_pose[rid].propagate(levels,float(world.data.time)-now)
        advance(float(world.data.time)+.5)
        origin=float(world.data.time);inst=next(x for x in scene.cargo if x.item_id=='beam_1')
        band=BandVisibility(world.model);region=plan['destination_region']
        slots=destination_slot_geoms([world.model.geom(g).name for g in range(world.model.ngeom)],region) if zone_slots=='zone' else []
        report['zone_slot_geoms']=[world.model.geom(g).name for g in slots]
        eyes=Eyes(band,world.model.geom('zone_'+region).id,slots)
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
        if line_guard:
            report['training_exclusions']['prefix'].update(start_world_t=origin,end_world_t=float(world.data.time))
            write(out/'training-segments.json',report['training_exclusions'])
        if held is None:
            report.update(status='complete',release_success=None,release_outcome='prefix_not_held');return report
        # ---------------- release: visible_only teacher ----------------
        for port in ports.values():port.stop()
        rel={}
        for rid,end in roles.items():
            truth_pose=None if relative_pose else [*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])]
            estimate=handoff_estimate(plan,rid,issued_pose[rid],pose_anchor=pose_anchor,own_pose_source=own_pose_source,truth_pose=truth_pose)
            pwm={int(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            rel[rid]=ReleaseTeacher(rid,end,pwm,handoff_pose_estimate=None if relative_pose else estimate,zone_rect=rect,own_pose_source=own_pose_source,reach_mode=reach_mode,odometry_profile=command_motion)
        report['handoff_estimates']={rid:list(issued_pose[rid].x) for rid in roles} if relative_pose else None
        loc={}
        if lookaround!='off':
            from sim.lookaround_localization import LookaroundLocalizer
            for rid,t in rel.items():
                truth_pose=None if relative_pose else [*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])]
                estimate=handoff_estimate(plan,rid,issued_pose[rid],pose_anchor=pose_anchor,own_pose_source=own_pose_source,truth_pose=truth_pose)
                loc[rid]=LookaroundLocalizer(static,estimate,mode=lookaround,map_pose_known=not relative_pose,odometry_profile=command_motion,localization_support=localization_support)
        zone_servo={}
        if rgb_center:
            from sim.release_zone_servo import ZoneCenterServo
            zone_servo={rid:ZoneCenterServo(static,region,loc[rid].camera,loc[rid].vl.mp) for rid in roles}
        look_eval={rid:{'views':[],'sweeps':[]} for rid in roles};look_run={}
        def look_truth(rid):
            # evaluation only: estimate error against truth and FK camera vs rendered camera (never fed back)
            g=pose_of(rid);x=loc[rid].own.x
            command_frame=relative_pose and not loc[rid].map_pose_known
            target=relative(eval_origin[rid],g[:2],g[2]) if command_frame else g
            out={'error_xy_m':float(math.hypot(x[0]-target[0],x[1]-target[1])),'error_yaw_deg':float(math.degrees((x[2]-target[2]+math.pi)%(2*math.pi)-math.pi)),
                 'truth':g,'error_frame':'arbitrary_command_start' if command_frame else 'map'}
            ctrl=world.controllers[rid];cid=ctrl.robot_cam_cid;c_,s_=math.cos(g[2]),math.sin(g[2])
            b_=world.robot(rid).base_xyz();cp=np.array([world.data.cam_xpos[cid][0]-b_[0],world.data.cam_xpos[cid][1]-b_[1],world.data.cam_xpos[cid][2]]);cz=world.data.cam_xmat[cid].reshape(3,3)@np.array([0.,0.,-1.])
            rot_b=np.array([[c_,s_,0.],[-s_,c_,0.],[0.,0.,1.]]);body_o,body_z=rot_b@cp,rot_b@cz
            fk,_=loc[rid].camera.pose({1:rel[rid].pwm[1],**{k:rel[rid].pwm[k] for k in (3,4,5,6)}})
            if fk is not None:
                out['camera_fk_origin_error_m']=float(np.linalg.norm(fk[0]-body_o))
                out['camera_fk_axis_error_deg']=float(math.degrees(math.acos(max(-1.,min(1.,float(fk[1][:,2]@body_z))))))
            return out
        def look_capture(rid,now):
            jpeg=base64.b64decode(ports[rid].capture()['image'])
            img=np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))
            servo={1:rel[rid].pwm[1],**{k:rel[rid].pwm[k] for k in (3,4,5,6)}}
            rec=loc[rid].observe(now,img,servo)
            if global_release:
                # Sparse review evidence of the actual consumed input, not
                # student training recording. Native size, no re-render/resize.
                path=out/'eval-lookaround-input'/rid/f'{len(loc[rid].views):04d}.jpg'
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(jpeg)
                rec.update(input_jpeg=str(path.relative_to(out)),input_sha256=hashlib.sha256(jpeg).hexdigest())
            if rgb_center:
                zone_servo[rid].observe(img,servo,now)
            audit.measurement('lookaround','own_rgb_landmarks',True,count=sum(rec.get(k,0) for k in ('wall_points','floor_lines','doors')))
            row={'t':now,'pan_pulse':servo[6],'wall_points':rec.get('wall_points'),'floor_lines':rec.get('floor_lines'),'doors':rec.get('doors'),
                 'seen_groups':rec.get('seen_groups'),**look_truth(rid)}
            look_eval[rid]['views'].append(row);ev.write(json.dumps({'kind':'lookaround_view','rid':rid,**row})+'\n')
        R=tuple(roles);code=PairReleaseCode(R);release_t0=float(world.data.time)
        st={'phase':'look','since':release_t0,'iter':0,'steps':0,'search':0,'sched':{},'plan':{},'go':None,'after_visible':False,'choice':None}
        recovery_stage={rid:0 for rid in roles}; recovery_log=[]
        regrasp_barriers=[]; barrier=None; regrasp_inputs=[]; rejection_counts={}
        line_checks=[]; line_check=None; line_pending=[]; line_stage=None; backoff_checks=[]
        nbv_history={rid:[] for rid in roles}
        release_command_poses={}
        b0=world.data.body(inst.body)
        report['release_start']={'beam_to_zone_center_m':float(math.dist(b0.xpos[:2],rect[:2]))}
        def pose_of(rid):return [*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])]
        def observe(rid,now,fine):
            if rgb_only:
                # This path must never call Eyes, pose_of, band.measure or a
                # simulator object lookup. Regrasp uses the issued release pose.
                return {'scan':[],'own_band_visible':False,'band':None,'partner_visible':False}
            at=time.monotonic();data=world.data;pose=pose_of(rid);t=rel[rid]
            m=band.measure(data,rid,roles[rid])
            if relative_pose or (t.holding and held_object=='hidden_v1'):
                # Own landing end from the grasp pose (fixed offset, commands FK); the true base pose only places
                # the camera for image formation (which floor points the pixels show), as rendering does.
                (ex,ey),(ox,oy),_=t.end_and_outward(now);c_,s_=math.cos(pose[2]),math.sin(pose[2])
                e=np.array([pose[0]+c_*ex-s_*ey,pose[1]+s_*ex+c_*ey,0.]);out_dir=np.array([c_*ox-s_*oy,s_*ox+c_*oy,0.])
            else:
                audit.read(t.holding,'scan_axis');audit.read(t.holding,'scan_end')
                audit.measurement(st['phase'],'scan_axis',m['visible_probes']>=3)
                audit.measurement(st['phase'],'scan_end',m['visible_probes']>=3)
                b=data.body(inst.body);rot=b.xmat.reshape(3,3);axis=rot[:,0]
                out_dir=-axis if roles[rid]=='teal' else axis
                e=own_end_world(world,inst,roles[rid])
            lat=np.array([-out_dir[1],out_dir[0],0.]);scan=[]
            for s_ in np.arange(-.25,.2501,.01 if fine else .05):
                for l_ in (-.05,.05):
                    p=e+s_*out_dir+l_*lat;p=(float(p[0]),float(p[1]),.0012)
                    c=eyes.classify(data,rid,p)
                    if c is not None:
                        scan.append([*relative(pose,p[:2])[:2],c])
                        audit.measurement(st['phase'],'scan_point',eyes.classify(data,rid,p) is not None)
            obs={'scan':scan,'own_band_visible':m['visible_probes']>=3,'band':None}
            audit.assigned_end(st['phase'],rid,obs['own_band_visible'])
            if obs['own_band_visible'] and not (t.holding and held_object=='hidden_v1'):
                audit.read(t.holding,'band_pose')
                audit.measurement(st['phase'],'own_band_pose',band.measure(data,rid,roles[rid])['visible_probes']>=3)
                gid=band.bands[roles[rid]];g=data.geom_xpos[gid];rot=data.body(inst.body).xmat.reshape(3,3)
                obs['band']=relative(pose,(float(g[0]),float(g[1])),math.atan2(rot[1,0],rot[0,0]))
            obs['partner_visible']=any(band.body_visible(data,rid,p+'__robot') for p in roles if p!=rid)
            timings['eyes']+=time.monotonic()-at
            return obs
        def post(tag,now):
            for rid,t in rel.items():code.post(rid,{**(t.last_report or {}),'phase':tag},now)
        def ready(tag,now):
            code.deliver(now);return code.ready(tag,st['since'])
        def schedule(rid,seq,t0):st['sched'][rid]=[(t0+dt,p) for dt,p in seq]
        def run_sched(now):
            for rid,seq in st['sched'].items():
                while seq and seq[0][0]<=now+1e-9:
                    _,pose=seq.pop(0)
                    for sid,v in pose.items():
                        if rel[rid].pwm.get(sid)!=v:
                            ports[rid].apply({'kind':'look','pan_pulse':v} if sid==6 else {'kind':'arm','servo_id':sid,'pulse':v},now);rel[rid].pwm[sid]=v
            return any(st['sched'].values())
        def run_plan(now):
            busy=False
            for rid,p in st['plan'].items():
                if p:w,d=p.pop(0);wheels[rid].command(w,d,now);busy=True
            return busy
        def every(seq_fn,interval):return [(interval*(k+1),p) for k,p in enumerate(seq_fn)]
        def start_lower(now):
            for rid,t in rel.items():schedule(rid,every(t.arm_waypoints(LOWER_Z_M,8),.2),now+.2)
            st.update(phase='lower',since=now,go=now+.2,end=now+.2+1.6+.6)
        def start_shift(now,s):
            if checked_regrasp:
                if barrier is None or not all(barrier.confirmed.values()) or barrier.state!='ready':
                    raise RuntimeError('REGRASP_BARRIER_REQUIRED')
                tag=f'regrasp_confirmed_{barrier.epoch}'
                if not code.ready(tag,st['since']):raise RuntimeError('REGRASP_ACK_REQUIRED')
            lateral=(st['choice'] or {}).get('lateral_shift_m')
            if (st['choice'] or {}).get('action')=='axis_correct':
                from sim.release_axis_correction import plans as axis_plans
                st['plan']=axis_plans(loc,rel,st['choice']['axis_turn_rad'],now)
                report.setdefault('axis_motion_commands',[]).append(dict(t=now,
                    angle_rad=st['choice']['axis_turn_rad'],plans=copy.deepcopy(st['plan'])))
            elif lateral is not None:
                from sim.release_global_observation import lateral_shift_plans
                st['plan']=lateral_shift_plans(loc,rel,lateral)
                report.setdefault('lateral_motion_commands',[]).append(dict(t=now,shift_m=lateral,
                    plans=copy.deepcopy(st['plan']),scope='own RGB headings + issued commands; nominal motion only'))
            else:
                st['plan']={rid:t.shift_plan(s,1. if rid==R[0] else -1.) for rid,t in rel.items()}
            st['steps']+=1
            st.update(phase='shift',since=now,go=now+.2)
        def regrasp_capture(rid,now,label):
            jpeg=base64.b64decode(ports[rid].capture()['image'])
            path=out/'eval-regrasp-input'/rid/f'{len(regrasp_inputs):05d}-{label}.jpg'
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(jpeg)
            regrasp_inputs.append(dict(robot=rid,t=now,epoch=st['iter'],label=label,
                path=str(path.relative_to(out)),sha256=hashlib.sha256(jpeg).hexdigest()))
            return np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))[:,:,::-1].copy()
        def line_factory(teacher,now):
            guard=line_control.LineAlign(teacher,now,camera=loc[teacher.rid].camera,
                undistort=loc[teacher.rid].vl.mp.undistort,
                wheel_command=lambda rid,w,d,at:wheels[rid].command(w,d,at),
                clearance=lambda dx,dy,da:line_control.map_motion_clear(loc[teacher.rid],dx,dy,da),
                **({'pick_audit':lambda at,t,xy:audit.pick('line_aligned_station',t.rid,at,t,xy=xy)} if fov_guard else {}))
            guard.peer_commands={r:dict(t.pwm) for r,t in rel.items() if r!=teacher.rid}
            return guard
        def regrasp_recovery_factory(teacher,now):
            if line_guard:return line_factory(teacher,now)
            from sim.release_regrasp_recovery import RealignRecovery
            return RealignRecovery(teacher,now,camera=loc[teacher.rid].camera,
                undistort=loc[teacher.rid].vl.mp.undistort,
                wheel_command=lambda rid,w,d,at:wheels[rid].command(w,d,at))
        k=0;outcome=None;done_at=None
        while float(world.data.time)-origin<cap_s:
            now=float(world.data.time);tick_t=now;ph=st['phase'];age=now-st['since']
            fine=ph in ('look','observe')
            for rid,t in rel.items():t.phase=ph;t.perceive(observe(rid,now,fine),now)
            if ph=='look' and age>=.6:
                for t in rel.values():t.report(now,'look')
                post('look',now);st.update(phase='await_look',since=now)
            elif ph=='await_look' and ready('look',now):
                choice=code.decide(now,require_seen=False);st['choice']=choice
                if choice['action']=='lower' or st['steps']>=8:start_lower(now)
                else:start_shift(now,choice['shift_m'])
            elif ph=='shift' and now>=st['go']-1e-9:
                if not run_plan(now):
                    if st['after_visible']:st['after_visible']=False;start_lower(now)
                    else:st.update(phase='look',since=now)
            elif ph=='lower':
                run_sched(now)
                if now>=st['end']-1e-9:
                    for t in rel.values():t.last_report={'kind':'lowered'}
                    post('lowered',now);st.update(phase='await_open',since=now)
            elif ph=='await_open' and ready('lowered',now):
                st.update(phase='open',since=now,go=now+.2,opened=False)
            elif ph=='open' and now>=st['go']-1e-9:
                if not st['opened']:
                    for rid,t in rel.items():ports[rid].apply({'kind':'arm','servo_id':1,'pulse':2000},now);t.pwm[1]=2000
                    st['opened']=True
                if now-st['go']>=1.2 and observe_mode=='backoff_v3':
                    # Step back with the gripper raised, then look: the floor beyond the own end enters the view.
                    for rid,t in rel.items():
                        t.released_here(now);schedule(rid,every(t.arm_waypoints(RAISE_Z_M,3),.2),now)
                        if active_recovery=='setdown_lookaround_v1':
                            release_command_poses[rid]=loc[rid].command_own.x.copy()
                    st['plan']={} if line_guard else {rid:t.shift_plan(OBSERVE_BACKOFF_M,-1.) for rid,t in rel.items()}
                    st.update(phase='observe_back',since=now,go=now+.8,settle=None,search=0,pre_backoff=line_guard)
                elif now-st['go']>=1.2:
                    for rid,t in rel.items():
                        t.released_here(now)
                        seq=every(t.arm_waypoints(RAISE_Z_M,3),.2)
                        schedule(rid,seq+[(1.0,t.gaze_target(now))],now)
                    st.update(phase='observe_move',since=now,end=now+1.0+.8,search=0)
            elif ph=='observe_back':
                run_sched(now)
                if now>=st['go']-1e-9 and not run_plan(now):
                    if st['settle'] is None:st['settle']=now+.3
                    elif now>=st['settle']-1e-9 and lookaround!='off':
                        from sim.lookaround_localization import ScriptRunner
                        for rid,t in rel.items():
                            look_eval[rid]['before']=look_truth(rid);look_eval[rid]['t0']=now
                            loc[rid].make_plan(t.pwm[6])
                            restore={k:t.pwm[k] for k in (3,4,5,6)} if lookaround in ('setdown_lookaround_v2','setdown_global_v1') else None
                            script=loc[rid].script(restore=restore)
                            if rgb_center:
                                from sim.lookaround_localization import LOOK_ARM,look_servo,VIEW_SETTLE_S
                                zone_servo[rid].begin()
                                # Preserve the real surroundings panorama, then
                                # inspect nearby floor edges with a downward view.
                                script=script[:-1]+[{'servo':look_servo(p,LOOK_ARM),'wait':1.0 if i==0 else VIEW_SETTLE_S,
                                    'capture':True,'label':f'zone_floor_{p:+.0f}'} for i,p in enumerate((-35.,0.,35.))]+script[-1:]
                            look_run[rid]=ScriptRunner(script,now)
                        st.update(phase='lookaround',since=now)
                    elif now>=st['settle']-1e-9:
                        for rid,t in rel.items():schedule(rid,[(0.,t.gaze_target(now))],now)
                        st.update(phase='observe_move',since=now,end=now+.8)
            elif ph=='lookaround':
                run_plan(now)
                for rid,t in rel.items():
                    def set_servo(pose,at,rid=rid,t=t):
                        for sid,v in pose.items():
                            if t.pwm.get(sid)!=v:
                                ports[rid].apply({'kind':'look','pan_pulse':v} if sid==6 else {'kind':'arm','servo_id':sid,'pulse':v},at);t.pwm[sid]=v
                    def set_wheels(pl,at,rid=rid):st['plan'][rid]=pl
                    look_run[rid].tick(now,set_servo=set_servo,set_wheels=set_wheels,
                        wheels_idle=lambda rid=rid:not st['plan'].get(rid) and all(now>=u-1e-9 for u in wheels[rid].until),
                        capture=lambda at,rid=rid:look_capture(rid,at))
                if all(r.done for r in look_run.values()):
                    for rid,t in rel.items():
                        dec=loc[rid].finalize()    # v2: one joint update with acceptance tests (None for v1)
                        look_eval[rid].update(after=look_truth(rid),sim_s=now-look_eval[rid]['t0'],script=look_run[rid].log,
                                              decision=None if dec is None else {k:dec.get(k) for k in ('accepted','reason','wall_inliers','features','views_with_evidence')})
                        if localization_support != 'off':
                            # Preserve every fit, including rejected poses and alternative scores.
                            look_eval[rid]['decision'] = copy.deepcopy(dec)
                        if lookaround=='setdown_lookaround_v1' and not relative_pose:   # only an actual map pose anchors map priors
                            t.reanchor_priors(list(loc[rid].own.x))
                        elif dec and dec['accepted'] and not global_release:
                            t.reanchor_priors(list(loc[rid].own.x))
                        if rgb_center:
                            (ex,ey),(ox,oy),_=t.end_and_outward(now)
                            zfit=zone_servo[rid].finalize([ex-.30*ox,ey-.30*oy])
                            look_eval[rid]['zone_center']=zfit
                            look_eval[rid]['zone_rgb_views']=zone_servo[rid].views
                            # Separate scoring, never inserted into zfit/the posted report.
                            target=relative(pose_of(rid),rect[:2])[:2]
                            predicted=zfit.get('center_body_m')
                            look_eval[rid]['zone_center_evaluation']={'truth_center_body_m':target,
                                'center_error_m':None if predicted is None else math.dist(predicted,target)}
                        look_eval[rid]['sweeps'].append(copy.deepcopy({k:v for k,v in look_eval[rid].items() if k not in ('sweeps','views')}))
                        schedule(rid,[(0.,t.gaze_target(now))],now)
                    if line_guard and st.get('pre_backoff'):
                        for rid,t in rel.items():
                            st['plan'][rid],receipt=line_control.backoff_plan(loc[rid],t)
                            backoff_checks.append(dict(t=now,robot=rid,**receipt))
                        st.update(phase='observe_back',since=now,go=now+ARM_MOVE_BACK_S,settle=None,pre_backoff=False)
                    else:st.update(phase='observe_move',since=now,end=now+ARM_MOVE_BACK_S)
            elif ph=='observe_move':
                run_sched(now)
                if now>=st['end']-1e-9:st.update(phase='observe',since=now)
            elif ph=='observe' and age>=.6:
                if global_release:
                    from sim.release_global_observation import margin_report
                    reports={rid:margin_report(loc[rid],t,now,
                        **({'lateral_recovery':lateral_recovery} if lateral_recovery!='off' else {}),
                        **({'axis_recovery':True} if checked_regrasp else {})) for rid,t in rel.items()}
                    for rid,t in rel.items():t.last_report=reports[rid]
                    if checked_regrasp:
                        for rid,r in reports.items():
                            if r.get('kind')=='none':
                                reason=r.get('reason','unobserved')
                                rejection_counts[reason]=rejection_counts.get(reason,0)+1
                elif rgb_center:
                    reports={rid:{'phase':'observe','kind':'rgb_center','zone_center':zone_servo[rid].result or {}} for rid in rel}
                    for rid,t in rel.items():t.last_report=reports[rid]
                else:reports={rid:t.report(now,'observe') for rid,t in rel.items()}
                blind=[rid for rid,r in reports.items() if r['kind'] in ('prior','none')]
                if blind and st['search']<4 and not global_release:
                    st['search']+=1;offset=(250,-250,500,-500)[st['search']-1]
                    for rid in blind:
                        target=dict(rel[rid].gaze_target(now));target[6]=max(500,min(2500,target[6]+offset))
                        schedule(rid,[(0.,target)],now)
                    st.update(phase='observe_move',since=now,end=now+.8)
                else:
                    post('observe',now);st.update(phase='await_observe',since=now)
            elif ph=='await_observe' and ready('observe',now):
                if global_release:
                    from sim.release_global_observation import pair_choice
                    choice=pair_choice(code.delivered,R,now,lateral_recovery=lateral_recovery,
                        **({'axis_recovery':True} if checked_regrasp else {}));code.log.append(choice)
                elif rgb_center:
                    from sim.release_zone_servo import pair_choice
                    choice=pair_choice(code.delivered,R,now);code.log.append(choice)
                else:choice=code.decide(now,require_seen=True)
                st['choice']=choice
                if choice['action']=='axis_correct':
                    from sim.release_axis_correction import correction_angle
                    try:choice['axis_turn_rad']=correction_angle(choice)
                    except ValueError as error:
                        outcome=str(error);rejection_counts[outcome]=rejection_counts.get(outcome,0)+1;break
                if choice['action']=='observe' and global_release:
                    from sim.release_global_observation import recovery_round
                    from sim.lookaround_localization import ScriptRunner
                    # Only own perception chooses the recovery action. A robot
                    # with sufficient evidence waits; no partner pose is read.
                    scripts,entries=recovery_round(loc,rel,code.delivered,recovery_stage,now,
                        active_recovery=active_recovery,nbv_history=nbv_history,
                        release_command_poses=release_command_poses)
                    recovery_log.extend(entries)
                    if scripts is None:
                        outcome='active_observation_exhausted';break
                    for rid,t in rel.items():
                        look_eval[rid]['before']=look_truth(rid);look_eval[rid]['t0']=now
                        look_run[rid]=ScriptRunner(scripts[rid],now)
                    st.update(phase='lookaround',since=now)
                    continue
                if choice['action']=='stop':outcome=choice['reason'];break
                if choice['action']=='lower' and observe_mode=='backoff_v3':
                    for rid in rel:schedule(rid,[(0.,FOLDED_BACKOFF)],now)
                    st.update(phase='done',since=now);done_at=now
                elif choice['action']=='lower':
                    for rid,t in rel.items():schedule(rid,[(0.,{3:820,4:2320})],now)
                    st['plan']={rid:t.shift_plan(BACKOFF_M,-1.) for rid,t in rel.items()}
                    st.update(phase='back_off',since=now,go=now+.6)
                else:
                    st['iter']+=1
                    from sim.release_zone_servo import MAX_CORRECTIONS
                    limit=MAX_CORRECTIONS if rgb_center else 3
                    if global_release:
                        from sim.release_global_observation import MAX_CORRECTIONS as limit
                    if st['iter']>limit:outcome='release_iteration_cap';break
                    recovery_stage={rid:0 for rid in roles}
                    nbv_history={rid:[] for rid in roles}
                    if line_guard:
                        line_pending=list(R);line_stage='before_approach';line_check=line_factory(rel[line_pending.pop(0)],now)
                        line_checks.append(line_check);st.update(phase='line_recheck',since=now)
                        continue
                    # Approach by own-command pulses until the re-grasp target is mid-reach (no reach crash).
                    for rid,t in rel.items():audit.pick('approach',rid,now,t)
                    st['plan']={rid:t.approach_plan(now) for rid,t in rel.items()}
                    for rid,pl in st['plan'].items():
                        if pl:schedule(rid,[(0.,{k:int(v) for k,v in solve_grip_site_ik((MOUNT_X_M+rel[rid].reach_mid(),0.,.095)).items() if k in (3,4,5,6)})],now)
                    moving=any(st['plan'].values())
                    st.update(phase='approach',since=now,go=now+(.8 if moving else 0.),settle=None,moving=moving)
            elif ph=='approach':
                run_sched(now)
                if now>=st['go']-1e-9 and not run_plan(now):
                    if st['settle'] is None:st['settle']=now+(.3 if st['moving'] else 0.)
                    if now>=st['settle']-1e-9:
                        if line_guard:
                            line_pending=list(R);line_stage='after_approach';line_check=line_factory(rel[line_pending.pop(0)],now)
                            line_checks.append(line_check);st.update(phase='line_recheck',since=now)
                            continue
                        dur=0.
                        try:
                            for rid,t in rel.items():
                                audit.pick('repick',rid,now,t)
                                seq,d=t.pick_schedule(now);schedule(rid,seq,now+.2);dur=max(dur,d)
                        except ValueError as error:
                            report['repick_error']=str(error);outcome='repick_unreachable';break
                        st.update(phase='repick',since=now,end=now+.2+dur)
            elif ph=='line_recheck':
                run_sched(now)
                peer=[r for r in R if r!=line_check.teacher.rid]
                if any(any(wheels[r].levels) or rel[r].pwm!=line_check.peer_commands[r] for r in peer):
                    outcome=release_profile.split('_')[0]+'_peer_motion_during_alignment';break
                status=line_check.tick(now,regrasp_capture,schedule)
                if status=='failed':outcome=line_check.failure;break
                if status=='ready':
                    if line_pending:
                        line_check=line_factory(rel[line_pending.pop(0)],now);line_checks.append(line_check)
                    elif line_stage=='before_approach':
                        if fov_guard:
                            for rid,t in rel.items():audit.pick('approach',rid,now,t)
                        try:st['plan']={rid:line_control.approach_plan(loc[rid],t,now) for rid,t in rel.items()}
                        except ValueError as error:outcome=str(error);break
                        moving=any(st['plan'].values())
                        st.update(phase='approach',since=now,go=now+.2,settle=None,moving=moving)
                    else:
                        dur=0.
                        try:
                            for rid,t in rel.items():
                                xy=(MOUNT_X_M+t.reach_mid(),0.)
                                if fov_guard:audit.pick('repick',rid,now,t,xy=xy)
                                seq,d=t.pick_schedule(now,xy=xy);schedule(rid,seq,now+.2);dur=max(dur,d)
                        except ValueError as error:
                            report['repick_error']=str(error);outcome='repick_unreachable';break
                        st.update(phase='repick',since=now,end=now+.2+dur)
            elif ph=='repick':
                run_sched(now)
                if now>=st['end']-1e-9:
                    if checked_regrasp:
                        from sim.release_regrasp import RegraspBarrier
                        barrier=RegraspBarrier(rel,st['iter'],now,wheel_commands=lambda r:list(wheels[r].levels),
                            recovery_factory=regrasp_recovery_factory if regrasp_recovery!='off' else None,
                            assigned_end_evidence=line_guard,
                            **({'colour_profile':release15.PROFILE} if fov_guard else {}))
                        regrasp_barriers.append(barrier)
                        for t in rel.values():t.holding=False
                        st.update(phase='regrasp_check',since=now)
                    else:
                        for t in rel.values():t.holding=True
                        st['after_visible']=True;start_shift(now,st['choice']['shift_m'])
            elif ph=='regrasp_check':
                run_sched(now)
                status=barrier.tick(now,regrasp_capture,schedule)
                if status=='failed':outcome=barrier.failure;break
                if status=='ready':
                    tag=f'regrasp_confirmed_{barrier.epoch}'
                    for rid,t in rel.items():
                        t.holding=True
                        t.last_report=dict(kind='own_rgb_confirmed',epoch=barrier.epoch,attempt=barrier.attempts[rid])
                    post(tag,now);st.update(phase='await_regrasp',since=now)
            elif ph=='await_regrasp':
                tag=f'regrasp_confirmed_{barrier.epoch}'
                if ready(tag,now):
                    bad,reason=barrier.fresh(now,regrasp_capture)
                    if bad is not None:
                        barrier.retry(bad,reason,now,schedule)
                        st.update(phase='regrasp_check',since=now)
                    else:
                        st['after_visible']=True
                        try:start_shift(now,st['choice'].get('shift_m',0.))
                        except ValueError as error:
                            outcome=str(error);rejection_counts[outcome]=rejection_counts.get(outcome,0)+1;break
                elif age>DELIVERY_WAIT_S:
                    outcome='regrasp_go_ack_timeout';break
            elif ph=='back_off':
                run_sched(now)
                if now>=st['go']-1e-9 and not run_plan(now):
                    for rid,t in rel.items():schedule(rid,[(0.,FOLDED_BACKOFF)],now)
                    st.update(phase='done',since=now);done_at=now
            elif ph=='done':
                run_sched(now)
                if age>=DELIVERY_WAIT_S:outcome='teacher_done';break
            for rid,t in rel.items():
                labels[rid].write(json.dumps({'t':now,'skill':'release','object_kind':'long_beam','role':roles[rid],
                    **({'training_eligible':False,'training_exclusion':('measurement_only_release' if fov_guard else 'measurement_only_release_prefix_excluded')} if line_guard else {}),
                    'teacher_phase':st['phase'],'wheels':list(wheels[rid].levels),'wheel_until':list(wheels[rid].until),
                    'pwm':{str(s):t.pwm[s] for s in SERVOS},'holding_belief':t.holding,'done':st['phase']=='done','report':t.last_report})+'\n')
            if k%10==0:frames(k,'release-'+st['phase'])
            issued={rid:(list(wheels[rid].levels),max([max(0.,min(.1,u-tick_t)) if lv else 0. for lv,u in zip(wheels[rid].levels,wheels[rid].until)]))
                    for rid in rel}
            if (ph=='shift' and ((lateral_recovery!='off' and (st['choice'] or {}).get('lateral_shift_m') is not None)
                    or (checked_regrasp and (st['choice'] or {}).get('action')=='axis_correct'))) or (ph=='regrasp_check' and regrasp_recovery!='off') or ph=='line_recheck':
                # Independent wheel PWM must propagate its time integral, not
                # max(duration) for every wheel (legacy axial pulses are equal).
                issued={rid:([lv*max(0.,min(.1,u-tick_t))/.1 for lv,u in zip(wheels[rid].levels,wheels[rid].until)],.1) for rid in rel}
            before={rid:pose_of(rid) for rid in rel} if own_pose_source!='commands' else {}
            k+=1;advance(tick_t+.1)
            for rid in loc:loc[rid].propagate(*issued[rid])
            for rid,t in rel.items():
                if own_pose_source=='commands':t.dead_reckon(*issued[rid])
                else:
                    after=pose_of(rid);dx,dy,da=relative(before[rid],after[:2],after[2]);t.belief.propagate(dx,dy,da)
            truth=snapshot(world,inst,roles,scene)
            if rgb_only:
                # Evaluation-only visibility audit, never returned to perception.
                for rid in roles:audit.assigned_end(st['phase'],rid,band.measure(world.data,rid,roles[rid])['visible_probes']>=3)
            ev.write(json.dumps({'t':float(world.data.time),'phase':st['phase'],'beam':truth['beam'],'contacts':truth['contacts'],
                'robots':{r:truth['robots'][r] for r in roles}})+'\n')
        steps=st['steps']
        report['release_outcome']=outcome or 'release_timeout'
        # ---------------- evaluation (truth) ----------------
        checks=[]
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
        report['evaluation_position_error']=position_error(last['beam_xy_yaw'],rect)
        reasons=[n for n,v in (('not_in_zone',not last['fit']),('not_on_floor',last['z']>=SUCCESS['on_floor_z_m']),
            ('tilt',last['tilt_deg']>=SUCCESS['tilt_deg']),('finger_contact',any(max(v)>1e-6 for v in last['contact_n'].values())),
            ('gripper_closed',any(p<SUCCESS['open_pwm'] for p in last['open_pwm'].values())),
            ('gripper_not_clear',min(last['grip_to_beam_m'])<SUCCESS['clear_m'])) if v]
        report.update(release_success=best*.1>=SUCCESS['settle_s']-1e-6 and report['release_outcome']=='teacher_done',
            release_failure_reasons=reasons if reasons else ([] if report['release_outcome']=='teacher_done' else [report['release_outcome']]),
            evaluation_last=last,evaluation_settled_s=best*.1,code_decisions=code.log,shift_steps=steps,iterations=st['iter'],
            teachers={rid:t.diagnostic() for rid,t in rel.items()},
            lookaround_result=None if lookaround=='off' else {rid:{'localizer':loc[rid].record(),'evaluation':look_eval[rid]} for rid in roles},release_sim_s=(done_at or float(world.data.time))-release_t0,status='complete')
        if global_release:
            report['active_observation']=recovery_log
            report['active_recovery']=active_recovery
            report['final_map_pose_known']={rid:loc[rid].map_pose_known for rid in roles}
            report['final_map_pose_accepted']={rid:bool((loc[rid].decision or {}).get('accepted')) for rid in roles}
            report['legacy_visibility_counts_applicable']=False  # RGB-only observe() deliberately returns an empty scan
            report['own_rgb_localization_inputs']={rid:{'frames':len(loc[rid].views),
                'measured_frames':sum(v.get('status')=='measured' for v in loc[rid].views),
                'native_input_hashes':sum('input_sha256' in v for v in loc[rid].views)} for rid in roles}
        return report
    except BaseException as error:
        report.update(status='HOST_ERROR' if not isinstance(error,KeyboardInterrupt) else 'interrupted',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        report['wall_s']=time.monotonic()-start;report['sim_s']=None if world is None else float(world.data.time)-origin
        report['loadavg_at_end']=os.getloadavg();report['input_audit']=audit.record()
        if line_guard:
            report['line_rechecks']=[c.record() for c in locals().get('line_checks',[])]
            report['map_backoff_checks']=locals().get('backoff_checks',[])
        if checked_regrasp:
            report['regrasp_verification']=[b.record() for b in locals().get('regrasp_barriers',[])]
            report['regrasp_input_frames']=locals().get('regrasp_inputs',[])
            report['release_rejection_reasons']=locals().get('rejection_counts',{})
        if isinstance(report.get('teachers'),dict):   # copied from the teachers' own diagnostics (no recomputation)
            report['input_audit']['visibility_by_phase']={r:t.get('visible_counts_by_phase') for r,t in report['teachers'].items()}
            report['input_audit']['max_destination_blind_s_by_phase']={r:t.get('max_destination_blind_s_by_phase') for r,t in report['teachers'].items()}
        try:report['timings_s']=timings
        except NameError:pass
        write(out/'result.json',report)
        for s in streams:s.close()
        if world is not None:world.close()
        compress_logs(out)


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,default=0)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cap-s',type=float,default=90.)
    p.add_argument('--release-profile',choices=release16.PROFILES,default='off')
    p.add_argument('--record-training',action='store_true',help='fail closed: safe profile and future verified gate/writer required')
    p.add_argument('--own-pose-source',choices=('commands','truth_comparison'),default='commands')
    p.add_argument('--pose-anchor',choices=POSE_ANCHOR_MODES,default='legacy_truth_v0',help='command_relative_v1: no truth handoff anchor; map pose unknown, own-command sweep only')
    p.add_argument('--placement',choices=PLACEMENT_MODES,default='margin_v0',help='zone_center_rgb_v1: local RGB rectangle centering; no world anchor')
    p.add_argument('--lateral-recovery',choices=LATERAL_MODES,default='off',help='bounded_v1: recover insufficient side clearance using own RGB localization')
    p.add_argument('--active-recovery',choices=ACTIVE_RECOVERY_MODES,default='off',help='map_nbv_v1: extra map views; setdown_lookaround_v1: retrace own backoff and scan front/rear after setdown')
    p.add_argument('--command-motion',choices=('off','native_yaw_v1'),default='off',help='native_yaw_v1: native wheel yaw sign in command integration and inverse rotation planning; speed magnitude unchanged')
    p.add_argument('--localization-support',choices=('off','map_free_v1'),default='off',help='map_free_v1: use uninflated static-map free space for pose hypotheses; motion clearance unchanged')
    p.add_argument('--regrasp-check',choices=REGRASP_CHECK_MODES,default='off',help='own_rgb_lift_v1: sequential own-RGB lift tests, bounded own retries, code ACK barrier and distinct axis recovery')
    p.add_argument('--regrasp-recovery',choices=REGRASP_RECOVERY_MODES,default='off',help='own_rgb_realign_v1: failed own grasp opens, backs off, image-servos and retries with finite caps')
    p.add_argument('--observe-mode',choices=OBSERVE_MODES,default='gaze_v2',help='backoff_v3: step back 0.15 m before the post-release look')
    p.add_argument('--render-dr',choices=('off','on_v1'),default='off',help='appearance randomization (harness/render_randomization.py); off for success measurement')
    p.add_argument('--zone-slots',choices=ZONE_SLOT_MODES,default='floor',help='zone: white slot squares inside the destination (static map) count as zone')
    p.add_argument('--reach-mode',choices=REACH_MODES,default='calibrated_mid_v1',help='pad_window_v2: approach to the measured pick-feasible IK window')
    p.add_argument('--held-object',choices=HELD_OBJECT_MODES,default='visible_v0',help='hidden_v1: held cargo world pose never enters decisions while held')
    p.add_argument('--lookaround',choices=LOOKAROUND_MODES,default='off',help='setdown_lookaround_v1: after the backoff step, look toward static-map landmarks chosen from the own pose estimate (640x480 own camera)');a=p.parse_args()
    if not 0<a.cap_s<=180:raise ValueError('finite cap required')
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan,a.out,cap_s=a.cap_s,own_pose_source=a.own_pose_source,observe_mode=a.observe_mode,render_dr=a.render_dr,zone_slots=a.zone_slots,reach_mode=a.reach_mode,held_object=a.held_object,lookaround=a.lookaround,pose_anchor=a.pose_anchor,placement=a.placement,lateral_recovery=a.lateral_recovery,active_recovery=a.active_recovery,command_motion=a.command_motion,localization_support=a.localization_support,regrasp_check=a.regrasp_check,regrasp_recovery=a.regrasp_recovery,release_profile=a.release_profile,record_training=a.record_training),ensure_ascii=False,default=str))
if __name__=='__main__':main()
