"""VIS6 evaluation metrics and pre-registered selection rules (pure functions; no file access).

Per frame: full-covariance XY NEES e^T P^-1 e (chi^2 with 2 dof for a consistent
filter; Bar-Shalom, Li & Kirubarajan 2001), yaw NEES, Gaussian NLL, 95 % ellipse
coverage (NEES <= chi2_2(0.95) = 5.991), > 3 sigma share (NEES > chi2_2(0.9973)).
Frames are time-correlated: the averages are descriptive (ANEES), not chi^2 tests.

Accuracy metrics follow ``vision_loc_score`` (door zone of PR #210, lateral =
|y_est - y_gt|): door position p90, door lateral p99, door yaw p90.
Over-confident loss events: runs of consecutive frames with position error
> max(3 * std_xy, 0.20 m), merge gaps <= 1 s within contiguous data, require >= 5 bad frames (literature
review 3.7 / 6.4). 1c detector diagnostic: see ``stall_diagnostic``.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

import numpy as np

CHI2_2_95 = 5.991464547107979
CHI2_2_3SIG = 11.829158081900795          # P(chi2_2 <= x) = 0.9973 (the 1D 3-sigma mass)
Z95 = 1.959963984540054
XY_VAR_FLOOR = 1e-8                       # m^2 added to the XY covariance diagonal (rounded logs)
YAW_VAR_FLOOR = 1e-10
EVENT_MIN_M = .20
LOST_M = .30


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def frame_terms(est_xyyaw: Sequence[float], cov: Sequence[Sequence[float]], gt_xyyaw: Sequence[float]) -> dict:
    """NEES / NLL / errors of one estimate (``cov``: 3x3 over x, y, yaw)."""
    c = np.asarray(cov, float)
    if c.shape != (3, 3) or not np.all(np.isfinite(c)):
        raise ValueError('cov must be a finite 3x3 matrix')
    e = np.array([est_xyyaw[0] - gt_xyyaw[0], est_xyyaw[1] - gt_xyyaw[1]], float)
    p = .5*(c[:2, :2] + c[:2, :2].T) + XY_VAR_FLOOR*np.eye(2)
    det = float(np.linalg.det(p))
    if np.linalg.eigvalsh(p).min() <= 0:
        raise ValueError('XY covariance is not positive definite')
    nees = float(e @ np.linalg.solve(p, e))
    ey = wrap(float(est_xyyaw[2]) - float(gt_xyyaw[2]))
    vy = max(float(c[2, 2]), 0.) + YAW_VAR_FLOOR
    # Wrapped normal density; yaw NEES remains a local/tangent diagnostic.
    if vy >= 36.:
        nll_yaw = math.log(2*math.pi)
    else:
        turns = int(math.ceil(6*math.sqrt(vy)/(2*math.pi))) + 1
        terms = [-.5*(ey + 2*math.pi*k)**2/vy for k in range(-turns, turns + 1)]
        nll_yaw = .5*math.log(2*math.pi*vy) - float(np.logaddexp.reduce(terms))
    return {'err_m': float(np.hypot(*e)), 'lat_m': abs(float(e[1])), 'yaw_err_deg': abs(math.degrees(ey)),
            'nees_xy': nees, 'nll_xy': .5*nees + .5*math.log((2*math.pi)**2*det),
            'nees_yaw': ey*ey/vy, 'nll_yaw': nll_yaw,
            'std_xy_m': float(math.sqrt(max(c[0, 0] + c[1, 1], 0.)))}


def _pct(a, q):
    a = np.asarray(a, float)
    return None if a.size == 0 else float(np.percentile(a, q))


def events(rows: Sequence[Mapping], min_frames: int = 5, merge_gap_s: float = 1.) -> dict:
    """All bad frames are counted; descriptive events merge brief recoveries within observed data."""
    lengths, n_fr, cur = [], 0, 0
    previous = last_bad = None
    for r in rows:
        contiguous = (previous is None or
                      (r['frame'] == previous['frame'] + 1 and 0 <= r['t'] - previous['t'] <= 1. + 1e-9))
        if not contiguous or (last_bad is not None and r['t'] - last_bad > merge_gap_s + 1e-9):
            if cur:
                lengths.append(cur)
            cur, last_bad = 0, None
        if r['err_m'] > max(3.*r['std_xy_m'], EVENT_MIN_M):
            cur += 1
            n_fr += 1
            last_bad = r['t']
        previous = r
    if cur:
        lengths.append(cur)
    qualifying = [n for n in lengths if n >= min_frames]
    return {'events': len(qualifying), 'frames': n_fr, 'longest_frames': max(qualifying, default=0)}


def summarize(episodes: Mapping[str, Sequence[Mapping]]) -> dict:
    """Metrics of one (candidate, seed) over the given episodes.

    ``episodes``: episode id -> time-ordered frame rows, each ``frame_terms`` output plus
    'frame', 't', 'groups' (``vision_loc_score.groups_of``).
    """
    allr = [r for rows in episodes.values() for r in rows]
    if not allr:
        raise ValueError('no frames')
    col = lambda rows, k: np.asarray([r[k] for r in rows], float)
    nees = col(allr, 'nees_xy')
    zy = np.sqrt(col(allr, 'nees_yaw'))
    door = [r for r in allr if 'door_zone' in r['groups']]
    loaded = [r for r in allr if 'loaded' in r['groups']]
    unloaded = [r for r in allr if 'loaded' not in r['groups']]
    ev = {ep: events(rows) for ep, rows in episodes.items()}
    nll_ep = {ep: float(np.mean(col(rows, 'nll_xy'))) for ep, rows in episodes.items() if rows}
    nll_yaw_ep = {ep: float(np.mean(col(rows, 'nll_yaw'))) for ep, rows in episodes.items() if rows}
    return {
        'n_frames': len(allr), 'n_episodes': len(episodes), 'n_door': len(door), 'n_loaded': len(loaded),
        'coverage95_xy': float(np.mean(nees <= CHI2_2_95)), 'exceed3_xy': float(np.mean(nees > CHI2_2_3SIG)),
        'anees_xy': float(np.mean(nees)), 'nees_xy_p50': _pct(nees, 50),
        'coverage95_yaw': float(np.mean(zy <= Z95)), 'exceed3_yaw': float(np.mean(zy > 3.)),
        'anees_yaw': float(np.mean(zy**2)),
        'nll_xy': float(np.mean(list(nll_ep.values()))), 'nll_yaw': float(np.mean(list(nll_yaw_ep.values()))),
        'nll_xy_by_episode': nll_ep,
        'pos_p90_m': _pct(col(allr, 'err_m'), 90), 'lost_frames': int(np.sum(col(allr, 'err_m') > LOST_M)),
        'door_pos_p90_m': _pct(col(door, 'err_m'), 90), 'door_lat_p99_m': _pct(col(door, 'lat_m'), 99),
        'door_yaw_p90_deg': _pct(col(door, 'yaw_err_deg'), 90),
        'sigma_xy_p90_m': _pct(col(allr, 'std_xy_m'), 90),
        'sigma_xy_p90_loaded_m': _pct(col(loaded, 'std_xy_m'), 90),
        'sigma_xy_p90_unloaded_m': _pct(col(unloaded, 'std_xy_m'), 90),
        'events': int(sum(e['events'] for e in ev.values())), 'event_frames': int(sum(e['frames'] for e in ev.values())),
        'events_by_episode': ev,
    }


SCALAR_KEYS = ('coverage95_xy', 'exceed3_xy', 'anees_xy', 'coverage95_yaw', 'exceed3_yaw', 'anees_yaw', 'nll_xy',
               'nll_yaw', 'pos_p90_m', 'lost_frames', 'door_pos_p90_m', 'door_lat_p99_m', 'door_yaw_p90_deg',
               'sigma_xy_p90_m', 'sigma_xy_p90_loaded_m', 'sigma_xy_p90_unloaded_m', 'events', 'event_frames')


def seed_mean(per_seed: Mapping[str, Mapping]) -> dict:
    """Mean and sample sd over PF seeds of every scalar metric, plus the per-episode NLL means."""
    if not per_seed:
        raise ValueError('no seeds')
    out: dict = {'seeds': sorted(per_seed), 'mean': {}, 'sd': {}}
    for k in SCALAR_KEYS:
        v = [s[k] for s in per_seed.values() if s.get(k) is not None]
        out['mean'][k] = None if not v else float(np.mean(v))
        out['sd'][k] = None if len(v) < 2 else float(np.std(v, ddof=1))
    eps = sorted({ep for s in per_seed.values() for ep in s['nll_xy_by_episode']})
    out['mean']['nll_xy_by_episode'] = {ep: float(np.mean([s['nll_xy_by_episode'][ep] for s in per_seed.values()]))
                                        for ep in eps}
    return out


def select_calibrated(stats: Mapping[str, Mapping], prefer: Sequence[str], band=(.90, .99)) -> dict:
    """Pre-registered calibration choice among ``prefer`` (fit split, seed means).

    Eligible: XY 95 % ellipse coverage within ``band``. Chosen: the lowest
    episode-equal XY NLL; ties (1e-9) go to the earlier name in ``prefer``.
    Accuracy is not a selection criterion. None eligible: ``chosen`` None.
    """
    missing = [n for n in prefer if n not in stats]
    if missing:
        raise ValueError(f'missing candidates {missing}')
    lo, hi = band
    elig = [n for n in prefer if stats[n]['coverage95_xy'] is not None and lo <= stats[n]['coverage95_xy'] <= hi]
    chosen = min(elig, key=lambda n: (round(stats[n]['nll_xy'], 9), prefer.index(n))) if elig else None
    return {'chosen': chosen, 'eligible': elig, 'band': [lo, hi],
            'table': {n: {'coverage95_xy': stats[n]['coverage95_xy'], 'nll_xy': stats[n]['nll_xy']} for n in prefer}}


DEFAULT_VALIDATION_RULE = {
    'coverage95_band': [.90, .99],
    'exceed3_xy_max': .02,
    'door_pos_p90_worse_max_m': .003,
    'door_lat_p99_worse_max_m': .003,
    'door_yaw_p90_worse_max_deg': .2,
    'sigma_xy_p90_loaded_max_m': .07,
    'episode_nll_no_worse': True,
    'event_frames_reduction_min': .30,
    'sigma_xy_p90_unloaded_max_m': .07,
}


def validation_gate(cand: Mapping, base: Mapping, rule: Mapping | None = None) -> dict:
    """Validation-split acceptance of ``cand`` against ``base`` (seed-mean dicts of ``seed_mean()['mean']``)."""
    r = {**DEFAULT_VALIDATION_RULE, **(rule or {})}
    fails = []
    lo, hi = r['coverage95_band']
    if not lo <= cand['coverage95_xy'] <= hi:
        fails.append(f"coverage95_xy {cand['coverage95_xy']:.4f} outside [{lo}, {hi}]")
    if cand['exceed3_xy'] > r['exceed3_xy_max']:
        fails.append(f"exceed3_xy {cand['exceed3_xy']:.4f} > {r['exceed3_xy_max']}")
    for key, lim in (('door_pos_p90_m', 'door_pos_p90_worse_max_m'), ('door_lat_p99_m', 'door_lat_p99_worse_max_m'),
                     ('door_yaw_p90_deg', 'door_yaw_p90_worse_max_deg')):
        if cand[key] is None or base[key] is None:
            fails.append(f'{key} missing')
        elif cand[key] - base[key] > r[lim] + 1e-12:
            fails.append(f'{key} worse by {cand[key] - base[key]:.4f} > {r[lim]}')
    for state in ('loaded', 'unloaded'):
        key, limit = f'sigma_xy_p90_{state}_m', r[f'sigma_xy_p90_{state}_max_m']
        value = cand.get(key)
        if value is None or value > limit:
            fails.append(f'{key} {value} missing or > {limit}')
    if r['episode_nll_no_worse']:
        for ep, v in base['nll_xy_by_episode'].items():
            c = cand['nll_xy_by_episode'].get(ep)
            if c is None or c > v + 1e-12:
                fails.append(f'nll_xy worse on {ep}')
    maximum = base['event_frames']*(1. - r['event_frames_reduction_min'])
    if cand['event_frames'] > maximum + 1e-12:
        fails.append(f"event_frames {cand['event_frames']} > allowed {maximum}")
    return {'pass': not fails, 'failures': fails, 'rule': r}


def select_gating(stats: Mapping[str, Mapping], prefer: Sequence[str], baseline: Mapping,
                  limits: Mapping) -> dict:
    """S3: constrain door accuracy before minimizing fit NLL (fixed order breaks ties)."""
    eligible = []
    keys = ('door_pos_p90_m', 'door_lat_p99_m', 'door_yaw_p90_deg')
    for name in prefer:
        if all(stats[name].get(k) is not None and baseline.get(k) is not None
               and stats[name][k] - baseline[k] <= limits[k] + 1e-12 for k in keys):
            eligible.append(name)
    return {'chosen': min(eligible, key=lambda n: (round(stats[n]['nll_xy'], 9), prefer.index(n)))
            if eligible else None, 'eligible': eligible, 'table': dict(stats)}


def stall_diagnostic(pairs: Iterable[Mapping], still_mps: float = .01, cmd_mps: float = .05,
                     correct_ratio: float = .5, still_rps: float = .02, cmd_rps: float = .05) -> dict:
    """1c detector alone against GT motion (eval only).

    ``pairs``: dicts with 'decision', 'dt', 'pred_m' (command-integrated), 'gt_m' (true
    base displacement over the same frame pair), plus pred_yaw_rad/gt_yaw_rad.
    Positive: both GT speeds below still thresholds, at least one predicted speed
    above its command threshold. Precision requires both true displacements below
    max(correct_ratio * predicted, still_threshold * dt). Unknown counts as a miss.
    The caller supplies unique seed0 pairs, never repeated PF-seed observations.
    """
    n = pos = tp_pos = stall = stall_ok = moving = unknown = unknown_pos = 0
    for p in pairs:
        n += 1
        dt = max(float(p['dt']), 1e-9)
        pred_yaw, gt_yaw = abs(p.get('pred_yaw_rad', 0.)), abs(p.get('gt_yaw_rad', 0.))
        translating, turning = p['pred_m']/dt > cmd_mps, pred_yaw/dt > cmd_rps
        is_pos = (p['gt_m']/dt < still_mps and gt_yaw/dt < still_rps and (translating or turning))
        pos += is_pos
        d = p['decision']
        if d == 'stall':
            stall += 1
            stall_ok += ((translating or turning)
                         and p['gt_m'] <= max(correct_ratio*p['pred_m'], still_mps*dt)
                         and gt_yaw <= max(correct_ratio*pred_yaw, still_rps*dt))
            tp_pos += is_pos
        elif d == 'moving':
            moving += 1
        else:
            unknown += 1
            unknown_pos += is_pos
    return {'pairs': n, 'positives': pos, 'stall_decisions': stall, 'moving_decisions': moving, 'unknown': unknown,
            'precision': None if stall == 0 else stall_ok/stall, 'recall': None if pos == 0 else tp_pos/pos,
            'abstain_share_of_positives': None if pos == 0 else unknown_pos/pos,
            'definition': {'still_mps': still_mps, 'cmd_mps': cmd_mps, 'correct_ratio': correct_ratio,
                           'still_rps': still_rps, 'cmd_rps': cmd_rps}}
