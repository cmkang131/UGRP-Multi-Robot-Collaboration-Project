"""Opt-in calibrated coupled pulse port and evaluation-only force/slip evidence."""
import math
import numpy as np
from sim.s3_stage_safety import PhysicsBackend as Previous
from sim.s3_motion_ports import PairPhasePort
from sim.s2_align_pulse import FinePulsePort
from harness.zone_s3_synchronized_carry import OPTION


class CarryPulsePort(PairPhasePort):
    def apply(self,action,sim_time):
        if self.coupled() and action.get('kind')=='mecanum' and any(action.get(k,0.) for k in ('forward','left','turn')):
            if action.get('turn',0.):raise ValueError('coupled pulse may translate/crab, never heading turn')
            return FinePulsePort.apply(self,action,sim_time)
        return super().apply(action,sim_time)


class PhysicsBackend(Previous):
    def reset(self,cap):
        elapsed=super().reset(cap)
        option=self.bundle['synchronized_carry']['option']
        if option=='off':return elapsed
        if option!=OPTION:raise ValueError('unknown carry option')
        for rid in ('r1','r2'):
            self.ports[rid]=CarryPulsePort(self.world,rid,
                coupled=lambda:all(self.commands.get(r,{}).get(1,2000)<=1600 for r in ('r1','r2')),
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        return elapsed

    def eval_sample(self):
        super().eval_sample()
        if self.bundle['synchronized_carry']['option']=='off':return
        import mujoco
        m,d=self.world.model,self.world.data
        item=next(k for k,v in self.objects.items() if v['kind']=='long_beam')
        geoms=self._box_geom[item];forces={r:dict(force_world_n=np.zeros(3),normal_sum_n=0.,contacts=0) for r in ('r1','r2')}
        for i,c in enumerate(d.contact[:d.ncon]):
            ids={int(c.geom1),int(c.geom2)}
            if not ids&geoms:continue
            for rid in forces:
                if not ids&(self._fingers[rid][0]|self._fingers[rid][1]):continue
                f=np.zeros(6);mujoco.mj_contactForce(m,d,i,f)
                # Force is on geom2, local frame first axis is the normal.
                on_beam=1. if int(c.geom2) in geoms else -1.
                forces[rid]['force_world_n']+=on_beam*np.asarray(c.frame).reshape(3,3).T@f[:3]
                forces[rid]['normal_sum_n']+=float(f[0]);forces[rid]['contacts']+=1
        scored=item if self.bundle['case']=='pair' else next(k for k,v in self.objects.items() if v['kind']=='cyan')
        body=d.body(self.objects[scored]['body_name'])
        robots={}
        for rid in ('r1','r2'):
            joints=[m.joint(f'{rid}__wheel_{w}_joint') for w in ('fl','fr','rl','rr')]
            robots[rid]=dict(wheel_qpos_rad=[float(d.qpos[j.qposadr[0]]) for j in joints],
                wheel_qvel_rad_s=[float(d.qvel[j.dofadr[0]]) for j in joints],
                force_world_n=forces[rid]['force_world_n'].tolist(),normal_sum_n=forces[rid]['normal_sum_n'],
                contacts=forces[rid]['contacts'])
        self._append('eval_only/cooperative-dynamics.jsonl',dict(t=self.now,robots=robots,
            cargo_tilt_deg=math.degrees(math.acos(float(np.clip(body.xmat[8],-1,1)))),
            cargo_z_m=float(body.xipos[2]),controller_feedback=False))
