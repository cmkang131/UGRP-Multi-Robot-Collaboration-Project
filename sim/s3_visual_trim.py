"""Opt-in measured final-alignment pulse capability; archived ports unchanged."""
from sim.s3_motion_ports import PairPhasePort
from sim.s3_stage_safety import PhysicsBackend as Previous

OPTION='measured_min100_v1'
DURATIONS=(.10,.12,.14)


class TrimPort(PairPhasePort):
    def apply(self, action, sim_time):
        # Only extend the existing 35-speed fine strafe to measured legal
        # lengths. Other proposals retain all original contract checks.
        if (not self.coupled() and action.get('kind')=='mecanum'
                and abs(action.get('left',0.))==.35
                and action.get('duration_s') in DURATIONS):
            import math
            if (set(action)!={'kind','forward','left','turn','duration_s'}
                    or action['forward']!=0 or action['turn']!=0 or not math.isfinite(sim_time)):
                raise ValueError('trim requires one finite axis and exact fields')
            f,l,t=(action[k] for k in ('forward','left','turn'))
            self._command_expires_at=None
            self._set_motors((f-l-t,f+l+t,f+l-t,f-l+t))
            self._drive_expires_at=float(sim_time)+action['duration_s']
            self._busy_until=self._drive_expires_at
            return dict(ok=True,robot_id=self.robot_id,kind='mecanum',sim_time=float(sim_time),
                busy_until=self._busy_until,actuator_state=self._actuator_state())
        return super().apply(action,sim_time)


class PhysicsBackend(Previous):
    def reset(self,cap):
        elapsed=super().reset(cap)
        option=self.bundle.get('visual_trim','off')
        if option=='off': return elapsed
        if option!=OPTION: raise ValueError('unknown visual trim option')
        for rid in ('r1','r2','r3'):
            self.ports[rid]=TrimPort(self.world,rid,
                coupled=lambda rid=rid:rid!='r3' and all(self.commands.get(r,{}).get(1,2000)<=1600 for r in ('r1','r2')),
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        return elapsed
