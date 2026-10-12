"""Existing egomap31 plant plus write-only wheel measurements. No physics changes."""
from sim.active_wall_map import PhysicsBackend as Previous


class PhysicsBackend(Previous):
    def eval_sample(self):
        super().eval_sample()
        m,d=self.world.model,self.world.data
        c=self.world.robot('r3')
        ids=c.wheel_act
        joints=m.actuator_trnid[ids,0]
        self._append('eval_only/wheels.jsonl',dict(t=self.now,
            command=c.motor_command.tolist(),torque=d.ctrl[ids].tolist(),
            q_rad=d.qpos[m.jnt_qposadr[joints]].tolist(),
            qvel_rad_s=d.qvel[m.jnt_dofadr[joints]].tolist(),contacts=int(d.ncon)))
