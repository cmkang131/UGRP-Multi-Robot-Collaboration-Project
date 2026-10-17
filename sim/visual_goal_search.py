"""Default-off own-RGB destination search: look around, explore, remember, arrive.

The skill receives only own camera pixels, issued arm/wheel commands and its own
egocentric memory.  It is never given a static map, world pose, visibility label
or zone coordinates.  Reused code (byte copies, provenance in
``experiments/2026-10-17-visgoal/vendor/provenance.json``):

* ``floor_patch`` / nominal camera rays: reloc19 ``destination_visual_acquire``
  and ``grasp_act_solo_lookback`` (PR #541).
* calibrated v5 wall/floor colour masks: scene-tex2 ``scene_colour_boundary``
  (PR #527) with the frozen indigo110_s80 calibration.
* robocentric point memory: egomem1 ``LandmarkMemory`` (legacy_v1, Castellanos
  old-frame update), PR #574.

Public navigation ideas, used as-is at the level of relative primitives:
Nav2 1.4.2 Spin (signed relative yaw accumulation) and DriveOnHeading
(relative-distance travel); Bug2 wall following for the divider door.  A
static occupancy grid/frontier method is deliberately not used because
``static_map_use=none``.  The zone interior is not known: the remembered point
is the median of visible paint pixels, which is inside the painted region.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from harness.zone_own_perception import PAINT_HUE, SLOT_MAX_RANGE_M, _usable_region

OPTION = 'visual_goal_search_v1'
CHI2_95 = 5.991464547107979
TURN_STEP_RAD = 0.022921          # own-command calibration r2, one exact pulse
TURN_PULSE_WHEELS = (-.35, .35, -.35, .35)
TURN_PULSE_S = 0.027857142857142865
PATCH_FIT_RANGE_M = SLOT_MAX_RANGE_M
FAR_RANGE_M = 4.0
# A far colour hint must be zone-sized, not just zone-hued.  Preflight r7
# west e00 targeted the 25x7 px blue end cap of a green beam (128-150 px,
# bbox bottom near the horizon) for 10 s before losing it.  Zone B at 1.05 m
# measured 28856 px and its 0.84 m^2 footprint is still >1000 px at the
# arena's 5-6 m sight lines.  Require the same 600 px as the metric fit.
MIN_COLOUR_PIXELS = 600
MIN_METRIC_PIXELS = 600
# Calibrated on rendered v5 frames from the assigned VM (2026-10-17): the
# blue-tinted floor lies in the hue band (hue 108) but its band saturation is
# p99 73-77 (west frames) and max 99 (east-away frame e10).  Zone-B paint
# measured S median 128; S>=110 retains 29859 px (vs 31491 at S>=30) and
# leaves 0 px on the no-zone frames.  Appearance gate, not zone position.
PAINT_SATURATION_MIN = 110
SIGMA_RANGE_M = .20               # inherited PR406 range assumption
SIGMA_BEARING_RAD = math.radians(3.)
# No authored zone size is available with static_map_use=none.  This generic
# bound only disables floor_patch's authored-extent test; the sensor range stays.
GENERIC_HALF_EXTENTS = (1.5, 1.5)


def _wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def signed_turn_wheels(direction, calibrated):
    """Apply the r2 positive-yaw pulse in the requested signed direction."""
    sign = 1. if float(direction) > 0 else -1.
    return [sign * float(w) for w in calibrated]


def _point_covariance(xy):
    """PR406 .2 m / 3 deg -> Cartesian 2x2, same propagation as egomem_vision."""
    xy = np.asarray(xy, float)
    r = float(np.linalg.norm(xy))
    a = math.atan2(xy[1], xy[0])
    c, s = math.cos(a), math.sin(a)
    j = np.array([[c, -r * s], [s, r * c]])
    return j @ np.diag([SIGMA_RANGE_M ** 2, SIGMA_BEARING_RAD ** 2]) @ j.T


def paint_components(bgr, band, *, min_pixels=MIN_COLOUR_PIXELS,
                     saturation_min=PAINT_SATURATION_MIN):
    """Largest destination-colour component from own raw fisheye RGB.

    Hue/V/region/connectivity limits are those of ``floor_patch``; saturation
    is raised from its S>=30 floor to the calibrated v5 paint gate.  The v5
    floor itself has hue 108 (inside the paint band) but only S<=99, so S>=30
    would call the whole floor a destination.  The 120 px far gate is below
    floor_patch's 600 px metric gate and is used only as a bearing/approach
    hint; it is never the remembered metric landmark by itself.
    """
    if bgr is None or bgr.shape != (480, 640, 3) or bgr.dtype != np.uint8:
        return dict(pixels=0, reason='own_rgb_missing', components=0)
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lo, hi = band
    mask = ((hsv[..., 0] >= lo - 5) & (hsv[..., 0] <= hi + 5)
            & (hsv[..., 1] >= int(saturation_min)) & (hsv[..., 2] >= 30)
            & _usable_region(w, h))
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return dict(pixels=0, reason='destination_colour_absent', components=0)
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    pixels = int(stats[i, cv2.CC_STAT_AREA])
    if pixels < int(min_pixels):
        return dict(pixels=pixels, reason='destination_component_small', components=int(n - 1))
    return dict(pixels=pixels, reason='destination_colour_observed',
                components=int(n - 1), label=i, labels=labels, mask=mask,
                bbox=[int(v) for v in stats[i, :4]], centroid=[float(v) for v in cents[i]])


def component_clear(paint, *, dilate_px=2):
    """Boolean mask of the accepted high-saturation paint component.

    Passed as ``floor_patch(..., clear=...)`` so the vendored fitted-segment
    helper cannot select the blue-tinted floor (its own S>=30 gate) instead of
    the paint.  Dilation restores the 3x3-opening edge before the fit.
    """
    labels = paint.get('labels') if paint else None
    label = paint.get('label') if paint else None
    if labels is None or label is None:
        return None
    mask = (np.asarray(labels) == int(label)).astype(np.uint8)
    if int(dilate_px) > 0:
        k = 2 * int(dilate_px) + 1
        mask = cv2.dilate(mask, np.ones((k, k), np.uint8))
    return mask.astype(bool)


def _ground_points(label_mask, pwm, *, max_range=FAR_RANGE_M):
    """Median floor-plane point of a raw-fisheye component (nominal camera FK)."""
    from sim.grasp_act_solo_lookback import transforms, _pixel_rays
    h, w = label_mask.shape
    _, cam = transforms(pwm)
    rays = _pixel_rays(w, h).reshape(h, w, 3)
    vs, us = np.nonzero(label_mask)
    if not len(vs):
        return None
    # Bounded sample keeps this at 10 Hz; every 3rd pixel is ample for a median.
    if len(vs) > 4000:
        keep = np.linspace(0, len(vs) - 1, 4000).astype(int)
        vs, us = vs[keep], us[keep]
    rr = rays[vs, us] @ cam[:3, :3].T
    valid = rr[:, 2] < -1e-4
    if not valid.any():
        return None
    scale = -cam[2, 3] / rr[valid, 2]
    xy = cam[:3, 3][:2] + scale[:, None] * rr[valid, :2]
    dist = np.linalg.norm(xy, axis=1)
    ok = (scale > 0) & (dist <= max_range)
    if not ok.any():
        return None
    xy = xy[ok]
    return dict(relative_xy_m=np.median(xy, axis=0).tolist(),
                nearest_range_m=float(np.percentile(np.linalg.norm(xy, axis=1), 2)),
                median_range_m=float(np.median(np.linalg.norm(xy, axis=1))),
                ground_pixels=int(ok.sum()), source='own_rgb_nominal_ground_projection')


def detect_paint(bgr, pwm, band, *, saturation_min=PAINT_SATURATION_MIN):
    """Far colour hint + lower-centre on-paint evidence, never a zone identity."""
    comp = paint_components(bgr, band, saturation_min=saturation_min)
    if comp.get('pixels', 0) < MIN_COLOUR_PIXELS:
        return comp
    label = comp['label']
    geom = _ground_points(comp['labels'] == label, pwm)
    mask = comp['mask']
    lower = mask[330:470, 160:480]
    comp.update(lower_centre_pixels=int(lower.sum()), lower_centre_share=float(lower.mean()),
                hat=(geom or {}))
    if geom:
        xy = np.asarray(geom['relative_xy_m'])
        comp.update(relative_xy_m=xy.tolist(), range_m=float(np.linalg.norm(xy)),
                    bearing_rad=float(math.atan2(xy[1], xy[0])),
                    nearest_range_m=geom['nearest_range_m'],
                    range_class='metric' if geom['nearest_range_m'] <= PATCH_FIT_RANGE_M else 'far_coarse')
    else:
        # Bearing remains observable even when the ray never reaches the floor
        # inside the supported range; it is a hint, not a landmark.
        h, w = mask.shape
        v, u = np.nonzero(mask)
        if len(u):
            from sim.grasp_act_solo_lookback import transforms, _pixel_rays
            _, cam = transforms(pwm)
            ray = _pixel_rays(w, h)[int(np.median(v)) * w + int(np.median(u))]
            rc = cam[:3, :3] @ ray
            comp.update(bearing_rad=float(math.atan2(rc[1], rc[0])),
                        range_m=None, range_class='bearing_only')
    return comp


def wall_points(bgr, pwm, calibration, *, max_range=3.2):
    """Calibrated v5 wall foot per column -> robot-frame points (nominal FK)."""
    # The runner registers the byte-vendored module as harness.scene_colour_boundary.
    from harness.scene_colour_boundary import surface_masks
    from sim.grasp_act_solo_lookback import transforms, _pixel_rays
    h, w = bgr.shape[:2]
    masks, _ = surface_masks(bgr, calibration)
    wall = masks['wall'] & _usable_region(w, h)
    has = wall.any(axis=0)
    if not has.any():
        return []
    vs = h - 1 - np.argmax(wall[::-1], axis=0)
    us = np.where(has & (vs < h - 18))[0]
    if not len(us):
        return []
    v0 = np.maximum(vs[us] - 2, 0); v1 = np.maximum(vs[us] - 1, 0); v2 = vs[us]
    # Require vertical wall support immediately above the bottom-most pixel.
    keep = wall[v0, us] & wall[v1, us] & wall[v2, us]
    us, vs = us[keep], vs[us][keep]
    if not len(us):
        return []
    _, cam = transforms(pwm)
    rays = _pixel_rays(w, h)[vs * w + us] @ cam[:3, :3].T
    valid = rays[:, 2] < -1e-4
    if not valid.any():
        return []
    scale = -cam[2, 3] / rays[valid, 2]
    xy = cam[:3, 3][:2] + scale[:, None] * rays[valid, :2]
    rng = np.linalg.norm(xy, axis=1)
    ok = (scale > 0) & (rng <= max_range)
    xy, rng = xy[ok], rng[ok]
    return [dict(relative_xy_m=p.tolist(), range_m=float(r),
                 bearing_rad=float(math.atan2(p[1], p[0])))
            for p, r in zip(xy, rng)]


@dataclass
class Options:
    hue_band: tuple = PAINT_HUE['B']
    signature: str = 'paint_hue_B'
    paint_saturation_min: int = PAINT_SATURATION_MIN
    exact_turn_rad: float = TURN_STEP_RAD
    max_stage_s: float = 240.
    wall_clear_m: float = .55
    wall_follow_m: float = .55
    front_block_m: float = .45
    obstacle_block_m: float = .42
    gap_missing_ticks: int = 3


class VisualGoalSearch:
    """Relative-command search controller; default off."""

    def __init__(self, *, option='off', options=None):
        if option not in ('off', OPTION):
            raise ValueError('UNKNOWN_VISUAL_GOAL_SEARCH')
        self.enabled = option == OPTION
        self.options = options or Options()
        self.stage = 'off' if not self.enabled else 'orient'
        self.turn_left = 0                 # exact calibrated pulses still due
        self.wall_side = 'right'
        self.gap_phase = 0
        self.gap_ticks = 0
        self.gap_turn = 'right'
        self.missing = 0
        self.seek_t = 0.
        self.leg = 0
        self.found = False
        self.arrived = False
        self.obs = None
        self.events = []
        self.stage_t = None
        self.colour_seen = False
        self.leg = 0
        self.leg_ticks = 0
        self.leg_len = 20
        self._next_stage = None
        self._turn_sign = 1
        self._spin_pulses = 0
        self.patch = None
        self.patch_record = None
        self.last_paint_t = None
        self.last_patch_t = None
        self.follow_t = 0.
        self.reacquire_pulses = None

    # ---- event ledger -------------------------------------------------
    def event(self, t, reason, *, category='navigation', blocked_object='not_observed',
              minimum_gap_m=None, gap_status='not_measured', **extra):
        e = dict(t=float(t), stage=self.stage, category=category, reason=reason,
                 blocked_object=blocked_object, minimum_gap_m=minimum_gap_m,
                 gap_status=gap_status, **extra)
        self.events.append(e)
        return e

    # ---- observation side --------------------------------------------
    def memory_observation(self, t, patch, patch_record):
        """Metric landmark only when the reused <=1.2 m floor fit succeeds."""
        if not self.enabled or patch is None:
            return None
        if self.patch is None or np.linalg.norm(np.asarray(patch) - np.asarray(self.patch)) > .02:
            self.event(t, 'metric_patch_acquired', category='perception',
                       patch_xy=np.asarray(patch).tolist(), pixels=int(patch_record.get('pixels', 0)),
                       blocked_object='not_observed')
        self.patch = np.asarray(patch, float)
        self.patch_record = dict(patch_record)
        self.last_patch_t = t
        self.found = True
        return dict(id='destination-paint-B', kind='destination_zone',
                    signature=self.options.signature,
                    relative_xy_m=np.asarray(patch).tolist(),
                    measurement_state=np.asarray(patch).tolist(),
                    covariance_m2=_point_covariance(patch).tolist(),
                    hue=float((self.options.hue_band[0] + self.options.hue_band[1]) / 2),
                    pixels=int(patch_record.get('pixels', 0)))

    # ---- control side -------------------------------------------------
    @staticmethod
    def _nearest(points, lo_deg, hi_deg, max_range):
        best = None
        for p in points:
            b = math.degrees(p['bearing_rad'])
            if lo_deg <= b <= hi_deg and p['range_m'] <= max_range:
                if best is None or p['range_m'] < best['range_m']:
                    best = p
        return best

    def _turn_pulses(self, rad):
        return int(round(abs(rad) / self.options.exact_turn_rad))

    def _set_stage(self, t, stage, **extra):
        reason = extra.pop('reason', None)
        if self.stage != stage:
            self.event(t, 'stage_' + stage, category='navigation', stage_reason=reason, **extra)
        self.stage = stage
        self.stage_t = t

    def _start_turn(self, pulses, sign, next_stage):
        self.turn_left = int(abs(pulses))
        self._turn_sign = 1 if sign >= 0 else -1
        self._next_stage = next_stage

    def _turn_tick(self, t, paint, walls, obstacles):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_while_turning')
            return None
        if self.turn_left > 0:
            self.turn_left -= 1
            return self._result(0., 0., 0., exact_turn=self._turn_sign)
        nxt = getattr(self, '_next_stage', None)
        self._next_stage = None
        if nxt is None:
            return None
        self._set_stage(t, nxt)
        return None

    def control(self, t, *, paint=None, walls=(), obstacles=(), memories=(), patch_ok=False,
                patch_xy=None):
        if not self.enabled:
            return dict(status='off', stage='off', forward=0., left=0., turn=0.,
                        exact_turn=0, stop=True, events=[], found=False, arrived=False,
                        colour_seen=False)
        paint = paint or {}
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self.last_paint_t = t
            if not self.colour_seen:
                self.colour_seen = True
                self.event(t, 'destination_colour_seen', category='perception',
                           pixels=int(paint.get('pixels', 0)), blocked_object='not_observed')
        # Prefer the freshest memory.  A large wrong-sign spin in preflight r2
        # broke association: a 0.9 m first patch and a later 1.15 m patch became
        # two landmarks, and min(range) then selected the stale 0.33 m ghost and
        # declared arrival outside zone B.  Age is the only ownership-neutral
        # discriminator available to the skill.
        target_mem = (min(memories, key=lambda m: (float(m.get('age_s', 99.)),
                                                   float(m['range_m'])))
                      if memories else None)
        if self.arrived:
            return self._result(0., 0., 0., True)
        if self.turn_left > 0 or getattr(self, '_next_stage', None) is not None:
            r = self._turn_tick(t, paint, walls, obstacles)
            if r is not None:
                return r
        # Stage-table dispatch: one tick at a time, no recursion.
        handler = {
            'orient': self._orient,
            'seek_wall': self._seek_wall,
            'approach_wall': self._approach_wall,
            'follow_north': self._follow,
            'follow_south': self._follow,
            'follow': self._follow,
            'gap_cross': self._gap_cross,
            'gap_forward': self._gap_forward,
            'east_search': self._east_search,
            'leg_forward': self._leg_forward,
            'target': self._target,
            'approach': self._approach,
        }.get(self.stage, self._orient)
        return handler(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)

    def _result(self, f, l, turn, stop=False, exact_turn=0):
        return dict(status='running', stage=self.stage, forward=float(f), left=float(l),
                    turn=float(turn), exact_turn=int(exact_turn), stop=bool(stop),
                    events=self.events[-1:], found=self.found, arrived=self.arrived,
                    colour_seen=self.colour_seen)

    def _orient(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_observed')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        # Look around first: one full Nav2 Spin-style in-place revolution using
        # the exact own-command calibration pulse.  It is the only way to see a
        # destination that is outside the initial field of view; walls seen
        # during the scan are used only after the scan completes.
        self._spin_pulses = getattr(self, '_spin_pulses', 0) + 1
        if self._spin_pulses > int(round(2 * math.pi / self.options.exact_turn_rad)):
            self._spin_pulses = 0
            front = self._nearest(walls, -22, 22, 3.2)
            if front is not None and front['range_m'] <= 3.0:
                self._set_stage(t, 'approach_wall', wall_range_m=front['range_m'],
                                after='full_spin')
                return self._approach_wall(t, paint, walls, obstacles, target_mem,
                                           patch_ok, patch_xy)
            # The wall foot is not projectable beyond the fitted floor range
            # (at >2 m it sits at/above the horizon).  Drive the initial
            # heading (Nav2 DriveOnHeading-style relative travel) until the
            # foot enters range; do not turn away yet.
            self.seek_t = 0.
            self._set_stage(t, 'seek_wall', reason='no_near_wall_after_full_spin')
            return self._seek_wall(t, paint, walls, obstacles, target_mem,
                                   patch_ok, patch_xy)
        return self._result(0., 0., 0., exact_turn=+1)

    def _seek_wall(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_while_seeking_wall')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        front = self._nearest(walls, -28, 28, 3.2)
        if front is not None and front['range_m'] <= 1.6:
            self._set_stage(t, 'approach_wall', wall_range_m=front['range_m'],
                            after='wall_seek')
            return self._approach_wall(t, paint, walls, obstacles, target_mem,
                                       patch_ok, patch_xy)
        ob = self._nearest_obstacle(obstacles, 30, .50)
        if ob is not None:
            # The arena contains loose cargo cubes.  Preflight r5 west e00 met
            # a cyan cube at 0.50-0.62 m during the very first seek tick and
            # aborted the wall approach for the lawnmower, losing the whole
            # 60 s probe.  A cube is not a reason to abandon the divider:
            # make one bounded away-turn (20 deg) and resume the same stage.
            self.event(t, 'obstacle_avoid', category='navigation',
                       blocked_object=ob['kind'], minimum_gap_m=ob['range_m'],
                       gap_status='floor_projection')
            away = +1 if ob['bearing_rad'] < 0 else -1
            self._start_turn(self._turn_pulses(math.radians(20.)), away, self.stage)
            return self._result(0., 0., 0.)
        self.seek_t += .1
        if self.seek_t > 20.:
            self.seek_t = 0.
            self.event(t, 'wall_seek_budget_exhausted', category='search',
                       blocked_object='not_observed', budget_sim_s=20.)
            self._enter_east_search(t, reason='wall_seek_budget_exhausted')
            return self._east_search(t, paint, walls, obstacles, target_mem,
                                     patch_ok, patch_xy)
        return self._result(.55, 0., 0.)

    def _approach_wall(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_while_approaching_wall')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        # Both handovers must fit inside this acceptance band.  seek_wall hands
        # over at <=1.6 m and orient hands over at <=3.0 m (the range at which
        # the floor-projected wall foot is still usable).  r4 west e00 lost a
        # visible divider at 1.58 m; r6 west e00 accepted 2.71 m after the full
        # spin, then counted ten "missing" ticks at 1.8 m and restarted the
        # 27 s scan.  Accept the full orient handover range and drive on.
        front = self._nearest(walls, -30, 30, 3.2)
        if front is None:
            self.missing += 1
            if self.missing > 10:
                self.missing = 0
                self._set_stage(t, 'orient', reason='wall_lost_before_follow')
            return self._result(.25, 0., 0.)
        self.missing = 0
        ob = self._nearest_obstacle(obstacles, 35, .55)
        if ob is not None:
            self.event(t, 'obstacle_avoid', category='navigation', blocked_object=ob['kind'],
                       minimum_gap_m=ob['range_m'], gap_status='floor_projection')
            return self._result(0., 0., 0., exact_turn=(1 if ob['bearing_rad'] >= 0 else -1))
        if front['range_m'] <= self.options.wall_clear_m:
            self._begin_follow(t, 'follow_north', 'right')
            r = self._turn_tick(t, paint, walls, obstacles)
            return r if r is not None else self._result(0., 0., 0.)
        return self._result(.55 if front['range_m'] > 1.0 else .35, 0., 0.)

    def _begin_follow(self, t, stage, side):
        self.wall_side = side
        self.missing = 0
        self._set_stage(t, stage)
        self._start_turn(self._turn_pulses(math.pi / 2),
                         +1 if stage == 'follow_north' else -1, stage)

    def _after_turnaround(self):
        return 'follow_north' if self.wall_side == 'right' else 'follow_south'

    def _follow(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        # Bug2-style wall following is bounded in SIM time: a perimeter
        # loop with no gap/colour hands over to the lawnmower search.
        self.follow_t = getattr(self, 'follow_t', 0.) + .1
        if self.follow_t > 30.:
            self.follow_t = 0.
            self.event(t, 'wall_follow_budget_exhausted', category='search',
                       blocked_object='not_observed', budget_sim_s=30.)
            self._enter_east_search(t, reason='wall_follow_budget_exhausted')
            return self._east_search(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_while_following_wall')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        right = self._nearest(walls, -145, -25, 1.5)
        left = self._nearest(walls, 25, 145, 1.5)
        front = self._nearest(walls, -30, 30, .9)
        ob = self._nearest_obstacle(obstacles, 40, .55)
        if ob is not None:
            self.event(t, 'obstacle_avoid', category='navigation', blocked_object=ob['kind'],
                       minimum_gap_m=ob['range_m'], gap_status='floor_projection')
            side = 1 if ob['bearing_rad'] >= 0 else -1
            if ob['range_m'] < self.options.obstacle_block_m:
                return self._result(0., 0., 0., exact_turn=side)
            return self._result(.25, 0., 0., exact_turn=side)
        if front is not None and front['range_m'] <= self.options.front_block_m:
            self.event(t, 'front_wall_block', category='navigation', blocked_object='wall',
                       minimum_gap_m=front['range_m'], gap_status='floor_projection')
            nxt = 'follow_south' if self.wall_side == 'right' else 'follow_north'
            self._set_stage(t, nxt, reason='front_wall_block')
            self._start_turn(self._turn_pulses(math.pi),
                             -1 if self.wall_side == 'right' else +1, nxt)
            self.wall_side = 'left' if nxt == 'follow_south' else 'right'
            return self._result(0., 0., 0.)
        side_pt = right if self.wall_side == 'right' else left
        if side_pt is None:
            self.missing += 1
            if self.missing >= self.options.gap_missing_ticks:
                self.missing = 0
                self.gap_phase = 0
                self.gap_ticks = 0
                self.gap_turn = 'right' if self.wall_side == 'right' else 'left'
                self._set_stage(t, 'gap_cross', reason='side_wall_gap_observed')
                return self._gap_cross(t, paint, walls, obstacles)
            return self._result(.3, 0., 0.)
        self.missing = 0
        desired = -90. if self.wall_side == 'right' else 90.
        err = math.degrees(_wrap(side_pt['bearing_rad'] - math.radians(desired)))
        if side_pt['range_m'] < .38:
            sign = +1 if self.wall_side == 'right' else -1
            return self._result(0., 0., 0., exact_turn=sign)
        if abs(err) > 16.:
            return self._result(.20, 0., 0., exact_turn=(-1 if err > 0 else +1))
        f = .55 if side_pt['range_m'] > .65 else .35
        return self._result(f, 0., 0.)

    def _gap_cross(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_at_gap')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        if self.gap_phase == 0:
            self.gap_ticks += 1
            if self.gap_ticks >= 4:
                self.gap_ticks = 0
                self.gap_phase = 1
                self._set_stage(t, 'gap_forward')
                self._start_turn(self._turn_pulses(math.pi / 2),
                                 -1 if self.gap_turn == 'right' else +1, 'gap_forward')
                r = self._turn_tick(t, paint, walls, obstacles)
                return r if r is not None else self._result(0., 0., 0.)
            return self._result(.45, 0., 0.)
        self._set_stage(t, 'gap_forward')
        return self._gap_forward(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)

    def _gap_forward(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_after_gap')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        front = self._nearest(walls, -30, 30, .55)
        self.gap_ticks += 1
        if front is not None or self.gap_ticks >= 16:
            self._enter_east_search(t, reason='gap_cross_finished')
            return self._east_search(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        return self._result(.6, 0., 0.)

    def _enter_east_search(self, t, reason):
        self._set_stage(t, 'east_search', reason=reason)
        self.leg = 0
        self.leg_ticks = 0
        self.leg_len = 20
        self._start_turn(self._turn_pulses(math.pi / 2), -1, 'leg_forward')

    def _east_search(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_in_search')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        if self.stage != 'east_search':
            self._set_stage(t, 'east_search')
        if self.turn_left > 0 or getattr(self, '_next_stage', None) is not None:
            r = self._turn_tick(t, paint, walls, obstacles)
            if r is not None:
                return r
        return self._leg_forward(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)

    def _leg_forward(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if paint.get('pixels', 0) >= MIN_COLOUR_PIXELS:
            self._set_stage(t, 'target', reason='destination_colour_on_leg')
            return self._target(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        ob = self._nearest_obstacle(obstacles, 30, .50)
        if ob is not None:
            # A 90 deg leg turn for every cargo cube burns many seconds in
            # place (r5 e00 spent most of its 60 s rotating).  Evade by 20 deg
            # and keep the same leg length instead of starting a new leg.
            self.event(t, 'obstacle_avoid', category='navigation', blocked_object=ob['kind'],
                       minimum_gap_m=ob['range_m'], gap_status='floor_projection')
            away = +1 if ob['bearing_rad'] < 0 else -1
            self._start_turn(self._turn_pulses(math.radians(20.)), away, self.stage)
            return self._result(0., 0., 0.)
        front = self._nearest(walls, -35, 35, .55)
        if front is not None:
            self._next_leg(t, reason='leg_wall')
            return self._result(0., 0., 0.)
        self.leg_ticks += 1
        if self.leg_ticks >= self.leg_len:
            self._next_leg(t, reason='leg_complete')
            return self._result(0., 0., 0.)
        return self._result(.55, 0., 0.)

    def _next_leg(self, t, reason):
        self.leg_ticks = 0
        self.leg += 1
        if self.leg >= 4:
            self.leg = 0
            self.leg_len = min(60, self.leg_len + 8)
        self._start_turn(self._turn_pulses(math.pi / 2), +1, 'leg_forward')
        self.event(t, 'search_leg_turn', category='search', leg_reason=reason, leg=self.leg,
                   blocked_object='not_observed')

    def _target(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if patch_ok:
            self._set_stage(t, 'approach', reason='metric_landmark_acquired')
            return self._approach(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        if paint.get('pixels', 0) < MIN_COLOUR_PIXELS:
            if self.last_paint_t is None or t - self.last_paint_t > 2.0:
                self._enter_east_search(t, reason='colour_lost')
                return self._east_search(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
            return self._result(0., 0., 0.)
        bearing = paint.get('bearing_rad')
        if bearing is None:
            return self._result(0., 0., 0., exact_turn=+1)
        if abs(bearing) > math.radians(6):
            return self._result(0., 0., 0., exact_turn=(+1 if bearing > 0 else -1))
        rng = paint.get('nearest_range_m', paint.get('range_m', 99.))
        return self._result(.55 if rng > 1.2 else .30, 0., 0.)

    def _approach(self, t, paint, walls, obstacles, target_mem=None, patch_ok=False, patch_xy=None):
        if target_mem is None:
            if patch_ok and patch_xy is not None:
                xy = np.asarray(patch_xy, float)
                target_mem = dict(relative_xy_m=xy.tolist(), range_m=float(np.linalg.norm(xy)),
                                  bearing_rad=float(math.atan2(xy[1], xy[0])), age_s=0.)
            else:
                self._enter_east_search(t, reason='memory_target_missing')
                return self._east_search(t, paint, walls, obstacles, target_mem, patch_ok, patch_xy)
        xy = np.asarray(target_mem['relative_xy_m'], float)
        rng = float(np.linalg.norm(xy)); bearing = math.atan2(xy[1], xy[0])
        age = float(target_mem.get('age_s', 99.))
        fresh = age <= 1.0
        lost = paint.get('pixels', 0) < MIN_COLOUR_PIXELS
        # Close to the remembered patch but the colour vanished for >2 SIM s:
        # look around locally before abandoning a near landmark.  This is the
        # public Spin primitive, not a new place estimate.
        if (lost and self.last_paint_t is not None
                and t - self.last_paint_t > 2.0 and rng <= 1.2):
            if self.reacquire_pulses is None:
                self.reacquire_pulses = int(round(
                    2 * math.pi / self.options.exact_turn_rad))
                self.event(t, 'local_reacquire_spin', category='search',
                           blocked_object='not_observed', memory_range_m=rng)
            if self.reacquire_pulses > 0:
                self.reacquire_pulses -= 1
                return self._result(0., 0., 0., exact_turn=+1)
            self.reacquire_pulses = None
            self._enter_east_search(t, reason='local_reacquire_failed')
            return self._east_search(t, paint, walls, obstacles, target_mem,
                                     patch_ok, patch_xy)
        if not lost:
            self.reacquire_pulses = None
        on_paint = (paint.get('lower_centre_pixels', 0) >= 700
                    and paint.get('nearest_range_m', 99.) <= .55)
        # The remembered point is the median of *visible* paint, which can sit
        # only ~0.18 m inside the near edge (preflight r3 e13: patch x 4.48 vs
        # zone edge 4.30).  Stopping 0.25-0.55 m short therefore declared a
        # place while the base was still outside.  Drive to the point itself.
        if on_paint and rng <= .10 and fresh:
            self.arrived = True
            self.event(t, 'arrival_inside_paint_hypothesis', category='arrival',
                       blocked_object='not_observed', memory_range_m=rng,
                       memory_age_s=age, nearest_range_m=paint.get('nearest_range_m'))
            return self._result(0., 0., 0., True)
        if abs(bearing) > math.radians(8):
            return self._result(0., 0., 0., exact_turn=(+1 if bearing > 0 else -1))
        if rng > .50:
            return self._result(.45 if rng > 1.0 else .28, 0., 0.)
        if fresh and rng > .10:
            return self._result(.18, 0., 0.)
        if fresh:
            self.arrived = True
            self.event(t, 'arrival_memory_range', category='arrival',
                       blocked_object='not_observed', memory_range_m=rng,
                       memory_age_s=age)
            return self._result(0., 0., 0., True)
        # Stale memory with no visual on-paint evidence is not an arrival claim.
        return self._result(0., 0., 0., True)

    def _nearest_obstacle(self, obstacles, half_angle_deg, max_range):
        best = None
        for o in obstacles:
            if o.get('kind') == 'robot':
                continue
            xy = np.asarray(o['xy'], float)
            rng = float(np.linalg.norm(xy)); b = math.atan2(xy[1], xy[0])
            if rng - float(o.get('radius', 0.)) <= max_range and abs(math.degrees(b)) <= half_angle_deg:
                if best is None or rng < best['range_m']:
                    best = dict(kind=o.get('kind', 'unknown'), bearing_rad=b, range_m=rng)
        return best
