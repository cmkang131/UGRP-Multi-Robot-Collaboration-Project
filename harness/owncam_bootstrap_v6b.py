"""v6b start-pose bootstrap: static dock prior, stationary look, belief-checked pan scan.

Opt-in layer over the v6 recovery PF (``owncam_recovery_v6``), selected by the
``b-boot`` / ``a+b-boot`` pair policies. v5h, b-only and a+b are unchanged.

1. Prior (AMCL-style initialisation). MCL starts from a prior belief bel(x0);
   uniform global initialisation is for the case without prior knowledge
   (Thrun, Burgard, Fox, *Probabilistic Robotics*, ch. 8). ROS ``amcl`` seeds
   particles from ``initial_pose_*`` with ``initial_cov_*``; its defaults
   (0.5 m, 0.5 m, pi/12 rad standard deviations) are used unchanged. Our map
   lists three authored dock rows and no robot-to-row assignment, so the
   prior is an equal-weight mixture of one AMCL Gaussian per row. Dock rows
   are static-map data (the host already uses them for idle keep-outs),
   never a live pose. A prior is not a fix: no fix time, no receipt.

2. Stop-and-look (Active Markov Localization; Fox, Burgard, Thrun 1998).
   Sense before acting while the belief is ambiguous. The executor issues no
   own arm/wheel command until the provider reports an informative fix and
   the unchanged guard certifies the job's first arm transition (or the
   existing gate LOW level is met; ``bootstrap_complete``). It
   first observes at the current view. The offline replay of the v6 cohort
   shows that one folded-arm view (landmarks clustered ~2.9 m ahead) leaves
   a y-yaw ridge (sigma_xy 0.34-0.6 m), too wide for the unchanged arm-raise
   guard. The only extra sensing action allowed is a camera pan (servo 6)
   with the base holding and the arm at its issued posture. Frames taken
   while the camera moves stay excluded (unchanged 0.3 s settle rule).

3. Belief check for that pan only (RRBT: Bry & Roy 2011 check the belief's
   k-sigma uncertainty ellipse against obstacles). The unchanged SweepGuard
   is evaluated at the mean and at the 2k sigma points of the reported
   3x3 (x, y, yaw) covariance, each with zero extra sigma inflation. This
   replaces the isotropic sqrt(var_x+var_y) inflation, which refuses even
   the current folded posture at every dock once sigma reaches its cap,
   for the pan-only bootstrap scan. The arm raise afterwards uses the
   unchanged guard and gate.

4. PF sampling for the stationary views (the robot does not move, so the
   exact belief is prior x prod_j p(z_j|x) up to the stationary diffusion):
   Mixture-MCL dual samples (Thrun, Fox, Burgard, Dellaert 2001) from the
   existing sensor-resetting proposal ``_reset_from``, weighted by that
   predicted belief, then resample-move MCMC (Gilks & Berzuini 2001) with
   the same belief as the invariant target. Neither re-uses a frame as new
   evidence; byte-identical frames are still dropped by the provider.

Provider-agnostic: the executor reads only ``PoseReport`` (``last_fix_t``,
``observation_quality`` receipt, mean and ``cov``). A markerless provider must
implement ``initialize_from_prior``; there is no tag fallback and no
landmark-specific logic here. Constants are development hypotheses.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from harness.owncam_recovery_v6 import MIN_INLIER_FRACTION, RecoveryLocalizer

# ROS amcl defaults (wiki.ros.org/amcl initial_cov_xx/yy/aa), unchanged.
AMCL_INITIAL_STD_XY_M = .5
AMCL_INITIAL_STD_YAW_RAD = math.pi / 12
PRIOR_SOURCE = 'static_map.start_dock'
FAIL_REASON = 'STATIONARY_BOOTSTRAP_NO_FIX'
SETTLE_AFTER_PAN_S = .6     # = owncam_drive.SETTLE_S (>= 0.3 s rule + one 5 Hz frame)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def dock_prior(static_map) -> dict | None:
    """Mixture components from the static map's authored dock rows, or None.

    Only authored fields are read: spawn_x_m, spawn_rows_y_m, spawn_yaw_rad.
    The profile's own seal must match, so an edited dock cannot pass silently.
    """
    dock = static_map.get('start_dock') if hasattr(static_map, 'get') else None
    if not dock:
        return None
    body = {k: v for k, v in dock.items() if k != 'sha256'}
    if dock.get('sha256') != _digest(body):
        raise ValueError('start_dock profile seal mismatch')
    rows = [float(y) for y in dock['spawn_rows_y_m']]
    x, yaw = float(dock['spawn_x_m']), float(dock['spawn_yaw_rad'])
    if not rows or not all(map(math.isfinite, [x, yaw, *rows])):
        raise ValueError('invalid start_dock profile')
    return {'source': PRIOR_SOURCE, 'dock_id': dock['id'], 'dock_version': dock['version'],
            'dock_sha256': dock['sha256'], 'components': [[x, y, yaw] for y in rows],
            'weights': [1. / len(rows)] * len(rows),
            'std_xy_m': AMCL_INITIAL_STD_XY_M, 'std_yaw_rad': AMCL_INITIAL_STD_YAW_RAD,
            'scope': 'start of session only; equal-weight rows, no robot-to-row assignment'}


def prior_logdensity(px, prior) -> np.ndarray:
    """log density of the equal-weight AMCL Gaussian mixture at each (x, y, yaw)."""
    comps = np.asarray(prior['components'], float)
    sxy, syaw = float(prior['std_xy_m']), float(prior['std_yaw_rad'])
    d = np.asarray(px, float)[:, None, :] - comps[None, :, :]
    d[..., 2] = (d[..., 2] + np.pi) % (2 * np.pi) - np.pi
    log_norm = -1.5 * math.log(2 * math.pi) - 2 * math.log(sxy) - math.log(syaw)
    q = (-.5 * ((d[..., 0] / sxy)**2 + (d[..., 1] / sxy)**2 + (d[..., 2] / syaw)**2) + log_norm
         + np.log(np.asarray(prior['weights'], float))[None, :])
    m = q.max(axis=1)
    return m + np.log(np.exp(q - m[:, None]).sum(axis=1))


class BootstrapLocalizer(RecoveryLocalizer):
    """RecoveryLocalizer whose initial belief may come from a static prior."""
    DUAL_FRACTION = .2          # same share as the v6 recovery proposals
    MAX_BOOT_FRAMES = 6         # one per WIDE_LOOK_PANS view
    MOVE_STEPS = ((.05, .05, .03), (.02, .02, .01), (.005, .005, .003))
    MOVE_ITERS = 10

    # ------------------------------------------------------------ prior
    def initialize_from_prior(self, t, prior):
        if self.initialized:
            raise ValueError('prior initialisation is only for an uninitialised PF')
        comps = np.asarray(prior['components'], float)
        pick = self.rng.choice(len(comps), size=self.n, p=np.asarray(prior['weights'], float))
        noise = self.rng.normal(size=(self.n, 3)) * [prior['std_xy_m'], prior['std_xy_m'], prior['std_yaw_rad']]
        self.predict_to(t)
        self.px = comps[pick] + noise
        self.px[:, 2] = (self.px[:, 2] + np.pi) % (2 * np.pi) - np.pi
        self.scale = 1. + self.rng.normal(size=(self.n, 3)) * self.params['motion']['scale_std']
        self.logw = self._map_logprior(self.px)
        self.initialized = True
        self.prior_receipt = {**prior, 'n_components': len(comps), 't': float(t)}
        self.boot_obs, self.boot_log, self.boot_ended = [], [], None
        self._normalize_and_resample()
        return True

    def bootstrap_active(self) -> bool:
        if getattr(self, 'prior_receipt', None) is None or self.boot_ended is not None:
            return False
        if self.last_informative_t is not None:
            self.boot_ended = 'informative_fix'
        elif np.any(np.abs(self.vel) > 1e-9) or self.cmd_expires >= 0.:
            self.boot_ended = 'wheel_motion'       # the stationary belief no longer holds
        elif len(self.boot_obs) >= self.MAX_BOOT_FRAMES:
            self.boot_ended = 'frame_budget'
        return self.boot_ended is None

    # ------------------------------------------------------------ update
    def update(self, t, detections, commanded_pose=None):
        boot = None
        if self.bootstrap_active() and (self.last_update_t is None or t > self.last_update_t):
            self.predict_to(t)
            if t - self.last_servo_cmd_t >= .3:
                boot = self._inject_dual(t, detections, commanded_pose)
        est = super().update(t, detections, commanded_pose)
        q = self.quality
        if (boot is not None and q.get('settled') and not q.get('saturated', True)
                and q.get('inlier_fraction', 0.) >= MIN_INLIER_FRACTION):
            # The parent applied this frame's likelihood; add it to the exact
            # stationary belief and restore diversity by resample-move.
            self.boot_obs.append(boot)
            self._resample_move()
            est = self.estimate()
        return est

    def _usable(self, detections):
        from harness.wall_tags import observed_tag_in_camera
        maximum = self.params['measurement'].get('max_range_m')
        return [d for d in detections if int(d['id']) in self.tags and d.get('solutions')
                and (not maximum or np.linalg.norm(observed_tag_in_camera(d)[0]) <= maximum)]

    def _belief(self, px, extra=()):
        total = prior_logdensity(px, self.prior_receipt) + self._map_logprior(px)
        for dets, pose in (*self.boot_obs, *extra):
            total = total + self._loglik(px, dets, pose)
        return total

    def _inject_dual(self, t, detections, commanded_pose):
        dets = self._usable(detections)
        if not dets:
            return None
        pose = {int(k): int(v) for k, v in (commanded_pose or self.servo).items()}
        k = max(1, int(self.n * self.DUAL_FRACTION))
        idx = self.rng.choice(self.n, k, replace=False)
        dual = self._reset_from(dets, pose, k)
        # Dual importance weight = predicted belief (prior x earlier stationary views).
        dens = self._belief(dual)
        record = {'t': float(t), 'k': int(k), 'views_before': len(self.boot_obs),
                  'max_logdensity': float(np.max(dens))}
        self.boot_log.append(record)
        if not np.isfinite(dens).any() or dens.max() < math.log(1e-12):
            record['skipped'] = 'observation_outside_prior_support'
            return (dets, pose)
        keep = np.ones(self.n, bool)
        keep[idx] = False
        reg = self.logw[keep] - self.logw[keep].max()
        reg -= math.log(np.exp(reg).sum())
        dual_w = dens - dens.max()
        dual_w -= math.log(np.exp(dual_w).sum())
        self.px[idx], self.scale[idx] = dual, 1.
        self.logw[keep] = reg + math.log(1 - self.DUAL_FRACTION)
        self.logw[idx] = dual_w + math.log(self.DUAL_FRACTION)
        self.stats['dual_samples'] = self.stats.get('dual_samples', 0) + int(k)
        return (dets, pose)

    def _resample_move(self):
        w = np.exp(self.logw - self.logw.max()); w /= w.sum()
        positions = (np.arange(self.n) + self.rng.uniform()) / self.n
        idx = np.minimum(np.searchsorted(np.cumsum(w), positions), self.n - 1)
        self.px, self.scale = self.px[idx].copy(), self.scale[idx].copy()
        self.logw = np.zeros(self.n)
        cur = self._belief(self.px)
        accepted = 0
        for step in self.MOVE_STEPS:
            for _ in range(self.MOVE_ITERS):
                prop = self.px + self.rng.normal(size=self.px.shape) * step
                prop[:, 2] = (prop[:, 2] + np.pi) % (2 * np.pi) - np.pi
                new = self._belief(prop)
                ok = np.log(self.rng.uniform(size=self.n)) < new - cur
                self.px[ok], cur[ok] = prop[ok], new[ok]
                accepted += int(ok.sum())
        if self.boot_log:
            self.boot_log[-1]['move_acceptance'] = round(accepted / (self.n * self.MOVE_ITERS
                                                                     * len(self.MOVE_STEPS)), 4)
        self.stats['moves'] = self.stats.get('moves', 0) + 1


# ---------------------------------------------------------------- provider seam
def _unwrap(provider):
    while hasattr(provider, 'provider'):
        provider = provider.provider
    return provider


def enable_bootstrap(provider, now):
    """Opt-in; requires the v6 recovery provider. Idempotent per provider.

    The prior is applied only to a PF that has not been initialised and has
    seen no wheel motion (start of session at the dock). Otherwise the
    existing observation bootstrap is kept and the receipt says why.
    """
    inner = _unwrap(provider)
    if getattr(inner, 'stationary_bootstrap', None) is not None:
        return inner.stationary_bootstrap
    from harness.owncam_pose_source import OwnCamPoseSource
    static_map = getattr(inner, 'static_map', None)
    prior = None if static_map is None else dock_prior(static_map)
    if isinstance(inner, OwnCamPoseSource):
        if not getattr(inner, 'recovery_v6', False):
            raise ValueError('v6b bootstrap requires the v6 recovery provider')
        loc = inner.loc
        if not isinstance(loc, BootstrapLocalizer):
            loc.__class__ = BootstrapLocalizer   # same object: shared PF identity preserved
        if prior is None:
            applied, reason = False, 'no_static_dock_prior'
        elif loc.initialized:
            applied, reason = False, 'already_initialized'
        elif np.any(np.abs(loc.vel) > 1e-9) or loc.cmd_expires >= 0.:
            applied, reason = False, 'wheel_motion_seen'
        else:
            applied, reason = loc.initialize_from_prior(float(now), prior), None
        if not inner.source.endswith(':boot_v6b'):
            inner.source += ':boot_v6b'
    else:
        method = getattr(inner, 'initialize_from_prior', None)
        if not callable(method) or not callable(getattr(inner, 'report', None)):
            raise ValueError('v6b provider lacks the static-prior initialisation contract')
        applied = bool(prior is not None and method(float(now), prior))
        reason = None if applied else 'provider_declined_or_no_prior'
    inner.stationary_bootstrap = {'enabled_at': float(now), 'prior_applied': bool(applied),
                                  'prior_skip_reason': reason, 'prior': prior,
                                  'completed_at': None, 'exhausted_at': None, 'fix_t': None}
    return inner.stationary_bootstrap


def bootstrap_state(provider):
    return getattr(_unwrap(provider), 'stationary_bootstrap', None)


def bootstrap_fix(report) -> bool:
    """Provider-neutral: an informative, settled fix exists in the receipt."""
    from harness.zone_pair_v6_policy import informative_fix
    return bool(report is not None and report.initialized and report.last_fix_t is not None
                and informative_fix(report))


def bootstrap_complete(report, *, guard=None, servo=None, first_motion=None) -> bool:
    """Informative fix AND the first motion is certifiable by the UNCHANGED guard.

    An informative frame can arrive while one view still leaves a ridge
    (offline: sigma_xy 0.18-0.39 m at the first fix). The stop-and-look ends
    only when the unchanged SweepGuard (isotropic, capped sigma) clears the
    job's first arm transition from the home pan, or, without a known first
    motion, at the existing gate LOW level (0.05 m / 0.06 rad, unloaded).
    """
    from harness import zone_own_guards as guards
    if not bootstrap_fix(report):
        return False
    if report.std_xy_m <= guards.GATE_UNLOADED.low_xy_m and report.std_yaw_rad <= guards.GATE_UNLOADED.low_yaw_rad:
        return True
    if guard is None or servo is None or first_motion is None:
        return False
    return bool(guard.transition_clear(servo, first_motion, guards.OwnPose.from_report(report), loaded=False))


def sigma_points(report, k):
    """Mean and mean +/- k*sqrt(lambda_i)*v_i of the reported (x, y, yaw) covariance."""
    mean = np.array([report.x_m, report.y_m, report.yaw_rad], float)
    cov = np.asarray(report.cov, float)
    if cov.shape != (3, 3) or not np.isfinite(cov).all() or not np.isfinite(mean).all():
        return None
    lam, vec = np.linalg.eigh((cov + cov.T) / 2)
    points = [mean]
    for i in range(3):
        d = k * math.sqrt(max(float(lam[i]), 0.)) * vec[:, i]
        points += [mean + d, mean - d]
    return points


def belief_pan_clear(guard, current, pan, report, *, k=None) -> bool:
    """RRBT-style: the unchanged guard at every sigma point, no extra inflation.

    Pan-only (servo 6), base holding, arm at its issued posture. Nothing else.
    """
    from harness import zone_own_guards as guards
    k = guards.K_SIGMA if k is None else k
    if report is None or not report.initialized:
        return False
    points = sigma_points(report, k)
    if points is None:
        return False
    return all(guard.transition_clear(current, {6: int(pan)},
                                      guards.OwnPose(float(p[0]), float(p[1]), float(p[2]), 0., 0.),
                                      loaded=False) for p in points)


class StationaryBootstrap:
    """Executor-side stop-and-look: hold, observe, belief-checked pan scan, restore.

    ``step`` returns commands to issue now, or None when the bootstrap is done.
    It never issues an arm (servo 1/3/4/5) or wheel command. The cumulative
    stationary time is bounded by ``zone_own_sweep.SWEEP_REOBSERVE_S``.
    """

    def __init__(self, guard, pans, start_servo, now, *, first_motion=None):
        from harness.zone_own_sweep import SweepRecheck
        self.guard, self.wait = guard, SweepRecheck()
        self.home = int(start_servo.get(6, 1500))
        # The job's first arm posture, checked from the home pan (e.g. LOOK_P20).
        self.first_motion = None if first_motion is None else {**dict(first_motion), 6: self.home}
        self.queue = [int(p) for p in pans if int(p) != self.home]
        self.target, self.since, self.stage = None, float(now), 'observe'
        self.log = [{'t': round(float(now), 3), 'event': 'start', 'home_pan': self.home}]
        self.outcome = None

    def _pan_step(self, servo):
        cur = int(servo.get(6, self.home))
        return {'kind': 'look', 'pan_pulse': cur + int(np.clip(self.target - cur, -60, 60))}

    def step(self, now, provider, servo):
        rep = provider.report(now)
        fixed = bootstrap_complete(rep, guard=self.guard, servo={**dict(servo), 6: self.home},
                                   first_motion=self.first_motion)
        if fixed and self.stage in ('observe', 'settle'):
            self.stage, self.target = 'restore', self.home
            self.log.append({'t': round(now, 3), 'event': 'fix', 'fix_t': rep.last_fix_t,
                             'std_xy_m': round(rep.std_xy_m, 4), 'std_yaw_rad': round(rep.std_yaw_rad, 4)})
        if self.stage == 'restore' and int(servo.get(6, self.home)) == self.home:
            self.outcome = 'fix'
            self.wait.check_gate(now, ready=True)
            return None
        if self.wait.check_gate(now, ready=False) == 'blocked':
            self.outcome = 'blocked'
            self.log.append({'t': round(now, 3), 'event': 'budget_exhausted', 'waited_s': self.wait.waited_s})
            return [{'kind': 'hold'}]
        if self.stage in ('pan', 'restore'):
            if int(servo.get(6, self.home)) != self.target:
                if not belief_pan_clear(self.guard, servo, self._pan_step(servo)['pan_pulse'], rep):
                    self.log.append({'t': round(now, 3), 'event': 'pan_step_refused', 'target': self.target})
                    if self.stage == 'pan':
                        self.stage, self.since = 'settle', now   # observe where we are, then next pan
                    return [{'kind': 'hold'}]
                self.since = now
                return [{'kind': 'hold'}, self._pan_step(servo)]
            if self.stage == 'restore':
                return [{'kind': 'hold'}]
            self.stage = 'settle'
        if self.stage == 'settle' and now - self.since + 1e-9 >= SETTLE_AFTER_PAN_S:
            self.stage = 'observe'
        if self.stage == 'observe' and now - self.since + 1e-9 >= SETTLE_AFTER_PAN_S:
            while self.queue:
                pan = self.queue.pop(0)
                if belief_pan_clear(self.guard, servo, pan, rep):
                    self.target, self.stage = pan, 'pan'
                    self.log.append({'t': round(now, 3), 'event': 'pan', 'target': pan,
                                     'std_xy_m': round(rep.std_xy_m, 4) if rep.initialized else None})
                    return [{'kind': 'hold'}, self._pan_step(servo)]
                self.log.append({'t': round(now, 3), 'event': 'pan_refused', 'target': pan})
        return [{'kind': 'hold'}]
