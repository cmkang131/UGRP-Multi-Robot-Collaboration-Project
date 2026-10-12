"""Existing egomap34 physics, with write-only sampled contact audit."""
from sim.active_wall_map import PhysicsBackend as Base


class PhysicsBackend(Base):
    def eval_sample(self):
        import mujoco
        m,d=self.world.model,self.world.data
        pairs=[]
        for c in d.contact[:d.ncon]:
            names=[mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,int(i)) or '' for i in (c.geom1,c.geom2)]
            if not any(n.startswith('r3__') for n in names):continue
            kind='wall' if any('wall' in n for n in names) else 'robot' if any(n.startswith(('r1__','r2__')) for n in names) else None
            if kind:pairs.append(dict(kind=kind,geoms=names,distance=float(c.dist)))
        self._append('eval_only/contact-audit.jsonl',dict(t=self.now,pairs=pairs))
        super().eval_sample()  # retain original wall/tilt/nonfinite failure boundary
