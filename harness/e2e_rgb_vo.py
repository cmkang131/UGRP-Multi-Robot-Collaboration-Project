"""Default-off own-RGB ground-plane visual odometry fused with issued pulses.

Option ``rgb_vo_v1`` (value of the existing ``stall_odometry`` toggle).

Measurement (Seegmiller & Wettergreen, IROS 2011, II-C--F; Zienkiewicz &
Davison, JFR 2015): OpenCV Shi-Tomasi corners + pyramidal LK with
forward/backward check on own floor pixels, fixed fisheye K/D and issued-servo
camera FK back-project to the floor z=0 (camera height fixes metric scale),
robust SE(2) by the registered S2 ``rigid_ransac``/PARAMS, covariance from the
fit residual and one-pixel ray propagation (same rule as S2 ``pair``).

Fusion, one frame interval (<= one calibrated 0.2 s pulse): issued-command
increment is the prior (calibrated pulse variance), VO is a measurement of the
same increment (increment-level Kalman update, robot_localization-style
differential fusion, Moore & Stouch 2014). If the innovation fails the
chi-square gate the command model is declared invalid for that interval
(stall/slip, Helmick et al. 2004) and the complete visual increment replaces it
(S2 ``ground_vo_v1`` replace rule; no double counting). The fused increment is
injected through ``PulseOdometry.motion_filter`` so the RBPF step callback
(odometry proposal, Grisetti et al. 2007) sees it.

Unknown VO (missing/stale/identical image, servo change or unsettled camera,
weak texture/rank) never means zero motion: the command increment is kept.
Inputs: own RGB, own issued commands/servo, fixed camera calibration only.
No simulator state, truth pose, contact or measured joint enters here.
"""
from functools import lru_cache
import copy
import math
import cv2
import numpy as np
from harness.active_camera import transform as camera_transform
from harness.floor_goal_self_mask import self_body_mask
from harness.zone_solo_cyan_progress_noise import PARAMS as S2_PARAMS, rigid_ransac
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

OPTION = 'rgb_vo_v1'
OPTION_V2 = 'rgb_vo_v2'  # v1 + rgb_pulse_gate_v1 stationarity fallback when VO is unavailable
WIDTH, HEIGHT = 640, 480
K = scaled_camera_matrix(WIDTH, HEIGHT)
D = np.asarray(CAMERA_FISHEYE_D, np.float64).reshape(4, 1)
PARAMS = dict(
    # Registered S2 tracker/RANSAC values, reused verbatim (not re-tuned).
    **{k: S2_PARAMS[k] for k in ('max_corners', 'quality', 'min_distance_px', 'lk_window_px',
                                 'lk_pyramid_levels', 'fb_max_px', 'min_tracks', 'min_cells',
                                 'cell_size_px', 'feature_pixel_sigma', 'ground_range_m')},
    max_pair_gap_s=.25,          # one 5 Hz frame interval (+ tolerance)
    settle_s=(.25, 2.25),        # OdomGrid default after an issued servo change
    chi2_gate=11.345,            # chi-square, 3 dof, p=.99
    saturation_max=100, value_min=25, colour_dilate_px=11)  # same as e2e_stall_odometry.flow_pair


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array([a[0]+c*b[0]-s*b[1], a[1]+s*b[0]+c*b[1], wrap(a[2]+b[2])])


def between(a, b):
    """x such that compose(a, x) == b."""
    c, s = math.cos(a[2]), math.sin(a[2]);d = np.asarray(b[:2], float)-a[:2]
    return np.array([c*d[0]+s*d[1], -s*d[0]+c*d[1], wrap(b[2]-a[2])])


def _servo_key(servo):
    return tuple(sorted((int(k), int(v)) for k, v in servo.items()))


@lru_cache(maxsize=16)
def _camera(servo_items):
    origin, rotation = camera_transform(dict(servo_items))
    return np.asarray(origin, float), np.asarray(rotation, float)


def ground(servo, uv):
    """Raw fisheye pixels -> floor z=0 points in the robot base frame."""
    origin, rotation = _camera(_servo_key(servo))
    uv = np.asarray(uv, np.float64).reshape(-1, 1, 2)
    if len(uv) == 0:
        return np.zeros((0, 2)), np.zeros(0)
    normal = cv2.fisheye.undistortPoints(uv, K, D)
    if normal is None:  # OpenCV may return None for degenerate input: no floor point, never zero motion
        return np.full((len(uv), 2), np.nan), np.full(len(uv), np.nan)
    normal = np.asarray(normal, np.float64).reshape(-1, 2)
    if len(normal) != len(uv):
        return np.full((len(uv), 2), np.nan), np.full(len(uv), np.nan)
    rays = np.column_stack((normal, np.ones(len(normal))))@rotation.T
    down = rays[:, 2] < -1e-9
    depth = np.full(len(rays), np.nan)
    depth[down] = -origin[2]/rays[down, 2]
    return origin[:2]+rays[:, :2]*depth[:, None], depth


@lru_cache(maxsize=16)
def floor_mask(servo_items):
    """Static mask: valid fisheye pixels whose ray meets the floor in range, minus own body."""
    servo = dict(servo_items)
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float64)
    raw = np.stack((xs, ys), -1).reshape(-1, 1, 2)
    ideal = cv2.fisheye.undistortPoints(raw, K, D, R=np.eye(3), P=K).reshape(HEIGHT, WIDTH, 2)
    valid = (ideal[..., 0] >= 0) & (ideal[..., 0] <= WIDTH-1) & (ideal[..., 1] >= 0) & (ideal[..., 1] <= HEIGHT-1)
    points, depth = ground(servo, raw.reshape(-1, 2))
    lo, hi = PARAMS['ground_range_m']
    ranges = np.linalg.norm(points, axis=1).reshape(HEIGHT, WIDTH)
    ok = valid & np.isfinite(ranges) & (ranges >= lo) & (ranges <= hi)
    ok &= ~self_body_mask(servo, 'camera_v3', WIDTH, HEIGHT)
    mask = cv2.erode(ok.astype(np.uint8)*255, np.ones((7, 7), np.uint8))
    mask[:4] = 0;mask[-10:] = 0;mask[:, :4] = 0;mask[:, -4:] = 0
    mask.setflags(write=False)
    return mask


def image_mask(rgb, servo):
    """Exclude saturated colour (cargo, zones, robots) and dark pixels, as flow_pair does."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    bad = (hsv[:, :, 1] > PARAMS['saturation_max'])|(hsv[:, :, 2] < PARAMS['value_min'])
    n = PARAMS['colour_dilate_px']
    bad = cv2.dilate(bad.astype(np.uint8), np.ones((n, n), np.uint8)) > 0
    mask = floor_mask(_servo_key(servo)).copy()
    mask[bad] = 0
    return mask


def rigid_fit_covariance(servo, p, q, a, b, rot, delta):
    """S2 ``pair`` rule: max(residual, one-pixel ray) variance times (J^T J)^-1."""
    rotated = b@rot.T;residual = a-(rotated+delta)
    jac = np.zeros((2*len(a), 3));jac[::2, 0] = 1;jac[1::2, 1] = 1
    jac[::2, 2] = -rotated[:, 1];jac[1::2, 2] = rotated[:, 0]
    if np.linalg.matrix_rank(jac) != 3:
        return None, None
    pixel_var = []
    for uv in (p, q):
        dx = ground(servo, uv+[.5, 0])[0]-ground(servo, uv-[.5, 0])[0]
        dy = ground(servo, uv+[0, .5])[0]-ground(servo, uv-[0, .5])[0]
        pixel_var.append(float(np.mean(dx*dx+dy*dy))*PARAMS['feature_pixel_sigma']**2)
    sigma2 = max(float(np.sum(residual**2)/max(1, 2*len(a)-3)), sum(pixel_var))
    return sigma2*np.linalg.inv(jac.T@jac), float(np.sqrt(np.mean(residual**2)))


def ground_pair(before, after, servo):
    """Robot SE(2) motion from ``before`` to ``after`` (static floor: p_b = R p_a + t)."""
    if before.shape != (HEIGHT, WIDTH, 3) or after.shape != before.shape:
        raise ValueError('640x480 RGB required')
    unknown = dict(status='unknown_texture', tracks=0, inliers=0, cells=0)
    if np.array_equal(before, after):
        return {**unknown, 'status': 'unknown_identical_rgb'}
    ma, mb = image_mask(before, servo), image_mask(after, servo)
    ga, gb = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY), cv2.cvtColor(after, cv2.COLOR_RGB2GRAY)
    pts = cv2.goodFeaturesToTrack(ga, maxCorners=PARAMS['max_corners'], qualityLevel=PARAMS['quality'],
                                  minDistance=PARAMS['min_distance_px'], mask=ma, blockSize=7)
    if pts is None:
        return unknown
    cfg = dict(winSize=(PARAMS['lk_window_px'],)*2, maxLevel=PARAMS['lk_pyramid_levels'],
               criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT, 30, .01))
    nxt, ok, _ = cv2.calcOpticalFlowPyrLK(ga, gb, pts, None, **cfg)
    if nxt is None:
        return unknown
    back, ok2, _ = cv2.calcOpticalFlowPyrLK(gb, ga, nxt, None, **cfg)
    if back is None:
        return unknown
    p, q = pts[:, 0].astype(np.float64), nxt[:, 0].astype(np.float64)
    xy = np.rint(q).astype(int)
    inside = (xy[:, 0] >= 0)&(xy[:, 0] < WIDTH)&(xy[:, 1] >= 0)&(xy[:, 1] < HEIGHT)
    good = inside&ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(np.abs(p-back[:, 0]).max(1) < PARAMS['fb_max_px'])
    good[inside] &= mb[xy[inside, 1], xy[inside, 0]] > 0
    p, q = p[good], q[good]
    if len(p) < PARAMS['min_tracks']:  # E2E14 crash: 0 tracked floor points reached ground()
        return {**unknown, 'tracks': len(p)}
    a, da = ground(servo, p);b, db = ground(servo, q)
    valid = np.isfinite(a).all(1)&np.isfinite(b).all(1)&(da > 0)&(db > 0)
    p, q, a, b = p[valid], q[valid], a[valid], b[valid]
    cw, ch = PARAMS['cell_size_px']
    cells = len(set((int(x)//cw, int(y)//ch) for x, y in p))
    unknown.update(tracks=len(p), cells=cells)
    if len(p) < PARAMS['min_tracks'] or cells < PARAMS['min_cells']:
        return unknown
    # rigid_ransac(before, after): before = rot @ after + delta, i.e. delta is
    # the robot motion expressed in the BEFORE base frame.
    fit = rigid_ransac(a, b)
    if fit is None:
        return {**unknown, 'status': 'unknown_rigid_consensus'}
    rot, delta, inl = fit
    p, q, a, b = p[inl], q[inl], a[inl], b[inl]
    cells = len(set((int(x)//cw, int(y)//ch) for x, y in p))
    if cells < PARAMS['min_cells']:
        return {**unknown, 'status': 'unknown_spatial_support', 'inliers': len(a), 'cells': cells}
    cov, rms = rigid_fit_covariance(servo, p, q, a, b, rot, delta)
    if cov is None:
        return {**unknown, 'status': 'unknown_information_rank', 'inliers': len(a), 'cells': cells}
    return dict(status='measured', tracks=unknown['tracks'], inliers=len(a), cells=cells,
                delta=[float(delta[0]), float(delta[1]), float(math.atan2(rot[1, 0], rot[0, 0]))],
                covariance=((cov+cov.T)/2).tolist(), fit_rms_m=rms)


def fuse(command_delta, command_cov, vo_delta, vo_cov, *, mode='fused', chi2_gate=None):
    """Increment-level Kalman update with a chi-square stall/slip replacement."""
    c = np.asarray(command_delta, float);Q = np.asarray(command_cov, float)
    z = np.asarray(vo_delta, float);Rv = np.asarray(vo_cov, float)
    nu = z-c;nu[2] = wrap(nu[2])
    S = Q+Rv
    nis = float(nu@np.linalg.solve(S, nu))
    gate = PARAMS['chi2_gate'] if chi2_gate is None else float(chi2_gate)
    if mode == 'replace' or nis > gate:
        return z.copy(), Rv.copy(), nis, 'vo_replaced'
    Kg = Q@np.linalg.inv(S)
    x = c+Kg@nu;x[2] = wrap(x[2])
    P = (np.eye(3)-Kg)@Q
    return x, (P+P.T)/2, nis, 'fused'


class VOFusion:
    """Own-input VO adapter around a PulseOdometry driver (live and fixed replay)."""

    def __init__(self, driver, mode='fused', *, chi2_gate=None, fallback=None):
        if mode not in ('fused', 'replace'):
            raise ValueError('UNKNOWN_VO_FUSION_MODE')
        if fallback not in (None, 'pulse_gate'):
            raise ValueError('UNKNOWN_VO_FALLBACK')
        self.fallback = fallback
        # v2: when VO cannot measure (e.g. pressed against a plain wall), use the
        # existing binary own-RGB stationarity decision; unknown still keeps command.
        from harness.e2e_stall_odometry import Detector, PULSE_GATE
        self.detector = Detector(driver, PULSE_GATE) if fallback else None
        # chi2_gate override exists only for offline sensitivity columns; the
        # live toggle always uses the registered PARAMS value.
        self.mode = mode;self.chi2_gate = chi2_gate
        # Same clone rule as e2e_stall_odometry.Detector: predictor state only.
        self.nominal = copy.copy(driver)
        self.nominal.__dict__ = copy.deepcopy({k: v for k, v in vars(driver).items()
                                               if k not in ('step_callback', 'motion_filter')})
        self.nominal.step_callback = None
        self.steps = []
        self.nominal.motion_filter = self._record
        self.last = None;self.plan = None;self.cursor = 0
        self.servo_since = getattr(driver, 'servo_since', 0.)
        self.counts = dict(measured=0, fused=0, vo_replaced=0, unknown=0, unapplied=0, substep_mismatch=0, gate_zero=0)

    def _record(self, delta, variance):
        self.steps.append((np.asarray(delta, float).copy(), np.asarray(variance, float).copy()))
        return delta, variance

    def command(self, row):
        self.nominal.command(row)
        if self.detector is not None:
            self.detector.command(row)
        if row['kind'] in ('arm', 'look', 'initial_servo_command'):
            self.servo_since = float(row['t'])

    def _command_increment(self):
        total = np.zeros(3);P = np.zeros((3, 3))
        for delta, variance in self.steps:
            c, s = math.cos(total[2]), math.sin(total[2])
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]]);world = R@delta
            F = np.eye(3);F[:2, 2] = [-world[1], world[0]]
            P = F@P@F.T+R@np.diag(variance)@R.T
            total = compose(total, delta)
        return total, P

    def observe(self, *, t, frame_id, rgb, servo, sha256=None):
        t = float(t)
        if self.last is not None and (t <= self.last['t'] or frame_id <= self.last['frame_id']):
            raise ValueError('FRESH_MONOTONIC_OWN_RGB_REQUIRED')
        self.nominal.advance(t)
        command_delta, command_cov = self._command_increment()
        steps = self.steps;self.steps = []
        gate = None
        if self.detector is not None:
            gate = self.detector.observe(t=t, frame_id=frame_id, rgb=rgb, servo=servo, sha256=sha256)
        row = dict(option=OPTION_V2 if self.fallback else OPTION, mode=self.mode, t=t, frame_id=frame_id, sha256=sha256,
                   command_delta=command_delta.tolist(), command_substeps=len(steps), status='no_previous_frame')
        loaded = int(int(servo.get(1, 2000)) <= 1600)
        if self.last is not None:
            if t-self.last['t'] > PARAMS['max_pair_gap_s']+1e-8:
                row['status'] = 'unknown_frame_gap'
            elif _servo_key(self.last['servo']) != _servo_key(servo):
                row['status'] = 'unknown_servo_change'
            elif self.last['t']-self.servo_since+1e-8 < PARAMS['settle_s'][loaded]:
                row['status'] = 'unknown_camera_settling'
            else:
                row.update(ground_pair(self.last['rgb'], rgb, servo))
        fused = command_delta
        if row['status'] == 'measured':
            self.counts['measured'] += 1
            fused, cov, nis, how = fuse(command_delta, command_cov, row['delta'], row['covariance'],
                                        mode=self.mode, chi2_gate=self.chi2_gate)
            self.counts[how] += 1
            row.update(fusion=how, nis=nis, fused_delta=fused.tolist(), fused_variance=np.diag(cov).tolist())
            self.plan = self._plan(steps, fused, cov) if steps else None
            if not steps:
                self.counts['unapplied'] += 1;row['fusion_applied'] = False
            else:
                row['fusion_applied'] = True
        elif gate is not None and self.detector.suppressed and steps:
            # Confirmed stationary view while translating: zero translation, keep
            # commanded yaw, inflate Q (AMCL alpha 2.0) -- never false certainty.
            from harness.e2e_stall_odometry import alpha_extra
            fused = np.array([0., 0., command_delta[2]])
            cov = command_cov+np.diag(alpha_extra(command_delta, True))
            self.counts['gate_zero'] += 1
            self.plan = self._plan(steps, fused, cov)
            row.update(fusion='gate_zero', fused_delta=fused.tolist(), fused_variance=np.diag(cov).tolist(),
                       fusion_applied=True)
        else:
            if self.last is not None:
                self.counts['unknown'] += 1
            self.plan = None
            row.update(fusion='command_kept', fused_delta=command_delta.tolist())
        if gate is not None:
            row['gate'] = {k: gate.get(k) for k in ('status', 'stationary', 'stationary_streak', 'median_px', 'p90_px', 'tracks')}
        self.cursor = 0
        self.last = dict(t=t, frame_id=frame_id, rgb=rgb.copy(), servo=dict(servo))
        return row

    def skip(self, t):
        """Frame without an image (offline replay): no pair across it, reset gate history."""
        self.nominal.advance(t);self.steps = []
        if self.detector is not None:
            d = self.detector
            d.frames.clear();d.stationary_since = None;d.streak = 0
            d.nominal.advance(t);d.last_nominal = np.asarray(d.nominal.pose)

    @staticmethod
    def _plan(steps, fused, cov):
        deltas = [d for d, _ in steps];variances = [v for _, v in steps]
        command_delta = np.zeros(3)
        for d in deltas:
            command_delta = compose(command_delta, d)
        correction = fused-command_delta;correction[2] = wrap(correction[2])
        size = np.array([math.hypot(d[0], d[1])+.1*abs(d[2]) for d in deltas])
        w = size/size.sum() if size.sum() > 1e-12 else np.full(len(deltas), 1./len(deltas))
        new = [d+wk*correction for d, wk in zip(deltas, w)]
        head = np.zeros(3)
        for d in new[:-1]:
            head = compose(head, d)
        new[-1] = between(head, fused)  # exact composition == fused increment
        target = np.diag(cov)
        return [(nd, target*wk) for nd, wk in zip(new, w)]

    def motion_filter(self, delta, variance):
        """Install as driver.motion_filter only around the frame's odom.advance(t)."""
        if self.plan is None:
            return delta, variance
        if self.cursor >= len(self.plan):
            self.counts['substep_mismatch'] += 1;self.plan = None
            return delta, variance
        planned = self.plan[self.cursor];self.cursor += 1
        return planned[0].copy(), planned[1].copy()

    def finish_interval(self):
        if self.plan is not None and self.cursor != len(self.plan):
            self.counts['substep_mismatch'] += 1
        self.plan = None;self.cursor = 0


def install(goal, option=OPTION):
    """Live E2E wiring (default off); same wrapper pattern as e2e_stall_odometry.install."""
    grid = goal.explorer.memory.self_map;odom = grid.odom;base = getattr(odom, 'base', odom);driver = base.driver
    from harness.self_pulse_odom import PulseOdometry
    if not isinstance(driver, PulseOdometry) or driver.motion_filter is not None:
        raise ValueError('UNMODIFIED_PULSE_ODOMETRY_REQUIRED')
    if option not in (OPTION, OPTION_V2):
        raise ValueError('UNKNOWN_RGB_VO_OPTION')
    vo = VOFusion(driver, fallback='pulse_gate' if option == OPTION_V2 else None);goal.e2e_vo = vo
    active = False
    pending_commands = []

    def motion_filter(delta, variance):
        return vo.motion_filter(delta, variance) if active else (delta, variance)
    driver.motion_filter = motion_filter
    command = goal.command

    def commanded(row):
        # The physical command has already been dispatched by Robot.commanded.
        # Defer only estimator integration until its complete RGB interval is
        # available, then replay every issued timestamp through the same facade.
        vo.command(row)
        pending_commands.append(copy.deepcopy(row))
        goal.last_command = copy.deepcopy(row)
    goal.command = commanded
    receive = goal.receive

    def received(**kw):
        nonlocal active
        if kw['robot_id'] != goal.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        row = vo.observe(t=kw['t'], frame_id=kw['frame_id'], rgb=kw['rgb'], servo=kw['servo'], sha256=kw['frame_sha256'])
        active = True;before = np.asarray(driver.pose)
        mismatches = vo.counts['substep_mismatch']
        try:
            for issued in pending_commands:
                command(issued)
            pending_commands.clear()
            odom.advance(kw['t'])
        finally:
            active = False;vo.finish_interval()
        if vo.counts['substep_mismatch'] != mismatches:
            row['fusion_applied'] = False
            raise ValueError('RGB_VO_SUBSTEP_MISMATCH')
        row['applied_delta'] = between(before, np.asarray(driver.pose)).tolist()
        row['counts'] = dict(vo.counts)
        action, trace = receive(**kw)
        trace['stall_odometry'] = dict(options=dict(stall_odometry=option, stall_recovery='off', stall_noise='off'),
                                       **{k: v for k, v in row.items() if k not in ('covariance',)})
        goal.last_trace = copy.deepcopy(trace)
        return action, trace
    goal.receive = received
    return goal
