"""Write-only 20 Hz wall contact evidence, never a controller observation."""


def category(names, rid):
    if not any(any(k in n for k in ('wall', 'divider', 'door')) for n in names):
        return None
    own = next((n for n in names if n.startswith(rid+'__')), None)
    if own:
        return 'finger' if 'finger' in own else 'wheel' if 'wheel_' in own else 'body'
    if any('cargo_box_00' in n for n in names):
        return 'cargo'
    return None


def backend_class(base):
    class Backend(base):
        def eval_sample(self):
            super().eval_sample()
            import mujoco
            import numpy as np
            m, d = self.world.model, self.world.data
            contacts = []
            for i in range(d.ncon):
                con = d.contact[i]
                names = [m.geom(int(g)).name or '' for g in con.geom]
                kind = category(names, self.rid)
                if kind:
                    force = np.zeros(6)
                    mujoco.mj_contactForce(m, d, i, force)
                    contacts.append(dict(category=kind, geoms=names,
                        distance_m=float(con.dist), normal_force_n=float(force[0])))
            self._append('eval_only/wall-contacts.jsonl', dict(t=self.now,
                controller_feedback=False, sample_interval_s=.05, contacts=contacts))
    return Backend
