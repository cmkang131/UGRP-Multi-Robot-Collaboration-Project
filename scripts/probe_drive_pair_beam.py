"""One fixed paired-beam perturbation, standard Scene and v92 teacher staging.

Invoked only by the managed friction probe with its host lock already held.
Truth is evaluation/abort only; no pose feedback, weld or direction correction.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path

import numpy as np

ROBOTS = ('r1', 'r2')
SEED = 1601
DRIVE_S, STOP_S = .5, 1.
WHEEL_INPUT = 35
# Existing catalogue probe robot limit; same conservative DEV limit for beam.
TILT_LIMIT_DEG = 10.


def design():
    from harness.zone_final_pair_excitation import LOADED_BEAM_POSE, MAP_ID
    from harness.zone_pair_highpose_staging import PREROLLS
    from scripts.cargo_formation_teacher import FINGER_MIN_N
    from scripts.zone_team_teacher import GRIP_LOST_S, LIFT_CLEAR_Z_M
    return dict(schema='ugrp.drive_pair_beam.v1', seed=SEED, map=MAP_ID,
        beam_pose=list(LOADED_BEAM_POSE), beam_kind='long_beam', mass_kg=.3,
        contact_profile='cargo_noslip_v1', staging=PREROLLS['high_held'],
        command={'r1':[-.35,.35,.35,-.35], 'r2':[0.,0.,0.,0.]},
        drive_s=DRIVE_S, stop_s=STOP_S, sample_s=.01,
        finger_min_n=FINGER_MIN_N, grip_lost_s=GRIP_LOST_S,
        lift_clear_m=LIFT_CLEAR_Z_M, drop_floor_m=.005, tilt_limit_deg=TILT_LIMIT_DEG,
        qualification='one asymmetric command comparison, not equal speed/force or mission success')


class PhysicalStop(RuntimeError):
    pass


class StopGuard:
    """Abort-only, existing teacher contact threshold/debounce and floor bound."""
    def __init__(self, plan):
        self.plan=plan; self.lifted=False; self.lost_since={}

    def check(self, row):
        p=self.plan
        if max([row['beam_tilt_deg'], *row['robot_tilt_deg'].values()]) >= p['tilt_limit_deg']:
            raise PhysicalStop('TILT_LIMIT')
        self.lifted |= row['beam_min_z_m'] > p['lift_clear_m']
        if not self.lifted:
            return
        if row['beam_min_z_m'] < p['drop_floor_m'] or row['beam_floor_contacts']:
            raise PhysicalStop('LOAD_DROP')
        for rid in ROBOTS:
            if min(row['finger_n'][rid]) < p['finger_min_n']:
                self.lost_since.setdefault(rid,row['t'])
                if row['t']-self.lost_since[rid] > p['grip_lost_s']:
                    raise PhysicalStop('GRIP_LOSS_'+rid)
            else:
                self.lost_since.pop(rid,None)


def deltas(start, row):
    progress={r:row['robot_xyz'][r][1]-start['robot_xyz'][r][1] for r in ROBOTS}
    yaw=math.atan2(math.sin(row['beam_yaw_rad']-start['beam_yaw_rad']),
                   math.cos(row['beam_yaw_rad']-start['beam_yaw_rad']))
    return dict(beam_delta_m=(np.array(row['beam_xyz'])-start['beam_xyz']).tolist(),
        beam_yaw_change_deg=math.degrees(yaw), robot_progress_m=progress,
        progress_difference_m=progress['r1']-progress['r2'],
        robot_delta_m={r:(np.array(row['robot_xyz'][r])-start['robot_xyz'][r]).tolist() for r in ROBOTS},
        grip_slip_m={r:float(np.linalg.norm(np.array(row['grip_in_beam_m'][r])-start['grip_in_beam_m'][r])) for r in ROBOTS})


class Recorder:
    def __init__(self,world,plan):
        import mujoco
        self.mj=mujoco; self.world=world; self.plan=plan; self.trace=[]
        self.guard=StopGuard(plan); self.phase='prepare'; self.start_t=float(world.data.time)
        m=world.model
        self.beam=m.body('cargo_beam').id
        self.bar=m.geom('cargo_beam__bar').id
        self.floor=m.geom('floor').id
        self.fingers={m.geom(f'{r}__{side}_finger').id:(r,i)
                      for r in ROBOTS for i,side in enumerate(('left','right'))}
        self.cargo={i for i in range(m.ngeom) if m.geom_bodyid[i]==self.beam and m.geom_contype[i]}

    def sample(self):
        m,d=self.world.model,self.world.data
        if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all():
            raise PhysicalStop('NONFINITE_STATE')
        body=d.body(self.beam);mat=body.xmat.reshape(3,3)
        tilt=lambda a:math.degrees(math.acos(float(np.clip(a.reshape(3,3)[2,2],-1,1))))
        finger={r:[0.,0.] for r in ROBOTS};floor=0;force=np.zeros(6)
        for i in range(d.ncon):
            c=d.contact[i]
            for a,b in ((c.geom1,c.geom2),(c.geom2,c.geom1)):
                if b not in self.cargo:continue
                if a==self.floor:floor+=1
                if a in self.fingers:
                    self.mj.mj_contactForce(m,d,i,force)
                    rid,k=self.fingers[a];finger[rid][k]+=abs(float(force[0]))
        bar_mat=d.geom_xmat[self.bar].reshape(3,3)
        # Exact lowest corner height for the catalogue's box beam.
        minz=float(d.geom_xpos[self.bar,2]-abs(bar_mat[2])@m.geom_size[self.bar])
        row=dict(t=float(d.time)-self.start_t,phase=self.phase,
            beam_xyz=body.xpos.tolist(),beam_yaw_rad=math.atan2(mat[1,0],mat[0,0]),
            beam_tilt_deg=tilt(body.xmat),beam_min_z_m=minz,beam_floor_contacts=floor,
            finger_n=finger, robot_xyz={r:self.world.robot(r).base_xyz().tolist() for r in ROBOTS},
            robot_yaw_rad={r:self.world.robot(r).base_rpy()[2] for r in ROBOTS},
            robot_tilt_deg={r:tilt(d.body(r+'__robot').xmat) for r in ROBOTS},
            grip_in_beam_m={r:(mat.T@((d.geom(f'{r}__left_finger').xpos+d.geom(f'{r}__right_finger').xpos)/2-body.xpos)).tolist() for r in ROBOTS},
            wheel_command={r:self.world.robot(r).motor_command.tolist() for r in ROBOTS},
            base_external_force={r:d.xfrc_applied[self.world.robot(r).robot_bid].tolist() for r in ROBOTS})
        self.trace.append(row);self.guard.check(row)
        return row


class StageAdapter:
    """Only adapts the unchanged high_held schedule to a headless world."""
    def __init__(self,world,rec):
        from sim.camera_robot_port import CameraRobotPort
        self.world,self.rec=world,rec;self.epoch=float(world.data.time);self.step=0
        self.dt=float(world.model.opt.timestep);self.deadline=self.epoch
        self.ports={r:CameraRobotPort(world,r) for r in ROBOTS}
        self.commands={r:dict(world.robot(r).servo_command_pulses) for r in ROBOTS}
        self.issued=[]

    @property
    def now(self):return self.epoch+self.step*self.dt

    def set_deadline(self,t):self.deadline=t

    def issue(self,rid,action):
        self.ports[rid].apply(action,self.now)
        sid=6 if action['kind']=='look' else action['servo_id']
        pulse=action['pan_pulse'] if sid==6 else action['pulse']
        self.commands[rid][sid]=pulse
        self.issued.append(dict(t=self.now-self.epoch,robot_id=rid,action=action))

    def advance_to(self,t):
        if not self.now-1e-8<=t<=self.deadline+1e-8:raise ValueError('stage deadline')
        target=round((t-self.epoch)/self.dt)
        if abs(self.epoch+target*self.dt-t)>1e-8:raise ValueError('nonintegral stage time')
        while self.step<target:
            for p in self.ports.values():p.tick(self.now)
            self.world._physics_step_for(self.world.robot('r1'))
            self.step+=1
            if self.step%max(1,round(.01/self.dt))==0:self.rec.sample()


def run_pair_case(profile,output:Path):
    import mujoco
    from sim.zone_final_v3_scene import FinalV3Scene,build_world as legacy
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from harness.zone_pair_highpose_staging import stations,run_preroll
    from scripts.probe_masterpi_drive_friction import write
    if profile not in ('legacy_wrench',PROFILE):raise ValueError('pair comparison requires legacy or v7')
    plan=design();output.mkdir();world=None;rec=None;stage=None;start=None;drive_issued=[]
    result=dict(case='pair_beam',profile=profile,status='HOST_ERROR',model_calls=0,physical_success=None,
        loaded=True,design=plan,design_sha256=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest(),
        loadavg_start=os.getloadavg(),qualification='TEST_SETUP_GT fixed teacher staging; abort-only truth; one DEV perturbation, not student/hardware success')
    wall0=time.perf_counter()
    try:
        scene=FinalV3Scene.from_spec(dict(map=plan['map'],seed=SEED,goal={'B':{'cyan':1}},extra_boxes={},
            team_cargo=[dict(item_id='beam',kind='long_beam',pose=plan['beam_pose'])]),'local_contact_fine')
        for r,(x,y,yaw) in stations(scene.config['static_map'],plan['beam_pose']).items():
            scene.config['setup_only']['spawns'][r]=[x,y,.0325,yaw]
        kwargs=dict(seed=SEED,render=False,warehouse_layout=scene.engine_layout,use_calibration_manifest=False)
        world=build_world(scene,drive_profile=PROFILE,**kwargs) if profile==PROFILE else legacy(scene,'cargo_noslip_v1',initial_sim_cap_s=45.,**kwargs)
        scene.setup(world);m,d=world.model,world.data
        active_welds=[i for i in range(m.neq) if m.eq_type[i]==mujoco.mjtEq.mjEQ_WELD and d.eq_active[i]]
        if active_welds:raise ValueError('weld must be OFF')
        rec=Recorder(world,plan);stage=StageAdapter(world,rec)
        result.update(scene=scene.record(),active_welds=active_welds,dt=float(m.opt.timestep),
            measurement_alignment='mj_step force/pose fields precede integration by at most one dt',
            drive_parameters=getattr(world,'drive_profile_record',None),cargo_mass_kg=float(m.body_mass[rec.beam]),
            robot_mass_kg={r:float(world.robot(r).robot_mass_kg) for r in ROBOTS},
            legacy_dynamics={r:dict(world.robot(r).dynamics) for r in ROBOTS} if profile=='legacy_wrench' else None,
            xml_sha256=hashlib.sha256(world.scene_xml.encode()).hexdigest())
        (output/'scene.xml').write_text(world.scene_xml)
        result['staging']=run_preroll(stage,'high_held')
        start=rec.sample()
        if start['beam_min_z_m']<=plan['lift_clear_m'] or any(min(start['finger_n'][r])<plan['finger_min_n'] for r in ROBOTS):
            raise PhysicalStop('STAGING_NOT_HELD')
        result['motion_start']=start
        dt=float(m.opt.timestep);n=round((DRIVE_S+STOP_S)/dt);pulse=round(DRIVE_S/dt)
        for i in range(n):
            rec.phase='drive' if i<pulse else 'stop'
            if i in (0,pulse):
                commands={r:plan['command'][r] if i<pulse else [0.]*4 for r in ROBOTS}
                for r in ROBOTS:world.robot(r).set_motor_commands(commands[r])
                drive_issued.append(dict(t=i*dt,phase=rec.phase,wheel_commands=commands))
            world._physics_step_for(world.robot('r1'))
            if (i+1)%max(1,round(.01/dt))==0:rec.sample()
        result['status']='MEASURED_DEV'
    except PhysicalStop as exc:
        result.update(status='PHYSICS_FAILURE',stop_reason=str(exc),failure_phase=rec.phase if rec else 'construction')
    except Exception as exc:
        result['error']=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        if world is not None:
            for c in world.controllers.values():c.set_motor_commands(np.zeros(4))
            result['warnings']={mujoco.mjtWarning(i).name:int(world.data.warning[i].number) for i in range(len(world.data.warning)) if world.data.warning[i].number}
            if rec is not None:
                result['sim_s']=float(world.data.time)-rec.start_t
                result['last_sample']=rec.trace[-1] if rec.trace else None
                if start is not None and 'motion_start' in result:
                    motion=[r for r in rec.trace if r['phase'] in ('drive','stop')]
                    if motion:
                        change=[deltas(start,r) for r in motion]
                        result.update(final=deltas(start,motion[-1]),
                            peak_beam_xy_m=max(math.hypot(*c['beam_delta_m'][:2]) for c in change),
                            peak_abs_yaw_deg=max(abs(c['beam_yaw_change_deg']) for c in change),
                            peak_abs_progress_difference_m=max(abs(c['progress_difference_m']) for c in change),
                            max_grip_slip_m={r:max(c['grip_slip_m'][r] for c in change) for r in ROBOTS})
                write(output/'trace.json',rec.trace)
            if stage is not None:
                write(output/'staging-commands.json',stage.issued)
                write(output/'drive-commands.json',drive_issued)
                result['commands']=len(stage.issued)+2*len(drive_issued)
                result['command_count_scope']='scheduled per-robot arm actions and wheel command batches, excludes final cleanup stop'
            world.close()
        result.update(wall_s=time.perf_counter()-wall0,loadavg_end=os.getloadavg())
        if result.get('sim_s'):result['wall_per_sim']=result['wall_s']/result['sim_s']
        write(output/'result.json',result)
    return result
