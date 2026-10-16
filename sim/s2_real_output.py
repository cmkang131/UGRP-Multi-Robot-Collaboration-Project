"""Explicit native-wheel output and eval-only stagnation abort. Old ports unchanged."""
import math
from collections import deque
from sim.camera_robot_port import CameraRobotPort


class RealPrimitivePort(CameraRobotPort):
    def __init__(self, *args, min_wheel_cmd='off', **kwargs):
        if min_wheel_cmd not in ('off', 'real_v1'):
            raise ValueError('unsupported min_wheel_cmd')
        super().__init__(*args, **kwargs)
        self.min_wheel_cmd = min_wheel_cmd

    def apply(self, action, sim_time):
        if self.min_wheel_cmd == 'off' or action['kind'] != 'mecanum':
            return super().apply(action, sim_time)
        if set(action) != {'kind', 'forward', 'left', 'turn', 'duration_s'}:
            raise ValueError('unexpected primitive fields')
        f, l, t, duration = [float(action[k]) for k in ('forward', 'left', 'turn', 'duration_s')]
        if not all(math.isfinite(v) for v in (f,l,t,duration,sim_time)):
            raise ValueError('nonfinite primitive')
        if not any((f,l,t)):
            return super().apply(action, sim_time)
        if sum(v != 0 for v in (f,l,t)) != 1 or not .10 <= duration <= .80:
            raise ValueError('REAL primitive requires one axis and bounded duration')
        if (f and abs(f) != .35) or (t and abs(t) != .35) or (l and (abs(l) != .65 or duration < .65)):
            raise ValueError('REAL primitive speed/duration mismatch')
        self._command_expires_at = None
        self._set_motors((f-l-t, f+l+t, f+l-t, f-l+t))
        self._drive_expires_at = float(sim_time)+duration
        self._busy_until = self._drive_expires_at
        return dict(ok=True, robot_id=self.robot_id, kind='mecanum', sim_time=float(sim_time),
                    busy_until=self._busy_until, actuator_state=self._actuator_state())


class StagnationGuard:
    """120 s rolling position envelope <1 cm. Receives eval rows, returns no action."""
    def __init__(self, option='off'):
        if option not in ('off', 'window120_v1'):
            raise ValueError('unsupported stagnation_watch')
        self.option, self.rows = option, deque()

    def check(self, row):
        if self.option == 'off':
            return
        t, xy = float(row['t']), tuple(row['robot_xyz_m'][:2])
        self.rows.append((t,xy))
        while len(self.rows) > 1 and self.rows[1][0] <= t-120.+1e-8:
            self.rows.popleft()
        if t-self.rows[0][0] < 120.-1e-8:
            return
        # Axis-aligned envelope diagonal is an upper bound on pairwise excursion;
        # an out-and-back movement >=1 cm is never mistaken for no displacement.
        extent = [max(p[i] for _,p in self.rows)-min(p[i] for _,p in self.rows) for i in (0,1)]
        if math.hypot(*extent) < .01:
            from sim.s2_realism import PhysicalStop
            raise PhysicalStop('STAGNATION_120S_LT_1CM')


def backend_class():
    from sim.s2_realism_camera_binding import PhysicsBackend as Base
    class Backend(Base):
        def __init__(self, bundle, *args, **kwargs):
            super().__init__(bundle, *args, **kwargs)
            self.ports = {rid: RealPrimitivePort(self.world, rid, allow_reverse=True, allow_mecanum=True,
                min_wheel_cmd=bundle['options'].get('min_wheel_cmd', 'off')) for rid in self.ports}
            self.stagnation = StagnationGuard(bundle['options'].get('stagnation_watch', 'off'))

        def eval_sample(self):
            super().eval_sample()
            self.stagnation.check(self.eval_rows[-1])
    return Backend
