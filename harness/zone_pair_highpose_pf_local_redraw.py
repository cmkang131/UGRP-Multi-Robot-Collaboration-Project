"""v98 local re-draw of the augmented-MCL random poses (independent review #363 P1-2).

What broke. R1 (``PF_RECOVERY`` in ``vision_pose_source_highpose``) was registered as *local* recovery: random poses are drawn
around the own estimate (``uniform_share`` 0, ``local_std`` 0.1 m / 0.1 m / 0.2 rad) because uniform injection over the map was
seen to move the estimate metres away. The frozen ``vision_pf._random_poses`` does that, but replaces every candidate that falls
inside a clearance-expanded wall with ``_uniform_free()``, a uniform draw over the whole free map. Next to a door or wall that is
not rare: with the registered calibration C, map ``zone_wide_door_geometry_v3``, seed 911 and a synthetic own belief at
(2.20, 0.05, 0) 101 of 2000 candidates became global (92 of them more than 1 m from the belief, the farthest 4.22 m; at (1.0, 1.1, 0)
16 of 2000, up to 5.57 m). R1 therefore was not local.

Fix (this module only; the frozen PF, the frozen scan helpers and the PF consistency module are untouched). ``install`` binds an
instance attribute ``pf._random_poses`` (``zone_final_pair_scan.resample`` looks the method up on the instance, as it does for
every other v98 override). It keeps the frozen proposal, mean/yaw and ``local_std`` exactly and changes only what happens to a
candidate that is not valid:

* a candidate is *valid* when ``_map_logprior`` is 0 (inside the bounds, outside the expanded walls) and it lies within
  ``bound_sigma`` standard deviations of the belief mean on every axis;
* an invalid candidate is drawn again from the same Gaussian (same ``local_std``, no scale was changed), in at most
  ``max_redraw_rounds`` vectorised rounds over the still-invalid slots (rejection sampling against the map prior); the
  neighbourhood is therefore a hard box of ``bound_sigma * local_std`` around the belief mean, never the whole map;
* a slot still invalid after the last round (the belief mean sits inside or against a wall so that almost every nearby pose is
  blocked) keeps an existing particle: one pose drawn from the current weighted particle set restricted to valid particles (all
  particles if none is valid). The method still returns exactly ``k`` rows because the caller concatenates ``k`` new scale,
  stuck and latent-state rows with them, so rejecting a slot would break the resampler; an existing particle is what ordinary
  resampling would have put there, and it can never be a jump across the map. Counted in ``pf.stats``.

``_uniform_free`` is never called (``install`` refuses a recovery config with ``uniform_share != 0``). When no candidate is
invalid the draw is bit-identical to the frozen method: the generator is consumed in the same order (the binomial for the
uniform share, then one normal block), only a candidate beyond ``bound_sigma`` sigma (probability ~2e-9 each) is treated like a
wall hit. No noise scale, trigger rate or threshold was changed.

Sources. Random-particle injection when the short-term likelihood falls below the long-term one: Thrun, Burgard & Fox,
Probabilistic Robotics (2005), Table 8.3 (augmented MCL), as implemented by Nav2/ROS AMCL (``pf_update_resample``). Drawing the
injected poses locally around the estimate with an expansion radius: Ueda, Arai & Sakamoto, IROS 2004 (expansion resetting; emcl2).
Rejection sampling of a proposal against a feasibility mask is the textbook way to restrict a distribution to a region; the
combination used here (local Gaussian, hard box, finite retries, existing particle on exhaustion) is this repository's engineering
choice, not a published algorithm. How emcl2 or Nav2 treat expansion draws that land in an occupied cell was not checked (U).
"""
from __future__ import annotations

import copy
import math

import numpy as np

SCHEMA = 'ugrp.pf_local_redraw.v98.v1'
# max_redraw_rounds is a termination bound, not a noise knob: a slot stays invalid after 16 rounds with probability
# p_invalid**16 (<1.5e-5 even when half of the neighbourhood is wall). bound_sigma=6 cuts a Gaussian mass of ~2e-9.
DEFAULT = {'schema': SCHEMA, 'max_redraw_rounds': 16, 'bound_sigma': 6.0}
CONFIG = DEFAULT
MODULE = 'harness/zone_pair_highpose_pf_local_redraw.py'


def validate(cfg=None):
    cfg = {**DEFAULT, **(cfg or {})}
    if set(cfg) != set(DEFAULT) or cfg['schema'] != SCHEMA:
        raise ValueError('unknown pf_local_redraw keys or schema')
    rounds, bound = cfg['max_redraw_rounds'], cfg['bound_sigma']
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 1000:
        raise ValueError(f'pf_local_redraw.max_redraw_rounds={rounds!r} must be an integer in [1, 1000]')
    if isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound) or not 1. <= bound <= 10.:
        raise ValueError(f'pf_local_redraw.bound_sigma={bound!r} outside [1, 10]')
    return cfg


def record(cfg=None):
    return {'module': MODULE, **validate(cfg),
            'proposal': 'frozen N(belief mean, recovery.local_std); invalid candidates redrawn from the same Gaussian',
            'invalid': 'map prior < 0 (bounds, expanded walls) or beyond bound_sigma * local_std of the belief mean',
            'exhausted': 'one existing weighted valid particle per slot (k rows kept; never a global draw)',
            'uniform_free_calls': 0}


def install(pf, cfg=None):
    """Bind the local re-draw to this PF instance (instance attribute only). A no-op when the recovery (R1) is off."""
    cfg = validate(cfg)
    if getattr(pf, 'local_redraw', None) is not None:
        raise ValueError('pf_local_redraw already installed')
    rec = pf.robust['recovery']
    if rec is None:                                       # no injection is ever drawn, nothing to bind
        pf.local_redraw = None
        return None
    if float(rec.get('uniform_share', 1.)) != 0.:
        raise ValueError('pf_local_redraw requires recovery.uniform_share == 0 (local-only recovery)')
    rounds, bound = int(cfg['max_redraw_rounds']), float(cfg['bound_sigma'])
    state = {'config': copy.deepcopy(cfg), 'last': None}
    pf.local_redraw = state
    pf.stats.update(local_redraw_calls=0, local_redraw_candidates=0, local_redraw_redrawn=0, local_redraw_exhausted=0)

    def random_poses(k):
        k = int(k)
        rec = pf.robust['recovery']
        if int(pf.rng.binomial(k, float(rec.get('uniform_share', 1.)))) != 0:   # same draw as the frozen method (stream parity)
            raise RuntimeError('pf_local_redraw: recovery.uniform_share changed after install')
        w = pf._weights()
        yaw = math.atan2(float(np.sum(w*np.sin(pf.px[:, 2]))), float(np.sum(w*np.cos(pf.px[:, 2]))))
        mean = np.array([float(np.sum(w*pf.px[:, 0])), float(np.sum(w*pf.px[:, 1])), yaw])
        std = np.asarray(rec.get('local_std', [.3, .3, .35]), float)
        loc = mean + pf.rng.normal(size=(k, 3))*std

        def invalid(c):
            return (pf._map_logprior(c) < 0) | np.any(np.abs(c - mean) > bound*std, axis=1)

        bad = invalid(loc)
        candidates = int(bad.sum())
        redraw = bad.copy()
        used = 0
        while bad.any() and used < rounds:
            idx = np.flatnonzero(bad)
            cand = mean + pf.rng.normal(size=(idx.size, 3))*std
            ok = ~invalid(cand)
            loc[idx[ok]] = cand[ok]
            bad[idx[ok]] = False
            used += 1
        kept = bad.copy()
        n_kept = int(kept.sum())
        if n_kept:
            valid = np.where(pf._map_logprior(pf.px) < 0, 0., w)
            p = valid if valid.sum() > 0. else w
            loc[kept] = pf.px[pf.rng.choice(pf.n, size=n_kept, p=p/p.sum())]
        loc[:, 2] = pf.wrap(loc[:, 2])
        state['last'] = {'k': k, 'mean': mean.tolist(), 'std': std.tolist(), 'rounds_used': used,
                         'redrawn': redraw & ~kept, 'kept_existing': kept}
        pf.stats['local_redraw_calls'] += 1
        pf.stats['local_redraw_candidates'] += k
        pf.stats['local_redraw_redrawn'] += candidates - n_kept
        pf.stats['local_redraw_exhausted'] += n_kept
        return loc

    pf._random_poses = random_poses
    return state
