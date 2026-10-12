"""Default-off evaluation-only cyan COM/contact supervisor; S3 files unchanged."""
from sim.s4_pair_live8 import PhysicsBackend as Previous
from sim.s4_beam_drop_guard import DropGuard
from sim.s3_stage_safety import check_cyan
from sim.zone_s3_no_prior import PhysicalStop

MODE='contact_com_v1'


def supported_height_stop(row, *, allow_floor=False):
    return bool(not row['drop'] and (allow_floor and row.get('floor_contact')
        or row['finger_contact'] and row['bilateral_finger_contact']))


class FloorSupportedGuard:
    """Evaluation-only release witness; delegate retains airborne loss and tilt."""
    def __init__(self, guard, com_row, append):
        self.guard,self.com_row,self.append=guard,com_row,append

    def check(self, row, *, release_allowed):
        floor=bool(self.com_row['floor_contact'] and not self.com_row['drop'])
        self.append('eval_only/r3/release-supervisor.jsonl',dict(t=row['t'],
            release_allowed_from_command=release_allowed,release_allowed_by_floor=floor,
            floor_contact=self.com_row['floor_contact'],drop=self.com_row['drop'],feedback_to_controller=False))
        return self.guard.check(row,release_allowed=release_allowed or floor)


class PhysicsBackend(Previous):
    def setdown_row(self):
        row=super().setdown_row();self._pending_beam_setdown=row;return row

    def cyan_row(self):
        import mujoco
        m,d=self.world.model,self.world.data
        item=next(k for k,v in self.objects.items() if v['kind']=='cyan');geoms=self._box_geom[item]
        fingers=[False,False];floor=False
        for c in d.contact[:d.ncon]:
            pair={int(c.geom1),int(c.geom2)}
            if not pair&geoms:continue
            for i,fg in enumerate(self._fingers['r3']):fingers[i]|=bool(pair&fg)
            floor|=any((mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,g) or '')=='floor' for g in pair-geoms)
        body=d.body(self.objects[item]['body_name'])
        guard=self.__dict__.setdefault('_s4_cyan_com_guard',DropGuard())
        row=guard.observe(t=self.now,com_z=float(body.xipos[2]),origin_z=float(body.xpos[2]),
            finger_contact=any(fingers),floor_contact=floor)
        return dict(item=item,**row,bilateral_finger_contact=all(fingers),finger_contacts=fingers,
            controller_feedback=False)

    def eval_sample(self):
        mode=self.bundle.get('cyan_drop_supervisor','off')
        if mode=='off':return super().eval_sample()
        if mode!=MODE:raise ValueError('unknown cyan supervisor')
        row=self.cyan_row();self._append('eval_only/r3/com-contact-supervisor.jsonl',row)
        original_guard=self.stage_cyan_guard
        if self.bundle.get('cyan_floor_support',False):
            self.stage_cyan_guard=FloorSupportedGuard(original_guard,row,self._append)
        try:
            try:super().eval_sample()
            except PhysicalStop as exc:
                if str(exc)!='LOAD_DROP:cyan_1' or not supported_height_stop(row,
                        allow_floor=self.bundle.get('cyan_floor_support',False)):raise
                # Resume interrupted evaluation only; never a controller call.
                self._append('eval_only/r3/height-stop-classification.jsonl',dict(**row,
                    original_guard=str(exc),classification='floor_supported_height_stop' if row.get('floor_contact')
                        and self.bundle.get('cyan_floor_support',False) else 'bilaterally_supported_height_stop',free_fall=False))
                self.record_dynamics()
                self._append('eval_only/setdown.jsonl',self._pending_beam_setdown)
                self.progress()
                check_cyan(self,self.stage_cyan_guard)
            if row['drop']:raise PhysicalStop('LOAD_DROP:cyan_1')
        finally:self.stage_cyan_guard=original_guard
