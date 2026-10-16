"""Evaluation-only supported-lowering classification and live DEV progress receipts."""
import json,math
import numpy as np
from sim.s3_synchronized_carry import PhysicsBackend as Previous
from sim.zone_s3_no_prior import PhysicalStop

LIMITS=dict(max_supported_descent_m_s=.12,max_cargo_tilt_deg=10.,min_floor_normal_n=.1)


def supported_lower(row):
    phases=row['states'].values()
    if set(row['states'])!={'r1','r2'} or not all(s in ('lower','wait_open','cp_open') for s in phases):return False
    if set(row['fingers'])!={'r1','r2'} or any(len(v)!=2 for v in row['fingers'].values()):return False
    if not math.isfinite(row['vertical_speed_m_s']) or abs(row['vertical_speed_m_s'])>LIMITS['max_supported_descent_m_s']:return False
    if not math.isfinite(row['cargo_tilt_deg']) or row['cargo_tilt_deg']>=LIMITS['max_cargo_tilt_deg']:return False
    held=all(all(v) for v in row['fingers'].values())
    # Losing a grasp during lower still stops. Floor support replaces the
    # grip witness only after both command-side floor contracts verified.
    release_floor=(all(s in ('wait_open','cp_open') for s in phases)
        and row['floor_normal_n']>=LIMITS['min_floor_normal_n'])
    return held or release_floor


class PhysicsBackend(Previous):
    states_getter=None
    def setdown_row(self):
        import mujoco
        m,d=self.world.model,self.world.data
        item=next(k for k,v in self.objects.items() if v['kind']=='long_beam');geoms=self._box_geom[item]
        fingers={r:[False,False] for r in ('r1','r2')};ground_n=0.
        for i,c in enumerate(d.contact[:d.ncon]):
            ids={int(c.geom1),int(c.geom2)}
            if not ids&geoms:continue
            for rid in fingers:
                for j,fg in enumerate(self._fingers[rid]):fingers[rid][j]|=bool(ids&fg)
            others=ids-geoms
            if any(any(s in (mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,g) or '') for s in ('floor','ground','terrain')) for g in others):
                f=np.zeros(6);mujoco.mj_contactForce(m,d,i,f);ground_n+=max(0.,float(f[0]))
        body=d.body(self.objects[item]['body_name']);z=float(body.xipos[2]);old=getattr(self,'previous_setdown_z',None)
        vz=0. if old is None else (z-old[1])/(self.now-old[0]) if self.now>old[0] else 0.
        self.previous_setdown_z=(self.now,z)
        states=self.states_getter() if self.states_getter else {}
        return dict(t=self.now,states=states,fingers=fingers,floor_normal_n=ground_n,cargo_z_m=z,
            body_origin_z_m=float(body.xpos[2]),vertical_speed_m_s=vz,
            cargo_tilt_deg=math.degrees(math.acos(float(np.clip(body.xmat[8],-1,1)))),controller_feedback=False)

    def progress(self):
        if self.now<getattr(self,'next_progress_s',0.):return
        self.next_progress_s=self.now+1.
        m,d=self.world.model,self.world.data
        row=dict(t=self.now,frame_count=self.frame,states=self.states_getter() if self.states_getter else {},robots={})
        for rid in ('r1','r2'):
            row['robots'][rid]=dict(base_xyz_m=d.body(rid+'__robot').xpos.tolist(),
                finger_xyz_m=np.mean([d.geom(next(iter(f))).xpos for f in self._fingers[rid]],axis=0).tolist(),
                issued=dict(self.commands.get(rid,{})))
        # Small, flushed progress trace is excluded from controller input.
        p=self.out/'progress.jsonl'
        with p.open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
        if (self.out.parent/'STOP_REQUEST').exists():raise RuntimeError('DEV_INITIAL_CHECK_STOP')

    def eval_sample(self):
        row=self.setdown_row()
        try:super().eval_sample()
        except PhysicalStop as e:
            if (self.bundle['setdown']['option']=='off' or str(e)!='LOAD_DROP:beam_1' or not supported_lower(row)):raise
            self._append('eval_only/setdown-classification.jsonl',dict(**row,
                original_guard=str(e),classification='supported_commanded_lowering',free_fall=False))
            self.record_dynamics()
        self._append('eval_only/setdown.jsonl',row)
        self.progress()
