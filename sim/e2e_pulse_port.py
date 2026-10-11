"""Opt-in E2E fractional expiry at the native actuator port; no physics runner."""
import math
from sim.s3_synchronized_carry import CarryPulsePort
from harness.e2e_pulse_budget import OPTIONS


class ResidualPulsePort(CarryPulsePort):
    def __init__(self, *args, pulse_budget='off', authorize_pulse=None, **kwargs):
        if pulse_budget not in OPTIONS: raise ValueError('UNKNOWN_E2E_PULSE_BUDGET')
        if pulse_budget != 'off' and not callable(authorize_pulse):
            raise ValueError('CURRENT_GO_AND_SCHEDULE_AUTHORIZER_REQUIRED')
        super().__init__(*args, **kwargs)
        self.pulse_budget, self.authorize_pulse = pulse_budget, authorize_pulse

    def apply(self, action, sim_time):
        moving = action.get('kind') == 'mecanum' and any(action.get(k, 0.) for k in ('forward', 'left', 'turn'))
        if self.pulse_budget == 'off' or not moving or not self.coupled():
            return super().apply(action, sim_time)
        if set(action) != {'kind', 'forward', 'left', 'turn', 'duration_s'}:
            raise ValueError('EXACT_RESIDUAL_PULSE_FIELDS_REQUIRED')
        f, l, t, duration = (float(action[k]) for k in ('forward', 'left', 'turn', 'duration_s'))
        if not all(math.isfinite(v) for v in (f, l, t, duration, sim_time)):
            raise ValueError('FINITE_RESIDUAL_PULSE_REQUIRED')
        if t or bool(f) == bool(l) or not 0 < duration <= (.1 if f else .65):
            raise ValueError('RESIDUAL_TRANSLATION_ONLY')
        if (f and abs(f) != .35) or (l and abs(l) != .65):
            raise ValueError('CALIBRATED_RESIDUAL_SPEED_REQUIRED')
        if not self.authorize_pulse(action, sim_time):
            raise ValueError('RESIDUAL_PULSE_GO_OR_SCHEDULE_MISMATCH')
        self._command_expires_at = None
        self._set_motors((f-l, f+l, f+l, f-l))
        self._drive_expires_at = float(sim_time)+duration
        self._busy_until = self._drive_expires_at
        return dict(ok=True, robot_id=self.robot_id, kind='mecanum', sim_time=float(sim_time),
                    busy_until=self._busy_until, actuator_state=self._actuator_state())
