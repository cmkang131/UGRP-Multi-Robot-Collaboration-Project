"""Independent global safety envelope; relative RGB cannot alter this budget.

The nominal PF is retained. A separate command reachability envelope prevents
small PF covariance after dead reckoning from erasing anchor uncertainty.
Coefficients are conservative development bounds, not calibrated coverage.
"""
from dataclasses import replace
import math

from harness.owncam_time import pose_report_fresh
from harness.zone_own_guards import OwnPose, BACKOFF_GAIN_MAX, BASE_MARGIN_M, K_SIGMA
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_v6_policy import informative_fix


class GlobalEnvelope:
    def __init__(self):
        self.anchor = None
        self.fix_t = None
        self.t = None
        self.motion = (0.,0.,0.)
        self.until = -math.inf
        self.travel_bound = self.turn_bound = 0.

    def advance(self, now):
        if self.t is None:
            self.t = now
        if now < self.t:
            self.anchor = None
            return
        dt = max(0.,min(now,self.until)-self.t)
        f,l,w = self.motion
        self.travel_bound += BACKOFF_GAIN_MAX*math.hypot(f,l)*dt
        self.turn_bound += BACKOFF_GAIN_MAX*abs(w)*dt
        self.t = now

    def command(self, row):
        self.advance(row['t'])
        if row['kind'] in ('drive','mecanum'):
            self.motion = tuple(row.get(k,0.) for k in ('forward','left','turn'))
            self.until = row['t']+row['duration_s']
        elif row['kind'] == 'hold':
            # Hold is issued intent; reserve finite stop lag, not instantaneous
            # physical stopping. Repeated holds do not refill the tail.
            self.until = min(self.until,row['t']+.2)

    def pose(self, report, now):
        self.advance(now)
        p = OwnPose.from_report(report)
        if (p is None or not pose_report_fresh(report,now)
                or min(p.std_xy,p.std_yaw)<0):
            return None
        hypotheses = (report.observation_quality or {}).get('posterior_envelope')
        if hypotheses is not None:
            xy, yaw = hypotheses.get('xy_radius_m'),hypotheses.get('yaw_radius_rad')
            if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in (xy,yaw)):
                return None
            p = replace(p,std_xy=max(p.std_xy,xy/2),std_yaw=max(p.std_yaw,yaw/2))
        if (informative_fix(report) and report.last_fix_t is not None
                and report.last_fix_t <= now and (self.fix_t is None or report.last_fix_t>self.fix_t)):
            if not 0 <= report.t_est-report.last_fix_t+1e-4 <= .3002:
                return None  # an old receipt cannot anchor a newer predicted mean
            # Reject a new compact mode outside the old reachable envelope;
            # lost recovery needs a new independently verified anchor.
            if self.anchor is not None:
                budget = self.travel_bound+2*(self.anchor.std_xy+p.std_xy)+.03
                if math.dist((p.x,p.y),(self.anchor.x,self.anchor.y))>budget:
                    return None
            self.anchor,self.fix_t = p,report.last_fix_t
            self.travel_bound = self.turn_bound = 0.
        if self.anchor is None or not 0 <= now-self.fix_t <= 30.:
            return None
        # Enclose both nominal PF and every position reachable from the anchor.
        age = now-self.fix_t
        discrepancy = math.dist((p.x,p.y),(self.anchor.x,self.anchor.y))
        dyaw = abs((p.yaw-self.anchor.yaw+math.pi)%(2*math.pi)-math.pi)
        xy = max(p.std_xy,self.anchor.std_xy+(discrepancy+self.travel_bound+.002*age+.01)/2)
        yaw = max(p.std_yaw,self.anchor.std_yaw+(dyaw+self.turn_bound+.001*age)/2)
        return replace(p,std_xy=xy,std_yaw=yaw)


class GlobalPairSweepGuard(PairSweepGuard):
    """No sigma clipping. Unsupported envelopes fail closed."""
    def margin(self, pose, lever_m):
        if (not all(math.isfinite(v) and v>=0 for v in (pose.std_xy,pose.std_yaw,lever_m))
                or pose.std_xy>.15 or pose.std_yaw>.20):
            return math.inf
        return BASE_MARGIN_M+self.residual+K_SIGMA*(pose.std_xy+pose.std_yaw*lever_m)

    def certificate(self, servo, pose, beam=None, *, loaded=False):
        if pose is None:
            return {'clear':False,'reason':'GLOBAL_ANCHOR_UNKNOWN','clearance_m':None}
        if not math.isfinite(self.margin(pose,1.)):
            return {'clear':False,'reason':'GLOBAL_ENVELOPE_UNSUPPORTED','clearance_m':None}
        candidates = [self.chassis_clearance(pose),self.arm_clearance(servo,pose,loaded=loaded)]
        if beam is not None:
            candidates.append(self.stationary_beam_clearance(beam,pose))
        gap,wall = min(candidates,key=lambda row:row[0])
        return {'clear':bool(gap>=0),'reason':'clear' if gap>=0 else 'GLOBAL_ENVELOPE_BLOCKED',
                'clearance_m':gap if math.isfinite(gap) else None,'wall_id':wall,
                'relook_reserve_low':bool(gap < .04 or pose.std_xy >= .10 or pose.std_yaw >= .15),
                'std_xy_m':pose.std_xy,'std_yaw_rad':pose.std_yaw}
