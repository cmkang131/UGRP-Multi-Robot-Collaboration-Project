"""Default-off release lifecycle for the evaluation-only physical drop guard."""
import math
from scripts.run_s3_integer_carry import PhysicsBackend as Previous
from sim.s3_synchronized_carry import CarryPulsePort


class CheckpointCarryPort(CarryPulsePort):
    """Explicit jointly-held crab duration capability; solo contract unchanged."""
    def apply(self, action, now):
        if (self.coupled() and action.get('kind') == 'mecanum'
                and action.get('left') and not action.get('forward') and not action.get('turn')):
            duration, speed = float(action['duration_s']), float(action['left'])
            if (set(action) != {'kind','forward','left','turn','duration_s'}
                    or not all(map(math.isfinite,(duration,speed,now)))
                    or abs(speed) not in (.35,.65) or not .10 <= duration <= .80):
                raise ValueError('checkpoint carry requires finite admitted speed, one axis, 100-800ms')
            self._command_expires_at=None
            self._set_motors((-speed,speed,speed,-speed))
            self._drive_expires_at=float(now)+duration;self._busy_until=self._drive_expires_at
            return dict(ok=True,robot_id=self.robot_id,kind='mecanum',sim_time=float(now),
                busy_until=self._busy_until,actuator_state=self._actuator_state())
        return super().apply(action,now)


def released_supported(row, commands):
    return (set(row['states']) == {'r1', 'r2'}
        and all(s in ('wait_open', 'cp_open', 'released', 'align') for s in row['states'].values())
        and all(commands.get(r, {}).get(1, 0) >= 2000 for r in ('r1', 'r2'))
        and row['floor_normal_n'] >= .1 and row['cargo_z_m'] <= .025
        and math.isfinite(row['vertical_speed_m_s']) and abs(row['vertical_speed_m_s']) <= .02
        and math.isfinite(row['cargo_tilt_deg']) and row['cargo_tilt_deg'] < 10.)


class PhysicsBackend(Previous):
    def reset(self, cap):
        elapsed=super().reset(cap)
        if self.bundle.get('checkpoint_correction',{}).get('options',{}).get('visual_checkpoint',False):
            for rid in ('r1','r2'):
                self.ports[rid]=CheckpointCarryPort(self.world,rid,
                    coupled=lambda:all(self.commands.get(r,{}).get(1,2000)<=1600 for r in ('r1','r2')),
                    allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        return elapsed

    def setdown_row(self):
        enabled = self.bundle.get('checkpoint_correction', {}).get('options', {}).get('release_epoch', False)
        cached = getattr(self, '_epoch_row', None)
        if enabled and cached is not None and cached['t'] == self.now:
            return cached
        row = super().setdown_row()
        if enabled: self._epoch_row = row
        return row

    def eval_sample(self):
        if self.bundle.get('checkpoint_correction', {}).get('options', {}).get('release_epoch', False):
            row = self.setdown_row()
            if 'beam_1' in self.lifted and released_supported(row, self.commands):
                self.lifted.discard('beam_1')
                self._append('eval_only/release-epochs.jsonl', {**row,
                    'event':'supported_release_disarms_previous_lift', 'controller_feedback':False,
                    'rearm':'unchanged height > .08 guard on the next actual lift'})
        return super().eval_sample()
