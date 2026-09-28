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

3. Belief check for that pan only (particle chance constraint: Blackmore,
   Ono, Bektassov, Williams 2010 approximate a collision chance constraint
   by the fraction of belief particles in collision; RRBT, Bry & Roy 2011,
   checks the belief rather than the mean). The unchanged SweepGuard is
   evaluated with zero extra sigma at each of 64 systematic samples of the
   provider's posterior plus the mean; all must be clear. After one folded
   view the posterior is still multimodal across the three dock rows
   (offline replay), which a Gaussian sigma-point check misrepresents.
   A provider without ``belief_hypotheses`` falls back to the mean and the
   2x3 covariance sigma points. The arm raise uses the unchanged guard.

4. PF sampling for the stationary views (the robot does not move, so the
   exact belief is b = prior x prod_j p(z_j|x) up to the stationary diffusion
   and the per-step map penalty): after each ACCEPTED view, resample-move
   MCMC (Gilks & Berzuini 2001) with target b restores sample diversity
   without re-using the view as new evidence. A rejected view mutates
   nothing. (Review #261: the first draft's Mixture-MCL dual samples were
   weighted by b alone, ignoring the proposal density q, and injected
   before the quality decision. A corrected b*L/q version did not change the
   offline first-view result, and prior + pan views reach completion in the
   synthetic tests, so dual samples were removed.)

5. Tag-only today: ``_usable`` and the parent likelihood read temporary
   wall tags. Zero-tag behaviour is unverified and needs a markerless
   provider implementing ``initialize_from_prior`` (VIS6, PR #253).

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
        """Parent update unchanged; an ACCEPTED stationary view joins the exact
        stationary belief and is followed by resample-move.

        No particle or weight is touched before the parent's quality decision:
        a rejected (unsettled, saturated or incompatible) view leaves the PF as
        the parent left it, i.e. prediction only (review #261 finding 5).
        """
        boot = None
        if self.bootstrap_active() and (self.last_update_t is None or t > self.last_update_t):
            dets = self._usable(detections)
            if dets:
                boot = (dets, {int(k): int(v) for k, v in (commanded_pose or self.servo).items()})
        est = super().update(t, detections, commanded_pose)
        q = self.quality
        if (boot is not None and q.get('settled') and not q.get('saturated', True)
                and q.get('inlier_fraction', 0.) >= MIN_INLIER_FRACTION):
            self.boot_obs.append(boot)
            self.boot_log.append({'t': float(t), 'views': len(self.boot_obs)})
            self._resample_move()
            est = self.estimate()
        return est

    def _usable(self, detections):
        from harness.wall_tags import observed_tag_in_camera
        maximum = self.params['measurement'].get('max_range_m')
        return [d for d in detections if int(d['id']) in self.tags and d.get('solutions')
                and (not maximum or np.linalg.norm(observed_tag_in_camera(d)[0]) <= maximum)]

    def _belief(self, px):
        total = prior_logdensity(px, self.prior_receipt) + self._map_logprior(px)
        for dets, pose in self.boot_obs:
            total = total + self._loglik(px, dets, pose)
        return total

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
    """Informative fix AND the first motion is certifiable WITHOUT sigma clamping.

    An informative frame can arrive while the posterior is still wide
    (offline: sigma_xy 0.18-0.39 m at the first fix). Completion requires either
    the existing gate LOW level (0.05 m / 0.06 rad, unloaded), or

    - reported sigma within the guard's own cap (0.15 m / 0.20 rad), so the
      guard's ``min(sigma, cap)`` clamp is inactive (review #261 finding 2), and
    - the unchanged SweepGuard clears the job's first arm transition from home.

    The old policies' guard is not modified; only this completion rule refuses
    a clearance that exists only because of the clamp.
    """
    from harness import zone_own_guards as guards
    if not bootstrap_fix(report):
        return False
    if report.std_xy_m <= guards.GATE_UNLOADED.low_xy_m and report.std_yaw_rad <= guards.GATE_UNLOADED.low_yaw_rad:
        return True
    if guard is None or servo is None or first_motion is None:
        return False
    if report.std_xy_m > guards.SIGMA_CAP_XY_M or report.std_yaw_rad > guards.SIGMA_CAP_YAW_RAD:
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


BELIEF_SAMPLES = 64


def belief_hypotheses(provider, n=BELIEF_SAMPLES):
    """Systematic samples of the provider's posterior, or None if it exposes none."""
    inner = _unwrap(provider)
    method = getattr(inner, 'belief_hypotheses', None)
    if callable(method):
        return np.asarray(method(n), float)
    loc = getattr(inner, 'loc', None)
    if loc is None or not getattr(loc, 'initialized', False):
        return None
    w = np.exp(loc.logw - loc.logw.max())
    w /= w.sum()
    idx = np.minimum(np.searchsorted(np.cumsum(w), (np.arange(n) + .5) / n), len(w) - 1)
    return np.asarray(loc.px[idx], float)


def belief_pan_clear(guard, current, pan, report, *, hypotheses=None, k=None) -> bool:
    """Pan-only (servo 6), base holding, arm at its issued posture. Nothing else.

    With ``hypotheses``: the unchanged guard at the mean and at every belief
    sample, zero extra inflation (particle chance constraint). Without:
    the mean and the covariance sigma points (fallback for other providers).
    """
    from harness import zone_own_guards as guards
    if report is None or not report.initialized:
        return False
    if hypotheses is not None:
        points = [np.array([report.x_m, report.y_m, report.yaw_rad], float), *np.asarray(hypotheses, float)]
    else:
        points = sigma_points(report, guards.K_SIGMA if k is None else k)
    if points is None or not all(np.isfinite(p).all() for p in points):
        return False
    return all(guard.transition_clear(current, {6: int(pan)},
                                      guards.OwnPose(float(p[0]), float(p[1]), float(p[2]), 0., 0.),
                                      loaded=False) for p in points)


class StationaryBootstrap:
    """Executor-side stop-and-look: hold, observe, belief-checked pan scan, home, verify.

    ``step`` returns commands to issue now, or None when the bootstrap is done.
    It never issues an arm (servo 1/3/4/5) or wheel command. The cumulative
    stationary time is bounded by ``zone_own_sweep.SWEEP_REOBSERVE_S``.

    Completion is decided only at the home pan, after the settle time and on
    the report current at that moment (review #261 finding 4). A pan view is
    visited once: revisiting could feed a byte-different copy of an earlier
    view as new evidence, so after the queue the scan only holds and observes.
    """

    def __init__(self, guard, pans, start_servo, now, *, first_motion=None):
        from harness.zone_own_sweep import SweepRecheck
        self.guard, self.wait = guard, SweepRecheck()
        self.home = int(start_servo.get(6, 1500))
        # The job's first arm posture, checked from the home pan (e.g. LOOK_P20).
        self.first_motion = None if first_motion is None else {**dict(first_motion), 6: self.home}
        self.queue = [int(p) for p in dict.fromkeys(pans) if int(p) != self.home]
        self.target, self.since, self.stage = None, float(now), 'observe'
        self.log = [{'t': round(float(now), 3), 'event': 'start', 'home_pan': self.home}]
        self.outcome = None

    def _pan_step(self, servo):
        cur = int(servo.get(6, self.home))
        return {'kind': 'look', 'pan_pulse': cur + int(np.clip(self.target - cur, -60, 60))}

    def _complete(self, rep, servo):
        return bootstrap_complete(rep, guard=self.guard, servo={**dict(servo), 6: self.home},
                                  first_motion=self.first_motion)

    def _event(self, now, event, rep=None, **detail):
        row = {'t': round(float(now), 3), 'event': event, **detail}
        if rep is not None and rep.initialized:
            row.update(std_xy_m=round(rep.std_xy_m, 4), std_yaw_rad=round(rep.std_yaw_rad, 4),
                       fix_t=rep.last_fix_t)
        self.log.append(row)

    def step(self, now, provider, servo):
        rep = provider.report(now)
        hyps = belief_hypotheses(provider)
        settled = now - self.since + 1e-9 >= SETTLE_AFTER_PAN_S
        if self.stage == 'verify' and settled:
            if self._complete(rep, servo) and int(servo.get(6, self.home)) == self.home:
                self.outcome = 'fix'
                self.wait.check_gate(now, ready=True)
                self._event(now, 'complete', rep)
                return None
            self._event(now, 'verify_failed', rep)
            self.stage = 'observe'
        if self.wait.check_gate(now, ready=False) == 'blocked':
            self.outcome = 'blocked'
            self._event(now, 'budget_exhausted', rep, waited_s=self.wait.waited_s)
            return [{'kind': 'hold'}]
        if self.stage in ('pan', 'restore'):
            if int(servo.get(6, self.home)) != self.target:
                step = self._pan_step(servo)
                if not belief_pan_clear(self.guard, servo, step['pan_pulse'], rep, hypotheses=hyps):
                    self._event(now, 'pan_step_refused', rep, target=self.target)
                    if self.stage == 'pan':
                        self.stage = 'observe'          # observe where we are, then the next pan
                    return [{'kind': 'hold'}]
                self.since = now
                return [{'kind': 'hold'}, step]
            self.stage = 'verify' if self.stage == 'restore' else 'observe'
            return [{'kind': 'hold'}]
        if self.stage == 'observe' and settled:
            if self._complete(rep, servo):
                if int(servo.get(6, self.home)) == self.home:
                    self.stage = 'verify'               # already settled at home: verify now
                    return self.step(now, provider, servo)
                self.stage, self.target = 'restore', self.home
                self._event(now, 'restore', rep)
                return self.step(now, provider, servo)
            while self.queue:
                pan = self.queue.pop(0)
                if belief_pan_clear(self.guard, servo, pan, rep, hypotheses=hyps):
                    self.target, self.stage = pan, 'pan'
                    self._event(now, 'pan', rep, target=pan)
                    return self.step(now, provider, servo)
                self._event(now, 'pan_refused', rep, target=pan)
        return [{'kind': 'hold'}]
