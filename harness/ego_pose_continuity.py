"""Default-off pose reporting and continuous control coordinates.

REP-105 frame separation, AMCL motion/cluster reporting, and Gaussian innovation
tests. Inputs are own command predictions and the existing RGB posterior only.
The RBPF posterior is correlated with its motion prior: the optional EKF-style
reporter is a DEV comparator, not a claim of calibrated independent measurements.
"""
from dataclasses import dataclass, asdict
import copy
import itertools
import math
import numpy as np

from harness.active_wall_mapping import compose, inverse
from harness.self_map_prob import wrap
from harness.self_odom_grid import transform
from harness.own_map_amcl_vendor.motion import moved

REP105 = 'rep105_offset_v1'
STATIONARY = 'amcl_min_motion_v1'
CLUSTER = 'amcl_cluster_v1'
MAHALANOBIS = 'mahalanobis_v1'
MAHALANOBIS_SE2 = 'mahalanobis_se2_v1'
BOUND = 'motion_covariance_v1'
CHI2_99_XY = 9.210340371976184
CHI2_99_SE2 = 11.344866730144373


@dataclass(frozen=True)
class Options:
    pose_continuity: str = 'off'
    stationary_update: str = 'off'
    pose_reporting: str = 'off'
    correction_gate: str = 'off'
    correction_limit: str = 'off'

    def __post_init__(self):
        for name, value in zip(asdict(self), (REP105, STATIONARY, CLUSTER, MAHALANOBIS, BOUND)):
            if name=='correction_gate' and getattr(self,name)==MAHALANOBIS_SE2:continue
            if getattr(self, name) not in ('off', value):
                raise ValueError('UNKNOWN_POSE_OPTION:' + name)

    @property
    def enabled(self):
        return any(v != 'off' for v in asdict(self).values())


def dominant_cluster(poses, weights):
    """AMCL occupied-bin neighbour components, max total weight, circular mean.

    Nav2 pf_kdtree uses 0.5m/0.5m/10deg bins and all 26 neighbours. Yaw bins
    wrap here at +/-pi (explicit seam repair, not a new density threshold).
    Maps are not averaged; the existing RBPF still owns each particle's map.
    """
    poses, weights = np.asarray(poses, float), np.asarray(weights, float)
    if (poses.ndim != 2 or poses.shape[1] != 3 or weights.shape != (len(poses),)
            or not np.isfinite(poses).all() or not np.isfinite(weights).all()
            or np.any(weights < 0) or weights.sum() <= 0):
        raise ValueError('FINITE_WEIGHTED_CLOUD_REQUIRED')
    weights = weights / weights.sum()
    bins = np.floor(poses / [.5, .5, math.pi/18]).astype(int)
    bins[:, 2] %= 36
    cells = {}
    for i, key in enumerate(map(tuple, bins)):
        cells.setdefault(key, []).append(i)
    remaining = set(cells)
    groups = []
    while remaining:
        first = min(remaining); remaining.remove(first)
        todo, group = [first], []
        while todo:
            key = todo.pop(); group.extend(cells[key])
            for dx, dy, da in itertools.product((-1, 0, 1), repeat=3):
                neighbour = (key[0]+dx, key[1]+dy, (key[2]+da) % 36)
                if neighbour in remaining:
                    remaining.remove(neighbour); todo.append(neighbour)
        groups.append(sorted(group))
    selected = max(groups, key=lambda ids: (float(weights[ids].sum()), -ids[0]))
    w = weights[selected]; mass = float(w.sum()); w = w/mass
    p = poses[selected]
    mean = w@p
    mean[2] = math.atan2(float(w@np.sin(p[:, 2])), float(w@np.cos(p[:, 2])))
    return mean, dict(clusters=len(groups), mass=mass, particles=len(selected),
                     representative=selected[int(np.argmax(w))])


def spd(cov):
    cov = np.asarray(cov, float)
    if cov.shape != (3, 3) or not np.isfinite(cov).all():
        raise ValueError('FINITE_3X3_COVARIANCE_REQUIRED')
    cov = (cov+cov.T)/2
    values, vectors = np.linalg.eigh(cov)
    if values.min() < -1e-8:
        raise ValueError('PSD_COVARIANCE_REQUIRED')
    return (vectors*np.maximum(values, 1e-10))@vectors.T


class Reporter:
    """Same numeric reporter in online control and fixed-measurement replay."""
    def __init__(self, pose, covariance, options=Options()):
        self.options = options
        self.pose = np.asarray(pose, float).copy()
        self.covariance = spd(covariance)
        self.motion_covariance = np.zeros((3, 3))
        self.last = {'reason': 'initialized'}

    def predict(self, body_delta, body_covariance):
        delta = np.asarray(body_delta, float)
        c, s = math.cos(self.pose[2]), math.sin(self.pose[2])
        R = np.array([[c,-s,0.], [s,c,0.], [0.,0.,1.]])
        world = R@delta
        F = np.eye(3); F[:2, 2] = [-world[1], world[0]]
        Q = R@np.asarray(body_covariance)@R.T
        self.pose = compose(self.pose, delta)
        self.covariance = spd(F@self.covariance@F.T+Q)
        self.motion_covariance = F@self.motion_covariance@F.T+Q

    def measure(self, measurement, covariance):
        z, R = np.asarray(measurement, float), spd(covariance)
        innovation = z-self.pose; innovation[2] = wrap(innovation[2])
        P = self.covariance
        S = P+R
        d2 = float(innovation[:2]@np.linalg.solve(S[:2, :2], innovation[:2]))
        row = dict(innovation=innovation.tolist(), mahalanobis_xy=d2,
                   threshold=CHI2_99_XY, accepted=True, reason='measurement')
        statistic,threshold=d2,CHI2_99_XY
        if self.options.correction_gate==MAHALANOBIS_SE2:
            statistic=float(innovation@np.linalg.solve(S,innovation));threshold=CHI2_99_SE2
            row.update(mahalanobis_se2=statistic,threshold=threshold,gate_dof=3,
                       innovation_covariance=S.tolist())
        if self.options.correction_gate != 'off' and statistic > threshold:
            row.update(accepted=False, reason='mahalanobis_rejected')
            if self.options.correction_gate==MAHALANOBIS_SE2:row['reason']='mahalanobis_se2_rejected'
        if self.options.correction_gate != 'off':
            K = np.linalg.solve(S.T, P.T).T
            correction = K@innovation
            I_K = np.eye(3)-K
            posterior = I_K@P@I_K.T+K@R@K.T  # Joseph form
        else:
            correction, posterior = innovation, R
        if self.options.correction_limit != 'off':
            Q = self.motion_covariance[:2, :2]+np.eye(2)*1e-10
            q2 = float(correction[:2]@np.linalg.solve(Q, correction[:2]))
            row['motion_mahalanobis_xy'] = q2
            if q2 > CHI2_99_XY:
                row.update(accepted=False, reason='motion_covariance_rejected')
        if row['accepted']:
            self.pose += correction; self.pose[2] = wrap(self.pose[2])
            self.covariance = spd(posterior)
            self.motion_covariance[:] = 0.
        row['correction_xy_m'] = float(np.linalg.norm(correction[:2])) if row['accepted'] else 0.
        self.last = row
        return row


class PoseView:
    def __init__(self, base, options):
        self.base, self.options = base, options
        self.reporter = Reporter(base.pose, base.covariance, options)
        self.inside = False
        self.driver_pose = np.asarray(base.driver.pose).copy()
        self.driver_covariance = np.asarray(base.driver.covariance).copy()
        self.last_motion_update = None
        self.cluster = None
        self.measurements = self.skips = 0

    def __getattr__(self, name):
        base = self.__dict__.get('base')
        if base is None:
            raise AttributeError(name)
        return getattr(base, name)

    @property
    def forecast_odometry(self):
        # Virtual information-gain rollouts mutate a private particle cloud,
        # not the live output reporter or its correlated covariance state.
        return self.base

    @property
    def reporting(self):
        return any(getattr(self.options, k) != 'off' for k in
                   ('pose_reporting', 'correction_gate', 'correction_limit'))

    @property
    def pose(self):
        return tuple(self.reporter.pose) if self.reporting and not self.inside else self.base.pose

    @property
    def covariance(self):
        if self.reporting and not self.inside:
            # Keep the PF's global ambiguity visible to existing safety logic.
            P, R = self.reporter.covariance, np.asarray(self.base.covariance)
            return P+R if self.options.correction_gate != 'off' else R
        return self.base.covariance

    def advance(self, t):
        self.base.advance(t)
        now = np.asarray(self.base.driver.pose)
        delta = compose(inverse(self.driver_pose), now)
        if np.any(abs(delta) > 1e-14):
            # Existing selective RBPF uses this same per-camera command noise.
            from harness.rbpf_rejection import motion_variance
            self.reporter.predict(delta, np.diag(motion_variance(delta)))
        self.driver_pose = now.copy()
        return self.pose

    def command(self, row):
        self.advance(row['t'])
        self.base.command(row)

    def measurement(self):
        g = self.base.owner
        z = np.asarray(self.base.pose)
        if self.options.pose_reporting != 'off':
            z, self.cluster = dominant_cluster(g.poses, g.weights)
        if self.reporting:
            self.reporter.measure(z, self.base.covariance)
        self.measurements += 1


def install(controller, options=Options()):
    """Wrap this instance only; all-off returns the exact original object."""
    if not options.enabled:
        return controller
    if hasattr(controller, '_pose_continuity_view'):
        raise ValueError('POSE_CONTINUITY_ALREADY_INSTALLED')
    e = controller.explorer; g = e.memory.self_map
    view = PoseView(g.odom, options)
    g.odom = view
    controller._pose_continuity_view = view
    observe = g._observe
    def observe_pose(rec, segments, **kw):
        if kw['robot_id'] != g.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        view.advance(rec['t_sim'])
        now = np.asarray(view.base.driver.pose)
        if (options.stationary_update != 'off' and view.last_motion_update is not None
                and not moved(now-view.last_motion_update)):
            view.skips += 1
            g.decisions.append(dict(t=rec['t_sim'], frame_id=rec['view_index'],
                reason=STATIONARY, matching_attempted=False, inserted=False,
                resampled=False, pose=list(view.pose), covariance=view.covariance.tolist()))
            return []
        before = len(g.decisions)
        view.inside = True
        try:
            result = observe(rec, segments, **kw)
        finally:
            view.inside = False
        if len(g.decisions) > before:
            event = g.decisions[-1]
            if event.get('matching_attempted') or event.get('particle_events'):
                view.last_motion_update = now.copy()
                view.measurement()
                event['pose_reporting'] = copy.deepcopy(view.reporter.last)
        return result
    g._observe = observe_pose
    localize = controller._localize
    def localize_pose(sample, t):
        before = np.asarray(view.base.pose)
        result = localize(sample, t)
        if not np.array_equal(before, np.asarray(view.base.pose)):
            view.measurement()
            sample['pose'] = list(view.pose)
            sample['covariance'] = view.covariance.tolist()
        return result
    controller._localize = localize_pose
    if options.pose_continuity != 'off':
        host = controller.heading_host
        if host is None:
            raise ValueError('REP105_REQUIRES_EXPLICIT_HEADING_HOST')
        def continuous_coordinates(pose, path, goal):
            odom = np.asarray(view.base.driver.pose)
            map_to_odom = compose(pose, inverse(odom))
            odom_from_map = inverse(map_to_odom)
            return (odom, transform(path, odom_from_map).tolist() if len(path) else [],
                    transform([goal], odom_from_map)[0])
        # Apply inside the shared Host after outer route adapters have selected
        # their final map-frame path. An outer wrapper would mix frames when
        # ReferenceRoute replaces path with _return_path.
        host.pose_frame_transform = continuous_coordinates
    receive = controller.receive
    def receive_pose(**kw):
        command, trace = receive(**kw)
        odom = np.asarray(view.base.driver.pose)
        map_pose = np.asarray(trace['local_pose'])
        trace['pose_continuity'] = dict(options=asdict(view.options), map_pose=map_pose.tolist(),
            odom_pose=odom.tolist(), map_to_odom=compose(map_pose, inverse(odom)).tolist(),
            control_pose=(odom if options.pose_continuity != 'off' else map_pose).tolist(),
            control_frame='command_odom' if options.pose_continuity != 'off' else 'local_map',
            raw_selected_pose=list(view.base.pose), update=copy.deepcopy(view.reporter.last),
            cluster=view.cluster, measurements=view.measurements, stationary_skips=view.skips,
            covariance_scope='correlated_posterior_DEV_not_calibrated_EKF')
        controller.last_trace = copy.deepcopy(trace)
        return command, trace
    controller.receive = receive_pose
    return controller
