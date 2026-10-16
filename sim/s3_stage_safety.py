"""Existing S2 physical abort guard for the new r3 lift/carry stage only."""
import math
import numpy as np
from sim.s3_motion_ports import PhysicsBackend as Previous
from sim.s2_realism import StopGuard, PhysicalStop as SoloStop
from sim.zone_s3_no_prior import PhysicalStop


def check_cyan(host, guard):
    m,d=host.world.model,host.world.data
    item=next(k for k,v in host.objects.items() if v['kind']=='cyan')
    body=d.body(host.objects[item]['body_name'])
    robot=d.body('r3__robot')
    geoms=host._box_geom[item]
    contact=[False,False]
    for c in d.contact[:d.ncon]:
        pair={int(c.geom1),int(c.geom2)}
        if pair & geoms:
            for i,fingers in enumerate(host._fingers['r3']): contact[i] |= bool(pair & fingers)
    # This authored cyan is a box; do not substitute a bounding sphere for its bottom.
    if any(int(m.geom_type[g]) != 6 for g in geoms): raise ValueError('cyan stage guard requires box geometry')
    bottom=min(float(d.geom_xpos[g,2]-abs(d.geom_xmat[g].reshape(3,3)[2])@m.geom_size[g]) for g in geoms)
    row=dict(t=host.now,cyan_z_m=float(body.xipos[2]),cyan_min_z_m=bottom,
        finger_contacts=contact,robot_tilt_deg=math.degrees(math.acos(float(np.clip(robot.xmat[8],-1,1)))),
        release_allowed=host.commands['r3'].get(1,2000)>=2000,feedback_to_controller=False)
    host._append('eval_only/r3/physical-supervisor.jsonl',row)
    try: guard.check(row,release_allowed=row['release_allowed'])
    except SoloStop as e: raise PhysicalStop(str(e)) from e


class PhysicsBackend(Previous):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.stage_cyan_guard=StopGuard()

    def eval_sample(self):
        super().eval_sample()
        if self.bundle['case']=='cyan': check_cyan(self,self.stage_cyan_guard)
