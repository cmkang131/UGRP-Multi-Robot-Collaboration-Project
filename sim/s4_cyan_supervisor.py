"""Default-off evaluation-only cyan COM/contact supervisor; S3 files unchanged."""
from sim.s4_pair_live8 import PhysicsBackend as Previous
from sim.s4_beam_drop_guard import DropGuard
from sim.s3_stage_safety import check_cyan
from sim.zone_s3_no_prior import PhysicalStop

MODE='contact_com_v1'


def supported_height_stop(row):
    return bool(not row['drop'] and row['finger_contact'] and row['bilateral_finger_contact'])


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
        try:super().eval_sample()
        except PhysicalStop as exc:
            if str(exc)!='LOAD_DROP:cyan_1' or not supported_height_stop(row):raise
            # The legacy S3 threshold interrupted the evaluation chain before
            # these receipts. Resume evaluation only, never a controller call.
            self._append('eval_only/r3/height-stop-classification.jsonl',dict(**row,
                original_guard=str(exc),classification='bilaterally_supported_height_stop',free_fall=False))
            self.record_dynamics()
            self._append('eval_only/setdown.jsonl',self._pending_beam_setdown)
            self.progress()
            check_cyan(self,self.stage_cyan_guard)  # existing tilt and grip-loss guard remains
        if row['drop']:raise PhysicalStop('LOAD_DROP:cyan_1')
