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
   AFTER the 1c stall correction, so gating requires 1c: motion is never judged
   from integrated commands alone (refused at construction otherwise). Mode
   ``skip`` drops repeated scans; ``discount`` applies the k-th repeat of the same
   view with weight 1/(k+1).
1b ``eta`` -- likelihood tempering: every applied scan log-likelihood (already
   tempered within the frame by ``effective_columns``) is multiplied by
   ``eta`` in (0, 1] (generalised Bayes learning rate; Thrun et al. AIJ 2001 over-
   confident sensor model remedy; Wu & Martin, Bayesian Analysis 2023 for choosing
   the rate by credible-interval coverage). Selection rule in the VIS6 plan.
1c ``stall`` -- image-based stall detection (``vision_stall_v6``): for two
   consecutive own frames at the same commanded arm pose (both settled, same own load
   state), when the floor texture moved much less than the command-integrated
   prediction the prediction of that frame interval is pulled back toward zero
   (``gain``) and the PF velocity state toward zero (``velocity_gain``): a ZUPT.

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
        if not isinstance(g, Mapping) or set(g) - {'min_d_m', 'min_yaw_rad', 'min_servo_pulse', 'mode'}:
            raise ValueError('vis6.gating needs min_d_m, min_yaw_rad, min_servo_pulse and mode only')
        if not {'min_d_m', 'min_yaw_rad'} <= set(g):
            raise ValueError('vis6.gating needs min_d_m and min_yaw_rad')
        pulse = g.get('min_servo_pulse', 10)
        if isinstance(pulse, bool) or not isinstance(pulse, int) or pulse < 1:
            raise ValueError('vis6.gating.min_servo_pulse must be a positive integer')
        mode = g.get('mode', 'skip')
        if mode not in GATE_MODES:
            raise ValueError(f'vis6.gating.mode must be one of {GATE_MODES}')
        if out['stall'] is None:
            raise ValueError('vis6.gating needs vis6.stall: motion must not be judged from integrated commands alone')
        g = {'min_d_m': _num(g['min_d_m'], 'vis6.gating.min_d_m', 0., 1., lo_open=True),
             'min_yaw_rad': _num(g['min_yaw_rad'], 'vis6.gating.min_yaw_rad', 0., math.pi, lo_open=True),
             'min_servo_pulse': pulse, 'mode': mode}
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

    def add_motion(self, d: float, a: float) -> None:
        self.d += abs(float(d))
        self.a += abs(float(a))

    def decide(self, pose: tuple | None) -> dict:
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
        if c['mode'] == 'skip':
            return {'apply': False, 'weight': 0., 'reason': 'static'}
        return {'apply': True, 'weight': 1./(self.repeats + 2), 'reason': 'repeat'}

    def commit(self, pose: tuple | None, decision: Mapping) -> None:
        if not decision['apply'] or self.cfg is None:
            return
        if decision['reason'] == 'repeat':
            self.repeats += 1
        else:
            self.d = self.a = 0.
            self.pose, self.started, self.repeats = pose, True, 0

    def state(self) -> dict:
        return {'d_m': round(self.d, 5), 'a_rad': round(self.a, 5), 'repeats': self.repeats}


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
    if not cfg['active']:
        if range_provider is not None:
            raise ValueError('range_provider given but vis6.range is off')
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
            self.stats.update(gated_skips=0, gated_repeats=0, stall_frames=0, stall_tests=0, stall_moving=0,
                              range_updates=0, range_gated_skips=0)

        # ------------------------------------------------------------ 1b
        def scan_loglik(self, obs, pose):
            ll, n_terms = super().scan_loglik(obs, pose)
            return ll*(self.vis6['eta']*self._scan_weight), n_terms

        # ------------------------------------------------------------ frame update
        def update_obs(self, t, obs, pose, image=None):
            self.diag = {}
            self.v6diag = {'eta': self.vis6['eta']}
            self.predict_to(t)
            if self.initialized and self._px_prev is not None:
                self._stall_step(t, obs, pose, image)
                d, a = self._mean_motion()
                self.scan_gate.add_motion(d, a)
                self.range_gate.add_motion(d, a)
                self.v6diag['motion'] = [round(d, 5), round(a, 5)]
            used = False
            if self.initialized and obs is not None:
                if not self.settled(t):
                    self.stats['unsettled_skips'] += 1
                elif int(obs.informative.sum()) >= int(self.measurement['min_columns']):
                    view = arm_pose(pose)
                    gate = self.scan_gate.decide(view)
                    self.v6diag['gate'] = {**gate, **self.scan_gate.state()}
                    if gate['apply']:
                        self._scan_weight = gate['weight']
                        try:
                            self.apply_scan(t, obs, pose)
                        finally:
                            self._scan_weight = 1.
                        self.scan_gate.commit(view, gate)
                        self.stats['scan_updates'] += 1
                        self.stats['scan_columns'] += int(obs.informative.sum())
                        self.stats['gated_repeats'] += int(gate['reason'] == 'repeat')
                        self.last_scan_t = t
                        used = True
                    else:
                        self.stats['gated_skips'] += 1
            if self.initialized:
                self._normalize_and_resample()
                self._px_prev = self.px.copy()
            self._remember_frame(t, pose, image)
            est = self.estimate()
            est['since_scan_s'] = None if self.last_scan_t is None else round(t - self.last_scan_t, 3)
            est['measured'] = used
            return est

        def _mean_motion(self) -> tuple[float, float]:
            """Weighted mean particle displacement (m, |rad|) since the last frame (after the 1c correction)."""
            w = self._weights()
            d = self.px - self._px_prev
            d[:, 2] = self.wrap(d[:, 2])
            return (math.hypot(float(np.sum(w*d[:, 0])), float(np.sum(w*d[:, 1]))),
                    abs(float(np.sum(w*d[:, 2]))))

        def _predicted_delta(self) -> np.ndarray:
            """Weighted mean of each particle's displacement since the last frame, in its own earlier base frame."""
            w = self._weights()
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
                info['reason'] = 'no_previous_frame'
                return
            if (prev['arm'] != arm_pose(pose) or prev['loaded'] != bool(self.load.loaded)
                    or not prev['settled'] or not self.settled(t) or t - prev['t'] > st['max_dt_s']):
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
                return
            g = float(st['gain'])
            d = self.px - self._px_prev
            d[:, 2] = self.wrap(d[:, 2])
            self.px = self._px_prev + (1. - g)*d
            self.px[:, 2] = self.wrap(self.px[:, 2])
            self.vel = self.vel*(1. - float(st['velocity_gain']))
            self.stats['stall_frames'] += 1

        # ------------------------------------------------------------ recipe #2 hook
        def update_range(self, t, reading: Mapping) -> dict:
            """Apply an injected range likelihood (recipe #2, e.g. PR #248) with the same eta and its own gate."""
            if self.vis6['range'] is None or self.range_provider is None:
                raise RuntimeError('vis6.range is off or no range_provider')
            self.predict_to(t)
            gate = self.range_gate.decide(None)
            self.v6diag['range_gate'] = {**gate, **self.range_gate.state()}
            if self.initialized and gate['apply']:
                ll = np.asarray(self.range_provider(self.px.copy(), reading), float)
                if ll.shape != (self.n,) or not np.all(np.isfinite(ll)):
                    raise ValueError('range_provider must return one finite log-likelihood per particle')
                if self._px_prev is not None:
                    # Resampling reorders the particles: book the motion since the last frame now and restart
                    # the frame-to-frame reference; the next frame pair has no full-interval prediction, so its
                    # stall test is skipped.
                    d, a = self._mean_motion()
                    self.scan_gate.add_motion(d, a)
                    self.range_gate.add_motion(d, a)
                self.logw = self.logw + ll*(self.vis6['eta']*gate['weight'])
                self.range_gate.commit(None, gate)
                self.stats['range_updates'] += 1
                self._normalize_and_resample()
                if self._px_prev is not None:
                    self._px_prev = self.px.copy()
                    self._prev_frame = None
            elif not gate['apply']:
                self.stats['range_gated_skips'] += 1
            return self.estimate()

        # ------------------------------------------------------------ report
        def estimate(self):
            est = super().estimate()
            if est.get('initialized'):
                est['vis6'] = dict(self.v6diag)
            return est

    return Vis6Localizer()
