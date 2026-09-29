"""Predict-only replay of a recorded carry leg through the registered particle-filter motion model.

Uses the real ``harness.owncam_localizer.OwnCamLocalizer`` (unchanged) with the same loaded profile the b-v6g/b-v6h
runs used (calibration_loop_v2 params + carry_dr_fit_cal1 profile + carry_general_fit deadband/drift + the 'pm+edge'
yaw bias), starts it from the RECORDED posterior (mean, covariance) at the leg start and feeds the RECORDED base
commands. No images, no measurement update: valid for the tag-blind carry legs (the recorded observation quality is
'no_usable_geometry' throughout the carry drive). The partner-mean yaw coupling (only affects yaw) is not replayed.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from harness import owncam_carry_v6e as v6e                       # noqa: E402
from harness.owncam_localizer import OwnCamLocalizer, wrap       # noqa: E402
from sim.zone_landmarks import tagged_map                          # noqa: E402

from xb_common import base_cmds                                    # noqa: E402

_MAP = None


def static_map():
    global _MAP
    if _MAP is None:
        _MAP = tagged_map('zone_wide_door_tags_v2')
    return _MAP


def base_params():
    p = json.load(open(REPO/'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'))['params']
    unloaded = p['motion']['scale_std']
    profile, _ = v6e.load_profile(unloaded)
    gfit, _ = v6e.load_pair_fit(general=True)
    profile['deadband'] = {k: [float(v) for v in gfit['deadband_cmd'][k]] for k in ('c0', 'u1')}
    profile['drift_ratio_std'] = float(gfit['drift_ratio_std'])
    profile['yaw_bias_std_rad_s'] = float(gfit['b_rad_s']['pm+edge'])
    p = copy.deepcopy(p)
    p['motion_loaded'] = {**p['motion_loaded'], **copy.deepcopy(profile)}
    return p


def variant_params(fwd_gain_mult=1.0, noise_abs_x=None, scale_std_x=None, extra_white_x=0.0, tau=None, white_x_mult=1.0, scale_x_mult=1.0):
    """Registered loaded profile with candidate motion-model changes (only keys a controller could set)."""
    p = base_params()
    ml = p['motion_loaded']
    g = np.array(ml['gain'], float)
    g[0, 0] *= fwd_gain_mult
    ml['gain'] = g.tolist()
    if noise_abs_x is not None:
        ml['noise_abs'] = [float(noise_abs_x), ml['noise_abs'][1], ml['noise_abs'][2]]
    if extra_white_x:
        ml['noise_abs'] = [float(np.hypot(ml['noise_abs'][0], extra_white_x)), ml['noise_abs'][1], ml['noise_abs'][2]]
    if scale_std_x is not None:
        ml['load_transition']['scale_std'][0] = float(scale_std_x)
    if tau is not None:
        ml['tau_s'] = float(tau)
    ml['noise_abs'][0] = float(ml['noise_abs'][0]*white_x_mult)
    ml['load_transition']['scale_std'][0] = float(ml['load_transition']['scale_std'][0]*scale_x_mult)
    return p


def replay_leg(params, mean0, cov0, cmds_leg, t0, t_end, seed=0, n=2000):
    """Start at ``t0`` from N(mean0, cov0) (loaded), feed base commands, return particles at ``t_end``.

    ``cmds_leg``: list of (t, forward, left, turn, expires) with t0 <= t (as ``xb_common.base_cmds``).
    """
    prm = copy.deepcopy(params)
    prm['particles'] = n
    loc = OwnCamLocalizer(static_map(), prm, seed=seed)
    rng = np.random.default_rng(seed + 12345)
    px = rng.multivariate_normal(np.asarray(mean0, float), np.asarray(cov0, float), size=n)
    px[:, 2] = wrap(px[:, 2])
    loc.px = px
    loc.logw = np.zeros(n)
    loc.initialized = True
    loc.t = float(t0)
    loc.load.loaded = True
    loc._init_plant_state()
    traj = []
    for (t, f, l, u, exp) in cmds_leg:
        loc.command({'t': t, 'kind': 'mecanum' if exp > t else 'hold', 'forward': f, 'left': l, 'turn': u,
                     'duration_s': exp - t})
    loc.predict_to(float(t_end))
    return loc.px.copy(), loc


def moments(px):
    yaw0 = px[:, 2].mean() if False else np.angle(np.exp(1j*px[:, 2]).mean())
    d = np.column_stack([px[:, 0], px[:, 1], wrap(px[:, 2] - yaw0)])
    m = d.mean(0)
    cov = np.cov(d.T)
    return np.array([m[0], m[1], wrap(yaw0 + m[2])]), cov
