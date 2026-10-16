"""Round-3 particle-filter extensions of the vision localizer (recovery, stuck mode, load-state slip scales).

``make_robust_pf`` subclasses ``vision_loc.VisionScanLocalizer`` (itself a
subclass of the hash-checked M1 ``OwnCamLocalizer``); nothing here reads the
simulator, ``eval_only/`` or ``teacher/``. Every extension is off unless the
config's ``robust`` block enables it, so ``robust = {}`` reproduces the round-2
filter exactly (same random-number consumption; tested).

1. **Augmented MCL** (``recovery``). Probabilistic Robotics (Thrun, Burgard, Fox
   2005) Table 8.3 as implemented in Nav2 AMCL ``nav2_amcl/src/pf/pf.c``
   (``pf_update_sensor`` / ``pf_update_resample``, LGPL-2.1-or-later; the
   algorithm is re-implemented here, no code copied): running averages
   ``w_slow``/``w_fast`` of the mean measurement likelihood, and at the next
   resampling each particle is replaced by a random pose with probability
   ``w_diff = max(0, 1 - w_fast/w_slow)``; after an injection both averages are
   reset (Nav2). Differences, all recorded: (a) the likelihood averaged is the
   per-column geometric-mean probability ``exp(ll/min(n_terms, effective_columns))``
   of each particle (the column count varies from frame to frame, the robust
   floor keeps it in [outlier_prob, 1]), weighted by the prior weights because
   this filter does not resample every frame; (b) an injection forces a
   resampling; (c) optional ``max_fraction`` cap (1 = Nav2) and a
   ``uniform_share`` of the random poses drawn uniformly over the free map
   (Nav2 ``uniformPoseGenerator``), the rest from a Gaussian around the current
   estimate (``local_std``).
2. **Near-stationary motion hypothesis** (``stuck``). A per-particle mode: while
   own wheel commands are active, a particle enters the mode at rate
   ``enter_per_s`` and leaves it at ``exit_per_s``; in the mode it keeps its pose
   (plus a small jitter) whatever is commanded, so a robot wedged against a box
   or a peer that keeps issuing commands (round-2 s909/s915: ~600 SIM s,
   3.7 cm of motion, 2,995 wheel commands) keeps a hypothesis at its true pose.
   The mode is copied on resampling.
3. **Load-state slip scales** (``loaded_scale_reinit``). The per-particle slip
   scales are redrawn from the new plant's ``scale_std`` when the own load state
   changes (the M1 filter kept the unloaded scales after a grasp and never used
   ``motion_loaded.scale_std``).
4. **Diagnostics** (always): per-frame fit quality, ``w_slow``/``w_fast``/``w_diff``,
   effective sample size before resampling, and per-direction information gain
   (share of the forward / lateral / yaw variance, in the robot frame at the
   estimate, removed by this frame's measurement). ``since_lateral_info_s``
   separates "a scan was applied" from "the lateral position was corrected".
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

import vision_loc as vl


def _num(v, name, lo=0., hi=math.inf, lo_open=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        raise ValueError(f'{name} must be a finite number, got {v!r}')
    if float(v) < lo or float(v) > hi or (lo_open and float(v) <= lo):
        raise ValueError(f'{name}={v!r} outside [{lo}, {hi}]')
    return float(v)


def validate_robust(robust: Mapping | None) -> dict:
    """Round-3 options merged over ``vision_loc.DEFAULT_ROBUST``; wrong types, NaN/Inf and out-of-range refused."""
    if robust is not None and not isinstance(robust, Mapping):
        raise ValueError(f'robust must be a mapping, got {type(robust).__name__}')
    unknown = set(robust or {}) - set(vl.DEFAULT_ROBUST)
    if unknown:
        raise ValueError(f'unknown robust options {sorted(unknown)}')
    cfg = {**vl.DEFAULT_ROBUST, **(robust or {})}
    if not isinstance(cfg['loaded_scale_reinit'], bool):
        raise ValueError('loaded_scale_reinit must be true or false')
    if cfg['estimate'] not in ('mean', 'dominant'):
        raise ValueError(f"estimate must be 'mean' or 'dominant', got {cfg['estimate']!r}")
    _num(cfg['info_gain_min'], 'info_gain_min', 0., 1.)
    st = cfg['stuck']
    if st is not None:
        if not isinstance(st, Mapping) or not {'enter_per_s', 'exit_per_s'} <= set(st):
            raise ValueError('stuck needs enter_per_s and exit_per_s')
        _num(st['enter_per_s'], 'stuck.enter_per_s', 0., 10., lo_open=True)
        _num(st['exit_per_s'], 'stuck.exit_per_s', 0., 10.)
        for k in ('jitter_xy_m', 'jitter_yaw_rad'):
            if k in st:
                _num(st[k], f'stuck.{k}', 0., .1)
    rec = cfg['recovery']
    if rec is not None:
        if not isinstance(rec, Mapping) or not {'alpha_slow', 'alpha_fast'} <= set(rec):
            raise ValueError('recovery needs alpha_slow and alpha_fast')
        a_s = _num(rec['alpha_slow'], 'recovery.alpha_slow', 0., 1., lo_open=True)
        a_f = _num(rec['alpha_fast'], 'recovery.alpha_fast', 0., 1., lo_open=True)
        if a_f <= a_s:
            raise ValueError('recovery.alpha_fast must exceed alpha_slow')
        _num(rec.get('max_fraction', 1.), 'recovery.max_fraction', 0., 1., lo_open=True)
        _num(rec.get('uniform_share', 1.), 'recovery.uniform_share', 0., 1.)
        std = rec.get('local_std', [.3, .3, .35])
        if not isinstance(std, (list, tuple)) or len(std) != 3:
            raise ValueError('recovery.local_std needs three numbers')
        for i, v in enumerate(std):
            _num(v, f'recovery.local_std[{i}]', 0., 5., lo_open=True)
    return cfg


def make_robust_pf(m1_module, static_map: Mapping, params: Mapping, measurement: Mapping, obs_params: Mapping,
                   sag_table: Mapping, seed: int, pan_table: Mapping | None = None, robust: Mapping | None = None):
    base = vl.vision_pf_class(m1_module)
    cfg = validate_robust(robust)

    class RobustVisionLocalizer(base):
        def __init__(self):
            super().__init__(static_map, params, measurement, obs_params, sag_table, seed, pan_table)
            self.robust = cfg
            self.stuck = np.zeros(self.n, bool)
            self.w_slow = self.w_fast = 0.
            self._inject = 0.
            self.diag: dict = {}
            self.last_info_t = {'fwd': None, 'lat': None, 'yaw': None}
            self.stats.update(injections=0, injected_particles=0, load_scale_resets=0)

        # ------------------------------------------------------------ motion
        def command(self, row):
            was = self.load.loaded
            super().command(row)
            if self.robust['loaded_scale_reinit'] and self.initialized and self.load.loaded != was:
                sd = float(self.params['motion_loaded' if self.load.loaded else 'motion']['scale_std'])
                self.scale = 1. + self.rng.normal(size=(self.n, 3))*sd
                self.stats['load_scale_resets'] += 1

        def predict_to(self, t):
            st = self.robust['stuck']
            if not st or not self.initialized or t <= self.t + 1e-9:
                return super().predict_to(t)
            t0, before, logw0 = self.t, self.px.copy(), self.logw.copy()
            wheels = bool(np.any(self.cmd)) and t0 < self.cmd_expires - 1e-9 or bool(np.any(np.abs(self.vel) > 1e-6))
            super().predict_to(t)
            if not wheels:
                return None
            dt = self.t - t0
            enter = (self.rng.random(self.n) < 1. - math.exp(-float(st['enter_per_s'])*dt)) & ~self.stuck
            leave = (self.rng.random(self.n) < 1. - math.exp(-float(st['exit_per_s'])*dt)) & self.stuck
            self.stuck = (self.stuck | enter) & ~leave
            s = self.stuck
            if s.any():
                k = int(s.sum())
                jit = np.asarray([st.get('jitter_xy_m', .002)]*2 + [st.get('jitter_yaw_rad', .002)], float)
                self.px[s] = before[s] + self.rng.normal(size=(k, 3))*jit*math.sqrt(dt)
                self.px[s, 2] = self.wrap(self.px[s, 2])
                steps = max(1, math.ceil(dt/self.step_s - 1e-9))
                self.logw[s] = logw0[s] + steps*self._map_logprior(self.px[s])
            return None

        step_s = m1_module.STEP_S

        # ------------------------------------------------------------ measurement
        def update_obs(self, t, obs, pose):
            self.diag = {}
            return super().update_obs(t, obs, pose)

        def apply_scan(self, t, obs, pose):
            w0 = self._weights()
            ll, n_terms = self.scan_loglik(obs, pose)
            k = min(n_terms, float(self.measurement['effective_columns']))
            fit = np.exp(ll/k) if k > 0 else np.ones(self.n)
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

        def _weights(self):
            w = np.exp(self.logw - self.logw.max())
            return w/w.sum()

        def _gains(self, w0, w1):
            """Share of the forward / lateral / yaw variance (robot frame at the estimate) removed by w0 -> w1."""
            out = {}
            yaw = math.atan2(float(np.sum(w1*np.sin(self.px[:, 2]))), float(np.sum(w1*np.cos(self.px[:, 2]))))
            c, s = math.cos(yaw), math.sin(yaw)
            axes = {'fwd': c*self.px[:, 0] + s*self.px[:, 1], 'lat': -s*self.px[:, 0] + c*self.px[:, 1]}
            for key, v in axes.items():
                out[key] = self._var_gain(v, w0, w1)
            d = self.wrap(self.px[:, 2] - yaw)
            out['yaw'] = self._var_gain(d, w0, w1)
            return out

        @staticmethod
        def _var_gain(v, w0, w1):
            def var(w):
                m = float(np.sum(w*v))
                return float(np.sum(w*(v - m)**2))
            v0 = var(w0)
            return 0. if v0 <= 1e-12 else float(np.clip(1. - var(w1)/v0, -1., 1.))

        # ------------------------------------------------------------ resampling (+ injection)
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
            self.px, self.scale, self.stuck = px, scale, stuck
            self.logw = np.zeros(self.n)
            self.stats['resamples'] += 1
            self.diag['injected'] = n_new

        def _random_poses(self, k: int) -> np.ndarray:
            rec = self.robust['recovery']
            n_uni = int(self.rng.binomial(k, float(rec.get('uniform_share', 1.))))
            out = [self._uniform_free(n_uni)]
            if k - n_uni:
                w = self._weights()
                yaw = math.atan2(float(np.sum(w*np.sin(self.px[:, 2]))), float(np.sum(w*np.cos(self.px[:, 2]))))
                mean = np.array([float(np.sum(w*self.px[:, 0])), float(np.sum(w*self.px[:, 1])), yaw])
                loc = mean + self.rng.normal(size=(k - n_uni, 3))*np.asarray(rec.get('local_std', [.3, .3, .35]), float)
                bad = self._map_logprior(loc) < 0
                if bad.any():
                    loc[bad] = self._uniform_free(int(bad.sum()))
                out.append(loc)
            px = np.concatenate(out)
            px[:, 2] = self.wrap(px[:, 2])
            return px

        def _uniform_free(self, k: int) -> np.ndarray:
            """Uniform over the free map (inside the bounds, outside the clearance-expanded walls), uniform yaw."""
            x0, x1, y0, y1 = self.bounds
            out = np.zeros((0, 3))
            while len(out) < k:
                c = np.column_stack([self.rng.uniform(x0, x1, 2*k), self.rng.uniform(y0, y1, 2*k),
                                     self.rng.uniform(-math.pi, math.pi, 2*k)])
                out = np.concatenate([out, c[self._map_logprior(c) == 0.]])
            return out[:k]

        # ------------------------------------------------------------ report
        def estimate(self):
            if self.robust['estimate'] == 'dominant' and self.initialized and self.stuck.any() and not self.stuck.all():
                return self._dominant_estimate()
            est = super().estimate()
            return self._with_diag(est)

        def _with_diag(self, est):
            if est.get('initialized'):
                w = self._weights()
                est['diag'] = {**self.diag, 'stuck_share': round(float(self.stuck.mean()), 4),
                               'stuck_weight': round(float(w[self.stuck].sum()), 4)}
                est['since_lateral_info_s'] = (None if self.last_info_t['lat'] is None
                                               else round(self.t - self.last_info_t['lat'], 3))
            return est

        def _dominant_estimate(self):
            """The M1 estimate computed over the motion mode (stuck / moving) holding most of the weight."""
            w = self._weights()
            sel = self.stuck if float(w[self.stuck].sum()) > .5 else ~self.stuck
            px, logw = self.px, self.logw
            try:
                self.px, self.logw = px[sel], logw[sel]
                est = super().estimate()
            finally:
                self.px, self.logw = px, logw
            est['n_eff_all'] = float(1./np.sum(w*w))
            est['mode'] = 'stuck' if sel is self.stuck else 'moving'
            return self._with_diag(est)

    return RobustVisionLocalizer()
