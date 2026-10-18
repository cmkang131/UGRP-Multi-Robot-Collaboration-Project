"""``crossroom_loaded_wallline_v1`` -- occlusion-aware loaded wall following.

Default off.  Design: ``outputs/reports/crossroom-stageB-fix.md`` section 2
(2026-10-18).  The recorded Stage B failure is the own-RGB cargo band
(y400-463 in 16/16 start frames) hiding the near wall foot; the loaded
controller then read three missing side-foot ticks as a doorway and claimed a
gap in 16/16 episodes (0/16 ground-truth crossings).

While the own-RGB carry monitor says *loaded*, this module

* keeps only wall-foot points whose supporting pixel row is **above** the
  cargo band, fits a robust line to those points, and steers to the fitted
  tangent and a fixed lateral stand-off;
* refuses to turn a missing side foot into ``gap_cross``: a gap claim is
  deferred (``gap_deferred_cargo_blind``) and the line is followed on; if the
  fit is lost for more than ``LINE_HOLD_TICKS`` the robot stops
  (``STOPPED_BLIND_CARGO``) instead of driving into unobserved floor;
* accepts a door only with three pieces of **positive** evidence above the
  band: the front cone is empty (<= 10 points, v3 measurement), a far jamb
  exists on the followed side at 0.6-1.3 m, and the along-line hole is
  0.40-0.60 m (the authored 0.50 m door).

Inputs are own-RGB wall points plus their supporting pixel rows (re-projected
with the runner's own camera FK) and the own-RGB band top.  No static map, no
world pose, no top camera, no ground truth.  The logic is pure (numpy only) so
it is unit-tested on synthetic masks/points without a simulator.

Constants are pre-registered from the design note before any gate run; none
was tuned on a gate episode.
"""
from __future__ import annotations

import math

import numpy as np

OPTION = 'crossroom_loaded_wallline_v1'
# The control input is meaningful only for the loaded conditions.  An unloaded
# stage that selects this toggle is rejected by the runner, never ignored.
LOADED_STAGES = ('B_loaded', 'B_loaded_mask_off', 'B_loaded_mask_on')

# Measured on 16/16 Stage B start frames (verifier, ops-alert.md:1329): the
# box occupies rows 400-463.  Row 400 is the first box pixel.
CARGO_BAND_TOP_ROW_DEFAULT = 400
# Antialiasing/top-edge pixels just above the measured row must not enter the
# line fit.
CARGO_BAND_MARGIN_PX = 4

# Robust line fit gates.  Range error of the reused perception is
# 0.06 + 0.08 r (FIX_DESIGN); 0.06 m is used only as an outlier gate.
LINE_MIN_POINTS = 4
LINE_MAX_RESIDUAL_M = 0.06
LINE_MIN_INLIER_RATIO = 0.60
LINE_MAX_RANGE_M = 1.8

# 1 s at 10 Hz: same order as the existing 3-tick gap rule and its 10-tick
# recovery paths.
LINE_HOLD_TICKS = 10

# Follow steering (reuses the base controller's calibrated pulse and deadbands;
# no continuous gains are introduced).
WALL_STANDOFF_M = 0.55
WALL_OFFSET_DEADBAND_M = 0.10
WALL_STANDOFF_FAR_M = 0.65
TANGENT_DEADBAND_DEG = 16.0
FOLLOW_TURN_FORWARD = 0.20
FOLLOW_OFFSET_FORWARD = 0.35
FOLLOW_NEAR_FORWARD = 0.35
FOLLOW_FAR_FORWARD = 0.55

# Door positive evidence (v3 measured constants, FIX_DESIGN v3 addendum).
GAP_FRONT_CONE_DEG = 20.0
GAP_FRONT_CONE_RANGE_M = 1.0
GAP_FRONT_CONE_MAX_POINTS = 10
GAP_JAMB_RANGE_M_V3 = 1.3
# The far jamb is the segment across the opening; the near wall segment is
# closer than this (the authored door is 0.50 m wide).
DOOR_JAMB_RANGE_MIN_M = 0.60
DOOR_JAMB_RANGE_MAX_M = GAP_JAMB_RANGE_M_V3
DOOR_HOLE_MIN_M = 0.40
DOOR_HOLE_MAX_M = 0.60

# The followed-side points used for the fit: the wall's own half-plane.  A
# 0.55 m wall seen 1.5-1.8 m ahead sits at only ~19-20 deg, so the base follow
# sector (-145..-25) would drop exactly the far part that stays above the
# cargo band.  The residual/inlier gate, not the sector, rejects a corner or a
# front wall that does not lie on this line.
SIDE_FIT_BEARING = {'right': (-180.0, -8.0), 'left': (8.0, 180.0)}
# The base ``_follow`` sector that opens the gap trigger; the loaded gate must
# never let a loss inside this sector become a gap claim.
SIDE_FOLLOW_BEARING = {'right': (-145.0, -25.0), 'left': (25.0, 145.0)}
SIDE_FOLLOW_RANGE_M = 1.5


def toggle_on(toggles):
    """True only for the explicit ``on`` string; missing/other means off."""
    return str((toggles or {}).get(OPTION, 'off')) == 'on'


def admit(toggles, stage):
    """Admit the toggle for loaded stages only; reject it elsewhere."""
    on = toggle_on(toggles)
    if on and stage not in LOADED_STAGES:
        raise ValueError('CROSSROOM_LOADED_WALLLINE_LOADED_ONLY')
    return on


def band_top_for_state(state, band_top_row):
    """Own-RGB band top row for the carry state, or ``None`` when disabled.

    ``held``       -> the measured full-frame red-component top row (fallback
                      :data:`CARGO_BAND_TOP_ROW_DEFAULT` when unreadable);
    ``uncertain``  -> the measured Stage B fallback row;
    ``lost``       -> ``None`` (gate disabled; the box is gone).
    """
    if state == 'lost':
        return None
    if state == 'held':
        return (int(band_top_row) if band_top_row is not None
                else CARGO_BAND_TOP_ROW_DEFAULT)
    return CARGO_BAND_TOP_ROW_DEFAULT


def band_top_from_mask(mask):
    """Topmost row of a boolean/uint8 red band mask on the full frame.

    Own RGB only: the mask is produced by the carry monitor's colour gate.
    Returns ``None`` for an empty mask.
    """
    m = np.asarray(mask)
    if m.size == 0:
        return None
    rows = np.flatnonzero(np.asarray(m).reshape(m.shape[0], -1).any(axis=1))
    if not len(rows):
        return None
    return int(rows[0])


def attach_rows(points, rows, front=None):
    """Attach the supporting pixel row to each wall point.

    ``rows`` is the runner's own camera-FK re-projection of every point's
    ground position with the same servo command that produced it (the point
    already came from that projection, so the row is exact).  Points whose
    projection is behind the camera are dropped.
    """
    rows = np.asarray(rows, dtype=float).reshape(-1)
    if len(rows) != len(points):
        raise ValueError('ROW_COUNT_MISMATCH')
    if front is None:
        keep = np.ones(len(points), bool)
    else:
        keep = np.asarray(front, dtype=bool).reshape(-1)
        if len(keep) != len(points):
            raise ValueError('FRONT_COUNT_MISMATCH')
    out = []
    for point, row, ok in zip(points, rows, keep):
        if not ok or not math.isfinite(row):
            continue
        item = dict(point)
        item['row'] = int(round(float(row)))
        out.append(item)
    return out


def above_band(points, band_top, *, margin=CARGO_BAND_MARGIN_PX,
               max_range=LINE_MAX_RANGE_M):
    """Wall points whose supporting row is above the cargo band."""
    if band_top is None:
        return []
    limit = int(band_top) - int(margin)
    out = []
    for p in points:
        row = p.get('row')
        if row is None or not math.isfinite(float(row)):
            continue
        if float(row) > limit:
            continue
        if float(p.get('range_m', float('inf'))) > float(max_range):
            continue
        out.append(p)
    return out


def _bearing_deg(point):
    if point.get('bearing_rad') is None:
        x, y = (float(v) for v in point['relative_xy_m'][:2])
        return math.degrees(math.atan2(y, x))
    return math.degrees(float(point['bearing_rad']))


def _nearest(points, lo_deg, hi_deg, max_range):
    best = None
    for p in points:
        b = _bearing_deg(p)
        if lo_deg <= b <= hi_deg and float(p['range_m']) <= max_range:
            if best is None or float(p['range_m']) < float(best['range_m']):
                best = p
    return best


def side_points(points, wall_side, *, bearing=None,
                max_range=LINE_MAX_RANGE_M):
    """Points of the followed side, within the follow range."""
    lo, hi = bearing or SIDE_FIT_BEARING.get(wall_side, SIDE_FIT_BEARING['right'])
    return [p for p in points
            if lo <= _bearing_deg(p) <= hi
            and float(p.get('range_m', float('inf'))) <= float(max_range)]


def side_foot(points, wall_side, *, max_range=SIDE_FOLLOW_RANGE_M):
    """Nearest foot in the base ``_follow`` sector (the gap-trigger source)."""
    lo, hi = SIDE_FOLLOW_BEARING.get(wall_side, SIDE_FOLLOW_BEARING['right'])
    return _nearest(points, lo, hi, max_range)


def fit_wall_line(points, *, wall_side=None,
                  max_residual=LINE_MAX_RESIDUAL_M,
                  min_inlier_ratio=LINE_MIN_INLIER_RATIO,
                  min_points=LINE_MIN_POINTS):
    """Robust total-least-squares line fit -> tangent bearing and stand-off.

    The line is fitted in the robot frame (x forward, y left).  ``tangent_deg``
    is the bearing of the fitted direction with ``x > 0`` forced (0 = wall
    parallel to the heading); ``offset_m`` is the unsigned perpendicular
    distance from the robot origin to the line.  Iterative residual rejection
    enforces ``max_residual``; a fit that keeps fewer than ``min_points`` or
    explains less than ``min_inlier_ratio`` of the points is rejected.
    """
    n = len(points)
    base = dict(ok=False, reason=None, n=n, inliers=0, inlier_ratio=0.0,
                residual_rms_m=None, tangent_deg=None, offset_m=None,
                signed_offset_m=None, direction=None, point=None)
    if n < int(min_points):
        return {**base, 'reason': 'too_few_points'}
    xy = np.asarray([[float(p['relative_xy_m'][0]),
                      float(p['relative_xy_m'][1])] for p in points], float)
    keep = np.ones(n, bool)
    for _ in range(8):
        if int(keep.sum()) < int(min_points):
            return {**base, 'inliers': int(keep.sum()),
                    'reason': 'too_few_inliers'}
        centre = xy[keep].mean(axis=0)
        _, _, vt = np.linalg.svd(xy[keep] - centre, full_matrices=False)
        direction = vt[0]
        normal = np.array([-direction[1], direction[0]])
        residual = np.abs((xy - centre) @ normal)
        new_keep = residual <= float(max_residual)
        if int(new_keep.sum()) < int(min_points):
            return {**base, 'inliers': int(new_keep.sum()),
                    'reason': 'too_few_inliers'}
        if np.array_equal(new_keep, keep):
            keep = new_keep
            break
        keep = new_keep
    centre = xy[keep].mean(axis=0)
    _, _, vt = np.linalg.svd(xy[keep] - centre, full_matrices=False)
    direction = vt[0]
    if direction[0] < 0:
        direction = -direction
    direction = direction / float(np.linalg.norm(direction))
    normal = np.array([-direction[1], direction[0]])
    residual = np.abs((xy[keep] - centre) @ normal)
    inliers = int(keep.sum())
    ratio = inliers / float(n)
    tangent = math.degrees(math.atan2(float(direction[1]), float(direction[0])))
    signed = float(np.dot(centre, normal))
    out = dict(ok=False, reason=None, n=n, inliers=inliers,
               inlier_ratio=ratio,
               residual_rms_m=float(np.sqrt(np.mean(residual ** 2))),
               tangent_deg=tangent, offset_m=abs(signed),
               signed_offset_m=signed,
               direction=[float(direction[0]), float(direction[1])],
               point=[float(centre[0]), float(centre[1])])
    if ratio < float(min_inlier_ratio):
        return {**out, 'reason': 'low_inlier_ratio'}
    # A right-hand wall lies at negative signed distance along the left normal;
    # a fit with the opposite sign is the other side of the room, not this wall.
    if wall_side == 'right' and signed > 0.05:
        return {**out, 'reason': 'wrong_side'}
    if wall_side == 'left' and signed < -0.05:
        return {**out, 'reason': 'wrong_side'}
    if abs(tangent) > 80.0:
        return {**out, 'reason': 'tangent_perpendicular'}
    return {**out, 'ok': True}


def follow_command(fit, wall_side, *, stale=False):
    """One calibrated action from the fitted line (tangent first, offset next)."""
    tangent = float(fit['tangent_deg'])
    if abs(tangent) > TANGENT_DEADBAND_DEG:
        return dict(forward=FOLLOW_TURN_FORWARD, exact_turn=(1 if tangent > 0 else -1),
                    reason=('hold_tangent' if stale else 'tangent'),
                    tangent_deg=tangent, offset_m=fit['offset_m'])
    err = float(fit['offset_m']) - WALL_STANDOFF_M
    if err < -WALL_OFFSET_DEADBAND_M:
        # too close to the followed wall: one pulse away from it.
        return dict(forward=FOLLOW_OFFSET_FORWARD,
                    exact_turn=(1 if wall_side == 'right' else -1),
                    reason=('hold_offset_close' if stale else 'offset_close'),
                    tangent_deg=tangent, offset_m=fit['offset_m'])
    if err > WALL_OFFSET_DEADBAND_M:
        # too far: one pulse toward it.
        return dict(forward=FOLLOW_OFFSET_FORWARD,
                    exact_turn=(-1 if wall_side == 'right' else 1),
                    reason=('hold_offset_far' if stale else 'offset_far'),
                    tangent_deg=tangent, offset_m=fit['offset_m'])
    far = float(fit['offset_m']) > WALL_STANDOFF_FAR_M
    return dict(forward=(FOLLOW_FAR_FORWARD if far else FOLLOW_NEAR_FORWARD),
                exact_turn=0,
                reason=('hold_follow' if stale else 'follow'),
                tangent_deg=tangent, offset_m=fit['offset_m'])


def door_positive_evidence(points, fit, wall_side, *,
                           front_cone_deg=GAP_FRONT_CONE_DEG,
                           front_cone_range_m=GAP_FRONT_CONE_RANGE_M,
                           front_cone_max=GAP_FRONT_CONE_MAX_POINTS,
                           jamb_range=(DOOR_JAMB_RANGE_MIN_M,
                                       DOOR_JAMB_RANGE_MAX_M),
                           hole_range=(DOOR_HOLE_MIN_M, DOOR_HOLE_MAX_M)):
    """All three positive-evidence pieces for accepting a doorway.

    ``points`` are the above-band wall points; ``fit`` is the followed-wall
    line.  Returns ``ok`` only when the front cone is empty, a far jamb exists
    on the followed side, and the along-line hole between the near segment and
    that jamb is 0.40-0.60 m.
    """
    info = dict(front_cone_points=0, front_ok=False, hole_m=None, hole_ok=False,
                far_jamb_range_m=None, far_jamb_ok=False, reasons=[])
    cone = [p for p in points
            if abs(_bearing_deg(p)) <= float(front_cone_deg)
            and float(p['range_m']) <= float(front_cone_range_m)]
    info['front_cone_points'] = len(cone)
    info['front_ok'] = len(cone) <= int(front_cone_max)
    if not info['front_ok']:
        info['reasons'].append('front_cone_occupied')

    if not fit or not fit.get('ok'):
        info['reasons'].append('no_line_fit')
        return {**info, 'ok': False}
    side = side_points(points, wall_side)
    if len(side) < LINE_MIN_POINTS:
        info['reasons'].append('too_few_side_points')
        return {**info, 'ok': False}
    direction = np.asarray(fit['direction'], float)
    centre = np.asarray(fit['point'], float)
    along = sorted(
        (float(np.dot(np.asarray(p['relative_xy_m'][:2], float) - centre,
                      direction)),
         float(p['range_m']))
        for p in side)
    best = None
    for i in range(len(along) - 1):
        hole = along[i + 1][0] - along[i][0]
        far_range = along[i + 1][1]
        # distance from the robot to the middle of the opening, along the line
        mid = centre + direction * (0.5 * (along[i][0] + along[i + 1][0]))
        mid_range = float(np.linalg.norm(mid))
        if mid_range > LINE_MAX_RANGE_M:
            continue
        if best is None or hole > best[0]:
            best = (hole, far_range)
    if best is None:
        info['reasons'].append('no_hole')
        return {**info, 'ok': False}
    info['hole_m'] = round(float(best[0]), 4)
    info['far_jamb_range_m'] = round(float(best[1]), 4)
    info['hole_ok'] = bool(float(hole_range[0]) <= best[0] <= float(hole_range[1]))
    info['far_jamb_ok'] = bool(float(jamb_range[0]) <= best[1]
                               <= float(jamb_range[1]))
    if not info['hole_ok']:
        info['reasons'].append('hole_out_of_range')
    if not info['far_jamb_ok']:
        info['reasons'].append('far_jamb_out_of_range')
    return {**info, 'ok': bool(info['front_ok'] and info['hole_ok']
                               and info['far_jamb_ok'])}


class LoadedWallLineGate:
    """Stateful loaded-follow gate (band top + rows in, decision out).

    ``decide`` returns one of

    * ``off``       -- toggle off, no band top (cargo lost), or not active;
    * ``follow``    -- fitted line drives a calibrated forward/turn action;
    * ``hold``      -- no fit this tick but the last fit is < 10 ticks old;
    * ``defer``     -- a base gap claim was refused (blind-band guard);
    * ``allow_gap`` -- positive above-band door evidence passed;
    * ``stop``      -- the fit has been lost for > ``hold_ticks``.
    """

    def __init__(self, *, enabled=False, wall_side='right',
                 band_margin=CARGO_BAND_MARGIN_PX,
                 hold_ticks=LINE_HOLD_TICKS,
                 fit_kwargs=None):
        self.enabled = bool(enabled)
        self.wall_side = wall_side
        self.band_margin = int(band_margin)
        self.hold_ticks = int(hold_ticks)
        self.fit_kwargs = dict(fit_kwargs or {})
        self.last_fit = None
        self.hold = 0
        self.blind_latched = False
        self.last_observation = None
        self.last_decision = None
        self.counters = dict(ticks=0, active_ticks=0, line_fits=0, line_lost=0,
                             gap_deferred_cargo_blind=0,
                             gap_confirmed_above_band=0,
                             blind_cargo_stops=0, hold_ticks=0)

    def set_side(self, wall_side):
        self.wall_side = wall_side

    def observe(self, walls, band_top):
        above = above_band(walls, band_top, margin=self.band_margin)
        side = side_points(above, self.wall_side)
        fit = fit_wall_line(side, wall_side=self.wall_side, **self.fit_kwargs)
        if fit['ok']:
            self.last_fit = fit
            self.hold = 0
            self.blind_latched = False
            self.counters['line_fits'] += 1
        else:
            self.hold += 1
            if self.hold == 1:
                self.counters['line_lost'] += 1
        obs = dict(above=above, side=side, fit=fit, hold=self.hold,
                   blind=bool(not fit['ok'] and self.hold > self.hold_ticks),
                   band_top=None if band_top is None else int(band_top))
        self.last_observation = obs
        return obs

    def follow_command(self, obs):
        if obs['fit']['ok']:
            return follow_command(obs['fit'], self.wall_side)
        if self.last_fit is not None and self.hold <= self.hold_ticks:
            self.counters['hold_ticks'] += 1
            return follow_command(self.last_fit, self.wall_side, stale=True)
        return None

    def decide(self, walls, band_top, *, gap_claimed):
        if not self.enabled or band_top is None:
            self.last_decision = dict(mode='off')
            return self.last_decision
        self.counters['ticks'] += 1
        self.counters['active_ticks'] += 1
        obs = self.observe(walls, band_top)
        if gap_claimed:
            evidence = door_positive_evidence(obs['above'], obs['fit'],
                                              self.wall_side)
            if evidence['ok']:
                self.counters['gap_confirmed_above_band'] += 1
                self.last_decision = dict(mode='allow_gap', evidence=evidence,
                                          observation=obs)
                return self.last_decision
            self.counters['gap_deferred_cargo_blind'] += 1
            self.last_decision = dict(mode='defer', evidence=evidence,
                                      command=self.follow_command(obs),
                                      observation=obs)
            return self.last_decision
        command = self.follow_command(obs)
        if command is not None:
            mode = 'follow' if obs['fit']['ok'] else 'hold'
            self.last_decision = dict(mode=mode, command=command,
                                      observation=obs)
            return self.last_decision
        if obs['blind']:
            if not self.blind_latched:
                self.blind_latched = True
                self.counters['blind_cargo_stops'] += 1
            self.last_decision = dict(mode='stop', observation=obs)
            return self.last_decision
        self.last_decision = dict(mode='hold', command=None, observation=obs)
        return self.last_decision

    def summary(self):
        obs = self.last_observation or {}
        fit = obs.get('fit') or {}
        return dict(option=OPTION, enabled=self.enabled,
                    wall_side=self.wall_side, band_top=obs.get('band_top'),
                    above_band_points=len(obs.get('above') or []),
                    side_points=len(obs.get('side') or []),
                    fit_ok=bool(fit.get('ok')),
                    fit_inliers=fit.get('inliers'),
                    fit_inlier_ratio=(round(float(fit['inlier_ratio']), 4)
                                      if fit.get('inlier_ratio') is not None
                                      else None),
                    fit_residual_rms_m=(round(float(fit['residual_rms_m']), 4)
                                        if fit.get('residual_rms_m') is not None
                                        else None),
                    tangent_deg=(round(float(fit['tangent_deg']), 2)
                                 if fit.get('tangent_deg') is not None else None),
                    offset_m=(round(float(fit['offset_m']), 4)
                              if fit.get('offset_m') is not None else None),
                    **self.counters)
