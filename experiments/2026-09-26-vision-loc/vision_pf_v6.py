"""VIS6 PF variant: literature-review recipe #1 ("honest updates") on top of the VIS5 filter.

Source of the recipe: ``outputs/lit-review-tagfree-localization-20260928.md`` section 6.1
(issue #216). Three config-selectable components, all OFF by default. With every
component off (``vis6`` absent, ``{}`` or ``{'eta': 1}``) the filter IS the VIS5
filter object path (``vision_pf_v5.make_robust_pf``): same particles, weights,
random-number consumption and reports (tested). ``vision_pf_v5.py`` and every
older PF/CLI file are imported, never modified.

1a ``gating`` -- measurement update gating (Nav2 AMCL ``update_min_d`` /
   ``update_min_a``; Thrun, Burgard & Fox, Probabilistic Robotics 2005; CMU 16-831
   lecture 3 notes on correlated measurements). A vision scan is applied only when,
   since the last applied scan, the ESTIMATED base motion reached ``min_d_m`` or
   ``min_yaw_rad``, or the own commanded arm/pan pose changed by ``min_servo_pulse``
   (a new view). The estimated motion is the weighted mean particle displacement
   AFTER the 1c stall correction, so gating requires 1c: only confirmed stall frames are corrected. Unknown frames and the bounded-stall
   fallback retain command prediction; this is not visual odometry. Mode
   ``skip`` drops repeated scans; ``discount`` applies the k-th repeat of the same
   view with weight 1/(k+1). A max_interval_s timeout forces a discounted scan
   even without motion (a local analogue of AMCL request_nomotion_update).
1b ``eta`` -- likelihood tempering: every applied scan log-likelihood (already
   tempered within the frame by ``effective_columns``) is multiplied by
   ``eta`` in (0, 1] (generalised Bayes learning rate; Thrun et al. AIJ 2001 over-
   confident sensor model remedy; Wu & Martin, Bayesian Analysis 2023 for choosing
   the rate by credible-interval coverage). Selection rule in the VIS6 plan.
1c ``stall`` -- image-based stall detection (``vision_stall_v6``): for two
   consecutive own frames at the same commanded arm pose (both settled, same own load
   state), when the floor texture moved much less than the command-integrated
   prediction the mean motion of that frame interval is pulled back toward zero
   (``gain``) while per-particle spread stays, and the PF velocity state is damped
   (``velocity_gain``, default .5). After 5 consecutive verdicts correction stops
   until a non-stall verdict. This bounded ZUPT does not establish actual zero speed.

Recipe #2 hook: ``update_range(t, reading)`` applies an injected per-particle range
log-likelihood provider (for PR #248's ultrasonic model once merged) with the same
``eta`` and, if gating is on, its own gate state. Nothing here imports PR #248.

Runtime inputs: own frames, own commands, the static map and fixed calibrations
only. No ``eval_only/``, teacher file or simulator state is read.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping

import numpy as np

import vision_pf_v5
import vision_stall_v6 as vst

SCHEMA = 'ugrp.vision_loc.vis6.v1'
GATE_MODES = ('skip', 'discount')
ARM_SERVOS = (3, 4, 5, 6)


def _num(v, name, lo, hi, lo_open=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        raise ValueError(f'{name} must be a finite number, got {v!r}')
    v = float(v)
    if v < lo or v > hi or (lo_open and v <= lo):
        raise ValueError(f'{name}={v!r} outside [{lo}, {hi}]')
    return v


def validate_vis6(cfg: Mapping | None) -> dict:
    """Normalised VIS6 options; wrong keys, types or ranges refused."""
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, Mapping):
        raise ValueError('vis6 must be a mapping')
    unknown = set(cfg) - {'eta', 'gating', 'stall', 'range'}
    if unknown:
        raise ValueError(f'unknown vis6 options {sorted(unknown)}')
    out = {'eta': _num(cfg.get('eta', 1.), 'vis6.eta', 0., 1., lo_open=True)}
    out['stall'] = vst.validate_stall(cfg.get('stall'))
    g = cfg.get('gating')
    if g is not None:
        if not isinstance(g, Mapping) or set(g) - {'min_d_m', 'min_yaw_rad', 'min_servo_pulse', 'mode', 'max_interval_s'}:
            raise ValueError('vis6.gating needs min_d_m, min_yaw_rad, min_servo_pulse, mode and max_interval_s only')
        if not {'min_d_m', 'min_yaw_rad'} <= set(g):
            raise ValueError('vis6.gating needs min_d_m and min_yaw_rad')
        pulse = g.get('min_servo_pulse', 10)
        if isinstance(pulse, bool) or not isinstance(pulse, int) or pulse < 1:
            raise ValueError('vis6.gating.min_servo_pulse must be a positive integer')
        mode = g.get('mode', 'skip')
        if mode not in GATE_MODES:
            raise ValueError(f'vis6.gating.mode must be one of {GATE_MODES}')
        if out['stall'] is None:
            raise ValueError('vis6.gating needs vis6.stall: stall correction must be available (unknown still uses command prediction)')
        g = {'min_d_m': _num(g['min_d_m'], 'vis6.gating.min_d_m', 0., 1., lo_open=True),
             'min_yaw_rad': _num(g['min_yaw_rad'], 'vis6.gating.min_yaw_rad', 0., math.pi, lo_open=True),
             'min_servo_pulse': pulse, 'mode': mode,
             'max_interval_s': _num(g.get('max_interval_s', 2.), 'vis6.gating.max_interval_s', 0., 30., lo_open=True)}
    out['gating'] = g
    r = cfg.get('range')
    if r is not None:
        if not isinstance(r, Mapping) or set(r) - {'enabled'} or not isinstance(r.get('enabled'), bool):
            raise ValueError('vis6.range needs only enabled (boolean)')
        r = {'enabled': bool(r['enabled'])}
    out['range'] = r if r and r['enabled'] else None
    out['active'] = bool(out['eta'] != 1. or out['gating'] or out['stall'] or out['range'])
    return out


class UpdateGate:
    """Nav2-AMCL-style update gate over the estimated motion since the last NEW-information update."""

    def __init__(self, cfg: Mapping | None):
        self.cfg = cfg
        self.d = self.a = 0.
        self.pose: tuple | None = None
        self.started = False
        self.repeats = 0
        self.last_applied_t = None

    def add_motion(self, d: float, a: float) -> None:
        self.d += abs(float(d))
        self.a += abs(float(a))

    def decide(self, pose: tuple | None, t: float = 0.) -> dict:
        """{'apply', 'weight', 'reason'} for an update now (``pose``: own arm/pan pulses, None for a fixed sensor)."""
        if self.cfg is None:
            return {'apply': True, 'weight': 1., 'reason': 'off'}
        c = self.cfg
        if not self.started:
            reason = 'first'
        elif self.d >= c['min_d_m']:
            reason = 'moved'
        elif self.a >= c['min_yaw_rad']:
            reason = 'turned'
        elif (pose is not None and self.pose is not None
              and max(abs(a - b) for a, b in zip(pose, self.pose)) >= c['min_servo_pulse']):
            reason = 'view'
        else:
            reason = None
        if reason is not None:
            return {'apply': True, 'weight': 1., 'reason': reason}
        if self.last_applied_t is not None and t - self.last_applied_t >= c.get('max_interval_s', 2.) - 1e-9:
            return {'apply': True, 'weight': 1./(self.repeats + 2), 'reason': 'timeout'}
        if c['mode'] == 'skip':
            return {'apply': False, 'weight': 0., 'reason': 'static'}
        return {'apply': True, 'weight': 1./(self.repeats + 2), 'reason': 'repeat'}

    def commit(self, pose: tuple | None, decision: Mapping, t: float = 0.) -> None:
        if self.cfg is None:
            return
        if decision['apply']:
            self.last_applied_t = float(t)
        if decision['reason'] in ('repeat', 'timeout', 'static'):
            self.repeats += 1
        else:
            self.d = self.a = 0.
            self.pose, self.started, self.repeats = pose, True, 0

    def state(self) -> dict:
        return {'d_m': round(self.d, 5), 'a_rad': round(self.a, 5), 'repeats': self.repeats, 'last_applied_t': self.last_applied_t}


def arm_pose(pose: Mapping) -> tuple:
    return tuple(int(pose.get(k, pose.get(str(k), -1))) for k in ARM_SERVOS)


RangeProvider = Callable[[np.ndarray, Mapping], np.ndarray]


def make_vis6_pf(m1_module, static_map: Mapping, params: Mapping, measurement: Mapping, obs_params: Mapping,
                 sag_table: Mapping, seed: int, pan_table: Mapping | None = None, robust: Mapping | None = None,
                 motion_v4: Mapping | None = None, sigma_v4: Mapping | None = None, report_v5: Mapping | None = None,
                 vis6: Mapping | None = None, range_provider: RangeProvider | None = None):
    """The VIS5 filter, or its VIS6 subclass when any recipe-1 component is on."""
    cfg = validate_vis6(vis6)
    args = (m1_module, static_map, params, measurement, obs_params, sag_table, seed, pan_table, robust,
            motion_v4, sigma_v4, report_v5)
    if cfg['range'] and range_provider is None:
        raise ValueError('vis6.range is enabled but no range_provider was given (recipe #2 hook)')
    if range_provider is not None and not cfg['range']:
        raise ValueError('range_provider given but vis6.range is off')
    if not cfg['active']:
        return vision_pf_v5.make_robust_pf(*args)
    if (sigma_v4 or {}).get('enabled') or (report_v5 or {}).get('enabled'):
        raise ValueError('VIS6 components cannot be stacked on the rejected VIS4/VIS5 report calibrations')
    # The VIS5 class is defined in a closure; its constructor takes no arguments. Build it once to get the class.
    base = type(vision_pf_v5.make_robust_pf(*args))

    class Vis6Localizer(base):
        def __init__(self):
            super().__init__()
            self.vis6 = cfg
            self.range_provider = range_provider
            self.scan_gate = UpdateGate(cfg['gating'])
            self.range_gate = UpdateGate(cfg['gating'])
            self._scan_weight = 1.
            self._px_prev: np.ndarray | None = None
            self._prev_frame: dict | None = None
            self.v6diag: dict = {}
            self._stall_streak = 0
            self._map_residue = np.zeros(self.n)
            self._map_steps = np.zeros(self.n)
            self._in_prediction = False
            self.motion_by_verdict = {k: [0., 0.] for k in ('stall', 'moving', 'unknown')}
            self.stats.update(gated_skips=0, gated_repeats=0, stall_frames=0, stall_tests=0, stall_moving=0,
                              range_updates=0, range_gated_skips=0, gated_timeouts=0, stall_capped=0)

        # ------------------------------------------------------------ 1b
        def scan_loglik(self, obs, pose):
            ll, n_terms = super().scan_loglik(obs, pose)
            return ll*(self.vis6['eta']*self._scan_weight), n_terms

        def apply_scan(self, t, obs, pose):
            w0 = self._weights()
            raw_ll, n_terms = super().scan_loglik(obs, pose)
            ll = raw_ll*(self.vis6['eta']*self._scan_weight)
            k = min(n_terms, float(self.measurement['effective_columns']))
            fit = np.exp(raw_ll/k) if k > 0 else np.ones(self.n)
            w_avg = float(np.sum(w0*fit))
            self.logw = self.logw + ll
            gains = self._gains(w0, self._weights())
            for key, g in gains.items():
                if g >= float(self.robust['info_gain_min']):
                    self.last_info_t[key] = t
            rec = self.robust['recovery']
            w_diff = 0.
            if rec:
                a_s, a_f = float(rec['alpha_slow']), float(rec['alpha_fast'])
                self.w_slow = w_avg if self.w_slow == 0. else self.w_slow + a_s*(w_avg - self.w_slow)
                self.w_fast = w_avg if self.w_fast == 0. else self.w_fast + a_f*(w_avg - self.w_fast)
                w_diff = max(0., 1. - self.w_fast/self.w_slow) if self.w_slow > 0 else 0.
                w_diff = min(w_diff, float(rec.get('max_fraction', 1.)))
            self._inject = w_diff
            self.diag = {'fit': round(w_avg, 5), 'n_terms': int(n_terms), 'w_slow': round(self.w_slow, 5),
                         'w_fast': round(self.w_fast, 5), 'w_diff': round(w_diff, 5),
                         'gain': [round(gains[k], 4) for k in ('fwd', 'lat', 'yaw')]}

        def _map_logprior(self, px):
            prior = super()._map_logprior(px)
            if getattr(self, '_in_prediction', False) and px is self.px:
                self._map_steps += 1
            return prior

        def predict_to(self, t):
            before = self.logw.copy()
            self._in_prediction = True
            try:
                result = super().predict_to(t)
            finally:
                self._in_prediction = False
            if self.initialized:
                self._map_residue += self.logw - before
            return result

        # ------------------------------------------------------------ frame update
        def update_obs(self, t, obs, pose, image=None):
            self.diag = {}
            self.v6diag = {'eta': self.vis6['eta']}
            self.predict_to(t)
            if self.initialized and self._px_prev is not None:
                raw_motion = self._mean_motion()
                self._stall_step(t, obs, pose, image)
                verdict = self.v6diag.get('stall', {}).get('decision', 'unknown')
                d, a = raw_motion if self.v6diag.get('stall', {}).get('capped') else self._mean_motion()
                self.motion_by_verdict[verdict][0] += d
                self.motion_by_verdict[verdict][1] += a
                self.v6diag['motion_by_verdict'] = {k: list(v) for k, v in self.motion_by_verdict.items()}
                self.scan_gate.add_motion(d, a)
                self.range_gate.add_motion(d, a)
                self.v6diag['motion'] = [round(d, 5), round(a, 5)]
            used = False
            if self.initialized and obs is not None:
                if not self.settled(t):
                    self.stats['unsettled_skips'] += 1
                elif int(obs.informative.sum()) >= int(self.measurement['min_columns']):
                    view = arm_pose(pose)
                    gate = self.scan_gate.decide(view, t)
                    self.v6diag['gate'] = {**gate, **self.scan_gate.state()}
                    if gate['apply']:
                        self._scan_weight = gate['weight']
                        try:
                            self.apply_scan(t, obs, pose)
                        finally:
                            self._scan_weight = 1.
                        self.scan_gate.commit(view, gate, t)
                        self.stats['scan_updates'] += 1
                        self.stats['scan_columns'] += int(obs.informative.sum())
                        self.stats['gated_timeouts'] += int(gate['reason'] == 'timeout')
                        self.stats['gated_repeats'] += int(gate['reason'] == 'repeat')
                        self.last_scan_t = t
                        used = True
                    else:
                        self.stats['gated_skips'] += 1
                        self.scan_gate.commit(view, gate, t)
            if self.initialized:
                self._normalize_and_resample()
                self._px_prev = self.px.copy()
                self._map_residue.fill(0.)
                self._map_steps.fill(0.)
            self._remember_frame(t, pose, image)
            est = self.estimate()
            est['since_scan_s'] = None if self.last_scan_t is None else round(t - self.last_scan_t, 3)
            est['measured'] = used
            return est

        def _motion_weights(self):
            # Undo only pending prediction penalties; retain any range evidence.
            logw = self.logw - self._map_residue
            w = np.exp(logw - logw.max())
            return w/w.sum()

        def _mean_motion(self) -> tuple[float, float]:
            """Weighted mean particle displacement (m, |rad|) since the last frame (after the 1c correction)."""
            w = self._motion_weights()
            d = self.px - self._px_prev
            d[:, 2] = self.wrap(d[:, 2])
            return (math.hypot(float(np.sum(w*d[:, 0])), float(np.sum(w*d[:, 1]))),
                    abs(float(np.sum(w*d[:, 2]))))

        def _predicted_delta(self) -> np.ndarray:
            """Weighted mean of each particle's displacement since the last frame, in its own earlier base frame."""
            w = self._motion_weights()
            d = self.px - self._px_prev
            d[:, 2] = self.wrap(d[:, 2])
            c, s = np.cos(self._px_prev[:, 2]), np.sin(self._px_prev[:, 2])
            body = np.column_stack([c*d[:, 0] + s*d[:, 1], -s*d[:, 0] + c*d[:, 1], d[:, 2]])
            return np.sum(w[:, None]*body, axis=0)

        # ------------------------------------------------------------ 1c
        def _remember_frame(self, t, pose, image):
            st = self.vis6['stall']
            if st is None or image is None:
                self._prev_frame = None
                return
            self._prev_frame = {'t': float(t), 'img': vst.prepare(image, int(st['blur_ksize'])),
                                'arm': arm_pose(pose), 'loaded': bool(self.load.loaded),
                                'settled': bool(self.settled(t))}

        def _stall_step(self, t, obs, pose, image):
            st, prev = self.vis6['stall'], self._prev_frame
            if st is None:
                return
            info = {'decision': 'unknown', 'reason': None}
            self.v6diag['stall'] = info
            if image is None or prev is None:
                self._stall_streak = 0
                info['reason'] = 'no_previous_frame'
                return
            if (prev['arm'] != arm_pose(pose) or prev['loaded'] != bool(self.load.loaded)
                    or not prev['settled'] or not self.settled(t) or t - prev['t'] > st['max_dt_s']):
                self._stall_streak = 0
                info['reason'] = 'not_a_static_arm_pair'
                return
            delta = self._predicted_delta()
            info['pred_m'] = round(math.hypot(float(delta[0]), float(delta[1])), 5)
            info['pred_yaw_rad'] = round(float(delta[2]), 5)
            info['prev_t'] = prev['t']
            img1 = vst.prepare(image, int(st['blur_ksize']))
            origin, rot = vst.camera_pose(self.column_model_for(pose))
            rows = (vst.floor_min_rows(obs, margin_px=float(st['obs_margin_px']))
                    if st['obs_floor_mask'] and obs is not None else None)
            res = vst.stall_test(prev['img'], img1, origin, rot, delta, st, rows)
            info.update(res)
            self.stats['stall_tests'] += 1
            if res['decision'] == 'moving':
                self.stats['stall_moving'] += 1
            if res['decision'] != 'stall':
                self._stall_streak = 0
                return
            self._stall_streak += 1
            info['consecutive_stall'] = self._stall_streak
            info['capped'] = self._stall_streak > st['max_consecutive_stall']
            if info['capped']:
                self.stats['stall_capped'] += 1
                return
            g = float(st['gain'])
            d = self.px - self._px_prev
            d[:, 2] = self.wrap(d[:, 2])
            # Remove only the mean body motion, preserving each particle's process spread.
            c, sn = np.cos(self._px_prev[:, 2]), np.sin(self._px_prev[:, 2])
            correction = np.column_stack([c*delta[0] - sn*delta[1], sn*delta[0] + c*delta[1],
                                          np.full(self.n, delta[2])])
            self.px = self._px_prev + d - g*correction
            self.px[:, 2] = self.wrap(self.px[:, 2])
            corrected_prior = self._map_steps*self._map_logprior(self.px)
            self.logw = self.logw - self._map_residue + corrected_prior
            self._map_residue = corrected_prior
            self.vel = self.vel*(1. - float(st['velocity_gain']))
            self.stats['stall_frames'] += 1

        # ------------------------------------------------------------ recipe #2 hook
        def update_range(self, t, reading: Mapping) -> dict:
            """Apply an injected range likelihood (recipe #2, e.g. PR #248) with the same eta and its own gate."""
            if self.vis6['range'] is None or self.range_provider is None:
                raise RuntimeError('vis6.range is off or no range_provider')
            self.predict_to(t)
            gate = self.range_gate.decide(None, t)
            self.v6diag['range_gate'] = {**gate, **self.range_gate.state()}
            if self.initialized and gate['apply']:
                ll = np.asarray(self.range_provider(self.px.copy(), reading), float)
                if ll.shape != (self.n,) or not np.all(np.isfinite(ll)):
                    raise ValueError('range_provider must return one finite log-likelihood per particle')
                self.logw = self.logw + ll*(self.vis6['eta']*gate['weight'])
                self.range_gate.commit(None, gate, t)
                self.stats['range_updates'] += 1
                # Defer pending map penalties until the camera can correct motion. Otherwise
                # range resampling could irrevocably select particles on the uncorrected path.
                self.logw -= self._map_residue
                self._normalize_and_resample()
                self.logw += self._map_residue
            elif not gate['apply']:
                self.stats['range_gated_skips'] += 1
                self.range_gate.commit(None, gate, t)
            return self.estimate()

        # Frozen VIS5 resampling order/RNG, with ancestry for the previous camera frame.
        def _normalize_and_resample(self):
            """M1 low-variance resampling (PythonRobotics), plus the stuck mode and augmented-MCL injection.

            With no injection this consumes the random generator exactly like the M1
            method (one uniform, one roughening draw), so ``robust = {}`` is the
            round-2 filter.
            """
            self.logw -= self.logw.max()
            w = np.exp(self.logw)
            w /= w.sum()
            n_eff = 1./np.sum(w*w)
            self.diag['ess_pre'] = round(float(n_eff), 1)
            inject = self._inject
            self._inject = 0.
            if n_eff >= self.params['resample_ratio']*self.n and inject <= 0.:
                self.logw = np.log(np.maximum(w, 1e-300))
                return
            n_new = int(self.rng.binomial(self.n, inject)) if inject > 0. else 0
            m = self.n - n_new
            positions = (np.arange(m) + self.rng.uniform())/m if m else np.zeros(0)
            idx = np.minimum(np.searchsorted(np.cumsum(w), positions), self.n - 1)
            px, scale, stuck = self.px[idx].copy(), self.scale[idx].copy(), self.stuck[idx].copy()
            rough = np.asarray(self.params.get('roughen', [0., 0., 0.]), float)
            if np.any(rough > 0) and m:
                px += self.rng.normal(size=px.shape)*rough
                px[:, 2] = self.wrap(px[:, 2])
            if n_new:
                sd = float(self.params['motion_loaded' if self.load.loaded else 'motion']['scale_std'])
                px = np.concatenate([px, self._random_poses(n_new)])
                scale = np.concatenate([scale, 1. + self.rng.normal(size=(n_new, 3))*sd])
                stuck = np.concatenate([stuck, np.zeros(n_new, bool)])
                self.stats['injections'] += 1
                self.stats['injected_particles'] += n_new
                self.w_slow = self.w_fast = 0.                  # Nav2: avoid spiralling into randomness
            if self._px_prev is not None:
                self._px_prev = np.concatenate([self._px_prev[idx], px[m:]])
            self._map_residue = np.concatenate([self._map_residue[idx], np.zeros(n_new)])
            self._map_steps = np.concatenate([self._map_steps[idx], np.zeros(n_new)])
            self.px, self.scale, self.stuck = px, scale, stuck
            self.logw = np.zeros(self.n)
            self.stats['resamples'] += 1
            self.diag['injected'] = n_new

        # ------------------------------------------------------------ report
        def estimate(self):
            est = super().estimate()
            if est.get('initialized'):
                est['vis6'] = dict(self.v6diag)
            return est

    return Vis6Localizer()
