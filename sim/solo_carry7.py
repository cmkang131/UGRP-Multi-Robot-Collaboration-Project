"""Opt-in robust relocalisation and remembered-cargo search. No simulator/GT."""
import math
import numpy as np
from sim.active_lookaround import wrap

OPTION = 'carry7_robust_recovery_v1'
NIS_LIMIT = 9.  # Mahalanobis radius 3; NOT a 99% chi-square(3) quantile
MODE_XY_M = .30
MODE_YAW_RAD = math.radians(30.)
MODE_LOG_RATIO = math.log(20.)  # retain sensor-compatible alternatives >= 1/20 peak
TURN_RATE_FLOOR = .08  # conservative command-model planning rate, not measured speed


def innovation_gate(prior, covariance, proposal):
    """Test against the prediction, before covariance shrinkage/mode collapse.

    The grid posterior reuses the prior; Pprior+Pposterior is not independent
    measurement noise. Use the prediction ellipsoid, plus per-axis 3 sigma.
    """
    delta = np.asarray(proposal, float)-prior
    delta[2] = wrap(delta[2])
    P = np.asarray(covariance, float)
    valid = np.isfinite(delta).all() and np.isfinite(P).all()
    try:
        np.linalg.cholesky(P)
        nis = float(delta@np.linalg.solve(P, delta)) if valid else math.inf
        axes = np.abs(delta)/np.sqrt(np.diag(P)) if valid else np.full(3, math.inf)
    except np.linalg.LinAlgError:
        nis, axes = math.inf, np.full(3, math.inf)
    return dict(accepted=bool(nis <= NIS_LIMIT and np.max(axes) <= 3.),
                prediction_nis=nis, limit=NIS_LIMIT, axis_sigma=axes.tolist(),
                delta_m_m_rad=delta.tolist(), covariance='prediction_only')


def sensor_modes(poses, sensor_loglik):
    """Keep distinct SE(2) sensor hypotheses BEFORE applying the Gaussian prior.

    Bounded nonmaximum suppression, including circular yaw. A long ridge is
    also ambiguous: two separated compatible poses prohibit covariance shrink.
    These are discrete hypotheses, not a full particle-filter implementation.
    """
    poses = np.asarray(poses, float); scores = np.asarray(sensor_loglik, float)
    valid = np.isfinite(scores) & np.isfinite(poses).all(axis=1)
    if not valid.any():
        return dict(available=True, ambiguous=True, hypotheses=[], reason='no_sensor_support')
    peak = float(scores[valid].max())
    ids = np.flatnonzero(valid & (scores >= peak-MODE_LOG_RATIO))
    ids = ids[np.argsort(-scores[ids], kind='stable')]
    modes = []
    while len(ids) and len(modes) < 8:
        i = ids[0]; p = poses[i].copy(); p[2] = wrap(p[2])
        modes.append(dict(pose=p.tolist(), relative_likelihood=float(math.exp(scores[i]-peak))))
        distance = np.linalg.norm(poses[ids, :2]-p[:2], axis=1)
        angle = np.abs(wrap(poses[ids, 2]-p[2]))
        ids = ids[(distance > MODE_XY_M) | (angle > MODE_YAW_RAD)]
    return dict(available=True, ambiguous=len(modes) != 1, hypotheses=modes,
                reason='additional_view_required' if len(modes) != 1 else 'single_sensor_mode',
                separation_m_rad=[MODE_XY_M, MODE_YAW_RAD], likelihood_ratio_floor=1/20)


def correction_gate(prior, covariance, proposal, modes):
    gate = innovation_gate(prior, covariance, proposal)
    complete = bool(modes and modes.get('available') is True)
    unique = complete and modes.get('ambiguous') is False and len(modes.get('hypotheses', [])) == 1
    # A single global mode must also agree with the local proposal.
    match = False
    if unique:
        p = modes['hypotheses'][0]['pose']
        match = math.dist(p[:2], proposal[:2]) <= MODE_XY_M and abs(wrap(p[2]-proposal[2])) <= MODE_YAW_RAD
    reasons = []
    if not gate['accepted']: reasons.append('prediction_3sigma')
    if not complete: reasons.append('hypotheses_unavailable')
    elif not unique: reasons.append('ambiguous_sensor_modes')
    elif not match: reasons.append('proposal_mode_mismatch')
    return dict(**{k:v for k,v in gate.items() if k != 'accepted'}, accepted=not reasons,
                reasons=reasons, modes=modes, additional_view_required=bool(reasons))


def global_sensor_grid(static):
    """Static-map-only coarse independent proposals; never an online pose read.

    The local fine grid is added by the caller. This global sensor branch keeps
    symmetric alternatives outside the local prior in the ambiguity test.
    """
    a,b,c,d = static['bounds_m']
    xs, ys = np.arange(a+.1,b,.20), np.arange(c+.1,d,.20)
    xy = np.stack(np.meshgrid(xs,ys,indexing='ij'),-1).reshape(-1,2)
    for o in static['obstacles']:
        if o.get('kind') != 'wall': continue
        center = np.asarray(o['center_m']); half = np.asarray(o['half_extents_m'])+.18
        xy = xy[~np.all(np.abs(xy-center) <= half, axis=1)]
    yaw = np.arange(-math.pi,math.pi,math.radians(10.))
    return np.column_stack((np.repeat(xy,len(yaw),axis=0), np.tile(yaw,len(xy))))


def refine_global_grid(poses, scores):
    """Refine 32 separated coarse peaks, independent of the local prior.

    A 20 cm/10 degree lattice alone could miss a narrow symmetric alternative
    while the local fine grid hits it. Cover each chosen cell at 2 cm/1 degree.
    This remains a finite DEV search, not a global coverage certificate.
    """
    ids=np.argsort(-scores,kind='stable');seeds=[]
    while len(ids) and len(seeds)<32:
        p=poses[ids[0]];seeds.append(p)
        d=poses[ids]-p
        ids=ids[(np.linalg.norm(d[:,:2],axis=1)>.25) | (np.abs(wrap(d[:,2]))>math.radians(20.))]
    offsets=np.stack(np.meshgrid(np.linspace(-.1,.1,11),np.linspace(-.1,.1,11),
        np.linspace(-math.radians(5.),math.radians(5.),11),indexing='ij'),-1).reshape(-1,3)
    return np.concatenate([p+offsets for p in seeds]) if seeds else np.empty((0,3))


def world_point(pose, local):
    x,y,a = pose; c,s = math.cos(a),math.sin(a)
    return [x+c*local[0]-s*local[1], y+s*local[0]+c*local[1], local[2]]


def body_point(pose, point):
    x,y,a = pose; c,s = math.cos(a),math.sin(a)
    dx,dy = point[0]-x,point[1]-y
    return [c*dx+s*dy,-s*dx+c*dy,point[2]]


class CargoReacquirer:
    """Aim from corrected own pose + remembered own-visible/issued-setdown site.

    No translation or grasp from memory. Only a fresh visible measurement ends
    this skill. After the centre view, scan +/-25 degrees around that bearing.
    """
    OFFSETS = (0., -25., 25., 0.)

    def __init__(self, pose, point, now, pwm, ops, *, source):
        self.point = list(point); self.source = source; self.ops = ops
        self.started = self.stage_t = now; self.i = 0; self.stage = 'turn'
        self.events = []; self.failure = None
        angle = abs(wrap(math.atan2(point[1]-pose[1],point[0]-pose[0])-pose[2]))
        # Actual bounded turn effort, servo slew <=60 pulses/tick and dwell.
        self.budget_s = (angle+math.radians(100.))/TURN_RATE_FLOOR + 4*(2000/600+1.) + 5.
        self.deadline = now+self.budget_s

    def tick(self, now, pose, pwm):
        if now > self.deadline:
            self.failure = 'carry_reacquire_unconfirmed'; return 0., dict(pwm)
        local = body_point(pose,self.point)
        bearing = math.atan2(local[1],local[0])
        offset = math.radians(self.OFFSETS[self.i])
        error = wrap(bearing+offset)
        if self.stage == 'turn':
            if abs(error) > math.radians(3.):
                return max(-.1,min(.1,.6*error)), {**pwm,6:1500}
            self.stage = 'settle'; self.stage_t = now
            self.events.append(dict(t=now,view=self.i,offset_deg=self.OFFSETS[self.i],bearing_rad=bearing))
        c,s = math.cos(offset),math.sin(offset)
        scan_local = [c*local[0]-s*local[1],s*local[0]+c*local[1],local[2]]
        target = self.ops.gaze(scan_local,pwm,visible=False)
        if target is None: target = dict(pwm)
        updated = {**pwm,**self.ops.slew(pwm,target)}
        settled = all(updated[k] == target[k] for k in target)
        if not settled: self.stage_t = now
        if settled and now-self.stage_t >= 1.:
            self.i += 1
            if self.i == len(self.OFFSETS):
                self.failure = 'carry_reacquire_unconfirmed'
            else: self.stage = 'turn'; self.stage_t = now
        return 0., updated

    def record(self):
        return dict(source=self.source, memory_world_m=self.point, started=self.started,
                    budget_s=self.budget_s, deadline=self.deadline, events=self.events,
                    failure=self.failure, memory_controls='gaze_and_in_place_rotation_only')
