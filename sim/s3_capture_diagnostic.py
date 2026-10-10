"""Evaluation-only low-speed actuator measurement; no student may use it."""
import math
from sim.s3_motion_ports import PairPhasePort
from sim.s3_stage_safety import PhysicsBackend as Previous

OPTION = 'eval_low_pulse_v1'
LEVELS = (.15, .20, .25, .35)


class DiagnosticPort(PairPhasePort):
    def apply(self, action, sim_time):
        if action.get('kind') == 'mecanum':
            if set(action) != {'kind', 'forward', 'left', 'turn', 'duration_s'}:
                raise ValueError('diagnostic primitive fields')
            f, l, t, dt = (float(action[k]) for k in ('forward','left','turn','duration_s'))
            if not all(math.isfinite(x) for x in (f,l,t,dt,sim_time)):
                raise ValueError('nonfinite diagnostic command')
            if sum(x != 0 for x in (f,l,t)) != 1 or dt != .10 or max(map(abs,(f,l,t))) not in LEVELS:
                raise ValueError('diagnostic requires one axis, registered speed, 100ms')
            self._command_expires_at = None
            self._set_motors((f-l-t,f+l+t,f+l-t,f-l+t))
            self._drive_expires_at = float(sim_time)+dt
            self._busy_until = self._drive_expires_at
            return dict(ok=True,robot_id=self.robot_id,kind='mecanum',sim_time=float(sim_time),
                        busy_until=self._busy_until,actuator_state=self._actuator_state())
        return super().apply(action,sim_time)


class PhysicsBackend(Previous):
    def reset(self, cap):
        mode=self.bundle.get('diagnostic_low_pulse','off')
        if mode not in ('off',OPTION): raise ValueError('unknown diagnostic capability')
        if mode != 'off' and self.bundle.get('student_control') is not False:
            raise ValueError('low-speed diagnostic forbids student control')
        elapsed=super().reset(cap)
        if mode == 'off': return elapsed
        for rid in self.ports:
            self.ports[rid]=DiagnosticPort(self.world,rid,coupled=lambda:False,
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        return elapsed
