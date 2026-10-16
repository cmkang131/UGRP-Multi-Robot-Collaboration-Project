"""Independent global safety envelope; relative RGB cannot alter this budget.

The nominal PF is retained. A separate command reachability envelope prevents
small PF covariance after dead reckoning from erasing anchor uncertainty.
Coefficients are conservative development bounds, not calibrated coverage.

Review 3: the reachable set is centred on the anchor plus the half-gain
integrated command (actual gain in [0, BACKOFF_GAIN_MAX]); each increment's
heading error is bounded by the anchor yaw and turn-gain uncertainty. The PF
discrepancy is measured from that centre, so a displacement is counted once.
"""
from dataclasses import replace
import math

from harness.owncam_time import pose_report_fresh
from harness.zone_own_guards import OwnPose, BACKOFF_GAIN_MAX, BASE_MARGIN_M, K_SIGMA
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_v6_policy import informative_fix


def reported_pose(report, now):
    p = OwnPose.from_report(report)
    if (p is None or not pose_report_fresh(report,now) or min(p.std_xy,p.std_yaw)<0):
        return None
    hypotheses = (report.observation_quality or {}).get('posterior_envelope')
    if hypotheses is not None:
        xy, yaw = hypotheses.get('xy_radius_m'),hypotheses.get('yaw_radius_rad')
        if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in (xy,yaw)):
            return None
        p = replace(p,std_xy=max(p.std_xy,xy/2),std_yaw=max(p.std_yaw,yaw/2))
    return p


# Planned safety re-observations are separate from the HIGH recovery budget.
# Registered in prereg_v6 v6_contract; development scheduling bounds only.
SCHEDULED_REOBSERVE = {
    'per_look_s': 6.,    # wait charged to the planned look; the rest spills to HIGH recovery
    'total_s': 240.,     # cumulative planned-look wait per job (of the 900 s SIM limit)
    'max_count': 80,     # planned safety looks per job (approach + align)
    'reserve_gap_m': .04,
    'reducible_sigma_m': .005,
    'reducible_sigma_rad': .005,
}


def heading_spread(delta):
    """Radius factor of {s*e(d): s in [0,1], |d|<=delta} around e(0)/2."""
    delta = min(abs(delta), math.pi)
    return math.sqrt(max(.25, 1.25-math.cos(delta)))


def _wrap(angle):
    return (angle+math.pi)%(2*math.pi)-math.pi


class GlobalEnvelope:
    def __init__(self):
        self.anchor = None
        self.fix_t = None
        self.t = None
        self.motion = (0.,0.,0.)
        self.until = -math.inf
        self.travel_bound = self.turn_bound = 0.
        self.centre_offset = (0.,0.)   # half-gain command displacement since anchor (world)
        self.centre_turn = 0.          # half-gain command rotation since anchor
        self.reacquisition = None
        self.last_candidate_fix_t = -math.inf

    def _reset_motion(self):
        self.travel_bound = self.turn_bound = 0.
        self.centre_offset, self.centre_turn = (0.,0.), 0.

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
        half = BACKOFF_GAIN_MAX/2
        steps = max(1,math.ceil(dt/.02))
        x,y = self.centre_offset
        base = 0. if self.anchor is None else self.anchor.yaw
        for _ in range(steps if dt > 0 else 0):
            h = dt/steps
            yaw = base+self.centre_turn+half*w*h/2
            x += half*h*(math.cos(yaw)*f-math.sin(yaw)*l)
            y += half*h*(math.sin(yaw)*f+math.cos(yaw)*l)
            self.centre_turn += half*w*h
        self.centre_offset = (x,y)
        self.t = now

    def inflation(self, pose):
        """Envelope growth over a fresh fix at this anchor (0 when unknown)."""
        if pose is None or self.anchor is None:
            return (0.,0.)
        return (pose.std_xy-(self.anchor.std_xy+.005), pose.std_yaw-self.anchor.std_yaw)

    def command(self, row):
        self.advance(row['t'])
        if row['kind'] in ('drive','mecanum'):
            self.motion = tuple(row.get(k,0.) for k in ('forward','left','turn'))
            self.until = row['t']+row['duration_s']
            self.reacquisition = None
        elif row['kind'] == 'hold':
            # Hold is issued intent; reserve finite stop lag, not instantaneous
            # physical stopping. Repeated holds do not refill the tail.
            self.until = min(self.until,row['t']+.2)

    def _verified_reacquisition(self, p, fix_t):
        """Three distinct, consecutive compact fixes while the base is stopped.

        Re-reading a receipt is not corroboration. Motion, missing information,
        disagreement or a >1 s gap restarts this separate recovery check. These
        are development consistency bounds, not calibrated absolute accuracy.
        """
        if fix_t <= self.last_candidate_fix_t:
            return False
        self.last_candidate_fix_t = fix_t
        if (fix_t < self.until + .2 or p.std_xy > .05 or p.std_yaw > math.radians(3)):
            self.reacquisition = None
            return False
        previous = self.reacquisition
        if previous is not None:
            first, last, reference, count = previous
            angle = abs((p.yaw-reference.yaw+math.pi)%(2*math.pi)-math.pi)
            if (fix_t-last <= 1. and math.dist((p.x,p.y),(reference.x,reference.y)) <= .03
                    and angle <= math.radians(3)):
                self.reacquisition = (first,fix_t,reference,count+1)
                return count+1 >= 3 and fix_t-first >= .3
        self.reacquisition = (fix_t,fix_t,p,1)
        return False

    def pose(self, report, now):
        self.advance(now)
        p = reported_pose(report,now)
        if p is None:
            self.reacquisition = None
            return None
        quality = report.observation_quality or {}
        current_rejected = (any(quality.get(k) is False for k in ('accepted','informative','settled'))
                            or quality.get('ambiguous') is True)
        # Providers retain last_fix_quality through a bad current observation.
        # That receipt can age normally, but cannot bridge a recovery streak.
        if (not informative_fix(report) or current_rejected
                or report.last_fix_t is None or report.last_fix_t > now):
            self.reacquisition = None
        if (informative_fix(report) and report.last_fix_t is not None
                and report.last_fix_t <= now and (self.fix_t is None or report.last_fix_t>self.fix_t)):
            if not 0 <= report.t_est-report.last_fix_t+1e-4 <= .3002:
                self.reacquisition = None
                return None  # an old receipt cannot anchor a newer predicted mean
            # Reject a new compact mode outside the old reachable envelope;
            # lost recovery needs a new independently verified anchor.
            if self.anchor is not None:
                budget = self.travel_bound+2*(self.anchor.std_xy+p.std_xy)+.03
                yaw_budget = self.turn_bound+2*(self.anchor.std_yaw+p.std_yaw)+.001*(now-self.fix_t)
                dyaw = abs((p.yaw-self.anchor.yaw+math.pi)%(2*math.pi)-math.pi)
                if (math.dist((p.x,p.y),(self.anchor.x,self.anchor.y))>budget or dyaw>yaw_budget):
                    if current_rejected or not self._verified_reacquisition(p,report.last_fix_t):
                        return None
            self.anchor,self.fix_t = p,report.last_fix_t
            self._reset_motion()
            self.reacquisition = None
        if self.anchor is None or not 0 <= now-self.fix_t <= 30.:
            return None
        # Enclose both nominal PF and every position reachable from the anchor:
        # centre = anchor + half-gain command, radius = gain/heading spread.
        age = now-self.fix_t
        a = self.anchor
        centre = (a.x+self.centre_offset[0],a.y+self.centre_offset[1])
        discrepancy = math.dist((p.x,p.y),centre)
        heading = 2*a.std_yaw+self.turn_bound/2+.001*age
        reach = self.travel_bound*heading_spread(heading)
        dyaw = abs(_wrap(p.yaw-a.yaw-self.centre_turn))
        xy = max(p.std_xy,a.std_xy+(discrepancy+reach+.002*age+.01)/2)
        yaw = max(p.std_yaw,a.std_yaw+(dyaw+self.turn_bound/2+.001*age)/2)
        return replace(p,std_xy=xy,std_yaw=yaw)

    def recovery_pose(self, report, now):
        """Enclose the old reachable anchor AND the unverified candidate.

        This is only a stationary camera-sweep budget, never a navigation fix.
        The caller must stop the base and retain the ordinary recovery deadline.
        """
        self.advance(now)
        p = reported_pose(report,now)
        a = self.anchor
        if (a is None or p is None or not pose_report_fresh(report, now)
                or not 0 <= now-self.fix_t <= 30.):
            return None
        age = now-self.fix_t
        angle = abs((p.yaw-a.yaw+math.pi)%(2*math.pi)-math.pi)
        return replace(a,
            std_xy=max(a.std_xy+(self.travel_bound+.002*age+.01)/2,
                       p.std_xy+math.dist((p.x,p.y),(a.x,a.y))/2),
            std_yaw=max(a.std_yaw+(self.turn_bound+.001*age)/2, p.std_yaw+angle/2))


class GlobalPairSweepGuard(PairSweepGuard):
    """No sigma clipping. Unsupported envelopes fail closed."""
    def margin(self, pose, lever_m):
        if (not all(math.isfinite(v) and v>=0 for v in (pose.std_xy,pose.std_yaw,lever_m))
                or pose.std_xy>.15 or pose.std_yaw>.20):
            return math.inf
        return BASE_MARGIN_M+self.residual+K_SIGMA*(pose.std_xy+pose.std_yaw*lever_m)

    def certificate(self, servo, pose, beam=None, *, loaded=False, reducible=True):
        """reducible: a new fix could shrink this envelope (motion since anchor).

        A thin gap alone never re-triggers a look that cannot improve it (review 3).
        """
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
                'relook_reserve_low':bool((gap < SCHEDULED_REOBSERVE['reserve_gap_m'] and reducible)
                                          or pose.std_xy >= .10 or pose.std_yaw >= .15),
                'reserve_gap_low':bool(gap < SCHEDULED_REOBSERVE['reserve_gap_m']),
                'std_xy_m':pose.std_xy,'std_yaw_rad':pose.std_yaw}
