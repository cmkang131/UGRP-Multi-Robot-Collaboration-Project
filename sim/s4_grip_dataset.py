"""Evaluation-only environment perturbations; never imported by RGB detection."""
import base64
import math
import numpy as np
from sim.s3_capture_diagnostic import PhysicsBackend as Previous
from sim.final_environment_checks import PhysicsBackend as ContactAudit
from sim.zone_s3_no_prior import PhysicalStop
from harness.zone_s2_realism_contract import SAFETY


class PhysicsBackend(Previous):
    def eval_sample(self):
        # Intentional drop is the diagnostic target, not a run-ending failure.
        # Preserve weld, finite-state and robot-tilt checks. No controller exists.
        ContactAudit.eval_sample(self)
        d = self.world.data
        if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all():
            raise PhysicalStop('NONFINITE_STATE')
        for rid in self.ports:
            tilt = math.degrees(math.acos(float(np.clip(d.body(rid+'__robot').xmat[8], -1, 1))))
            if tilt >= SAFETY['robot_tilt_limit_deg']:
                raise PhysicalStop('ROBOT_TILT_LIMIT:'+rid)

    def capture_one(self, rid, relative_s):
        obs = self.ports[rid].capture()
        jpeg = base64.b64decode(obs['image'], validate=True)
        relative = f'robots/{rid}/rgb/{self.frame:05d}.jpg'
        path = self.out/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)
        self._append(f'robots/{rid}/frames.jsonl',
                     {**{k:v for k,v in obs.items() if k != 'image'}, 'path':relative,
                      'relative_s':relative_s, 'commanded_servo':dict(self.commands[rid])})
        self.frame += 1

    def label(self, rid, relative_s):
        kind = 'cyan' if rid == 'r3' else 'long_beam'
        item = next(k for k,v in self.objects.items() if v['kind'] == kind)
        sides = [False, False]
        for c in self.world.data.contact[:self.world.data.ncon]:
            if c.dist > 0: continue
            pair = {int(c.geom1), int(c.geom2)}
            if pair & self._box_geom[item]:
                for i,f in enumerate(self._fingers[rid]): sides[i] |= bool(pair & f)
        self._append('eval_only/labels.jsonl', dict(sim_time=self.now, relative_s=relative_s,
                     finger_sides=sides, label='held' if all(sides) else 'partial' if any(sides) else 'zero',
                     object_com_z_m=float(self.world.data.body(self.objects[item]['body_name']).xipos[2]),
                     feedback_to_controller=False))


class Perturbation:
    def __init__(self, host, rid, case):
        self.host, self.case = host, case
        owners = ('r3',) if rid == 'r3' else ('r1','r2')
        self.actuators = [aid for r in owners for aid in host.world.robot(r).gripper_act]
        self.original = host.world.model.actuator_forcerange[self.actuators].copy()
        kind = 'cyan' if rid == 'r3' else 'long_beam'
        obj = next(v for v in host.objects.values() if v['kind'] == kind)
        self.body = host.world.model.body(obj['body_name']).id
        self.started = False

    def apply(self, relative_s):
        c = self.case
        active = c['variant'] == 'loss' and relative_s+1e-8 >= c['onset_s']
        if active and not self.started:
            self.host.world.model.actuator_forcerange[self.actuators] = self.original*.001
            self.started = True
            self.host._append('eval_only/perturbations.jsonl', dict(**c, actual_onset_sim_s=self.host.now,
                actuator_ids=self.actuators, original_forcerange=self.original.tolist(), force_scale=.001,
                mechanism='motor-force limitation plus external cargo force; no issued-command change', feedback_to_controller=False))
        f = self.host.world.data.xfrc_applied[self.body]
        f[:] = 0.
        if active and relative_s < c['onset_s']+.6-1e-8:
            f[:2] = c['force_xy_n']
