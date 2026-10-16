"""Explicit fine-pulse capability and reset lifecycle; all prior ports unchanged."""
import math
from sim.s2_real_output import RealPrimitivePort


class FinePulsePort(RealPrimitivePort):
    def __init__(self, *args, alignment_pulse='off', **kwargs):
        if alignment_pulse not in ('off', 'real_fine_v1'):
            raise ValueError('unsupported alignment_pulse')
        super().__init__(*args, **kwargs)
        self.alignment_pulse = alignment_pulse

    def apply(self, action, sim_time):
        if self.alignment_pulse == 'off' or action['kind'] != 'mecanum' or action.get('duration_s') != .06:
            return super().apply(action, sim_time)
        if self.min_wheel_cmd != 'real_v1' or set(action) != {'kind','forward','left','turn','duration_s'}:
            raise ValueError('fine pulse requires explicit real output and exact fields')
        f,l,t = [float(action[k]) for k in ('forward','left','turn')]
        if not all(math.isfinite(v) for v in (f,l,t,sim_time)) or sum(v != 0 for v in (f,l,t)) != 1:
            raise ValueError('fine pulse requires one finite axis')
        if any(v and abs(v) != .35 for v in (f,l,t)):
            raise ValueError('fine pulse requires fixed 35 speed')
        self._command_expires_at = None
        self._set_motors((f-l-t,f+l+t,f+l-t,f-l+t))
        self._drive_expires_at = float(sim_time)+.06
        self._busy_until = self._drive_expires_at
        return dict(ok=True,robot_id=self.robot_id,kind='mecanum',sim_time=float(sim_time),
                    busy_until=self._busy_until,actuator_state=self._actuator_state())


def backend_class(base=None):
    if base is None:
        from sim.s2_real_output_reset import backend_class as previous
        base = previous()
    class Backend(base):
        def reset(self, cap):
            elapsed = super().reset(cap)
            option = self.bundle['options'].get('alignment_pulse','off')
            if option != 'off':
                self.ports = {rid:FinePulsePort(self.world,rid,allow_reverse=True,allow_mecanum=True,
                    min_wheel_cmd=self.bundle['options'].get('min_wheel_cmd','off'),alignment_pulse=option)
                    for rid in self.ports}
                if hasattr(self,'out'):
                    from scripts.run_final_environment_checks import write
                    write(self.out/'eval_only/alignment-option.json',dict(option=option,
                        ports={rid:type(p).__name__ for rid,p in self.ports.items()},
                        expiry='native substep port.tick, not 20 Hz control polling'))
            return elapsed
    return Backend
