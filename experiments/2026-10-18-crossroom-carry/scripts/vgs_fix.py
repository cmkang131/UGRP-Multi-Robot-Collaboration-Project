"""crossroom-stageA-fix policy overrides (default off).

Subclasses the vendored Stage A policy and overrides only the two failure
points measured in Stage A, both behind explicit toggles:

* ``gap_twosided`` -- before accepting a side-wall gap, require a same-side
  wall face ahead within 1.6 m and at least ``tracked_side_ticks_min`` ticks of
  tracked side wall.  A lost wall foot in the open pickup room then no longer
  starts an east search in the wrong room.
* ``door_align`` -- while crossing the gap, estimate the lateral offset from
  the two wall feet on the left/right of the robot frame and issue small
  calibrated turns until |offset| <= 0.02 m before driving through.

The vendored policy bytes are not modified; provenance records the base
commit (c390105c2) and this override scope.  No ground truth enters the
policy: wall feet are own-RGB observations.
"""
from __future__ import annotations

import math

import numpy as np

from sim.visual_goal_search import VisualGoalSearch, MIN_COLOUR_PIXELS

ALIGN_TOLERANCE_M = 0.02
GAP_FRONT_RANGE_M_V2 = 1.2
APPROACH_ESCAPE_S = 15.0
# v3 constants (measured, see FIX_DESIGN v3 section):
#  - false-gap events in the recorded Stage A raw show a dense wall directly
#    ahead (front cone |bearing|<=20 deg, range<=1.0 m: 377-418 points on
#    e03/e14, 23 on e10) or no jamb at all after the side wall is lost
#    (e00/e04/e06/e08/e12/e15); a doorway keeps the ahead cone empty and a
#    jamb in the 20-110 deg side sector.
GAP_FRONT_CONE_MAX_POINTS = 10
GAP_JAMB_RANGE_M_V3 = 1.3
GAP_JAMB_BEARING = (20., 110.)
#  - the single recorded declaration outside zone B (fix v2 e02, margin
#    -0.0162 m) had the zone paint bbox bottom at 461/480 = 0.960 of the
#    frame; the v3 edge check requires the paint to reach the bottom 2% band
#    (>=0.98) before the declaration is kept.
ZONE_EDGE_BOTTOM_NORM = 0.98
ZONE_EDGE_MAX_RETRACT = 30
ZONE_EDGE_FRAME_H = 480
TRACKED_SIDE_TICKS_MIN = 12
GAP_FRONT_RANGE_M = 1.6


class FixedVisualGoalSearch(VisualGoalSearch):
    def __init__(self, *, option, options=None, gap_twosided=False,
                 door_align=False,
                 tracked_side_ticks_min=TRACKED_SIDE_TICKS_MIN,
                 gap_front_range_m=GAP_FRONT_RANGE_M,
                 align_tolerance_m=ALIGN_TOLERANCE_M,
                 two_sided_v2=False,
                 gap_v3=False,
                 zone_edge_check=False,
                 approach_escape_s=APPROACH_ESCAPE_S):
        super().__init__(option=option, options=options)
        self.gap_twosided = bool(gap_twosided)
        self.door_align = bool(door_align)
        self.tracked_side_ticks_min = int(tracked_side_ticks_min)
        self.gap_front_range_m = float(gap_front_range_m)
        self.align_tolerance_m = float(align_tolerance_m)
        self.side_track_ticks = 0
        self.gap_claims = 0
        self.gap_confirmed = 0
        self.gap_rejected = 0
        self.align_events = 0
        self.align_uncertain_ticks = 0
        self.two_sided_v2 = bool(two_sided_v2)
        self.gap_v3 = bool(gap_v3)
        self.zone_edge_check = bool(zone_edge_check)
        self.zone_retracts = 0
        self.zone_edge_ok = 0
        self.zone_edge_forced = 0
        self.approach_escape_s = float(approach_escape_s)
        self.approach_t = 0.0
        self.approach_escapes = 0

    # ---- side-wall tracking ------------------------------------------
    def _side_sector(self):
        return (-160., -20.) if self.wall_side == 'right' else (20., 160.)

    def _update_side_tracking(self, walls):
        if not walls:
            self.side_track_ticks = 0
            return
        lo, hi = self._side_sector()
        if self._nearest(walls, lo, hi, 1.5) is not None:
            self.side_track_ticks += 1
        else:
            self.side_track_ticks = 0

    def control(self, t, *, paint=None, walls=(), obstacles=(), memories=(),
                patch_ok=False, patch_xy=None):
        self._update_side_tracking(walls)
        return super().control(t, paint=paint, walls=walls, obstacles=obstacles,
                               memories=memories, patch_ok=patch_ok,
                               patch_xy=patch_xy)

    # ---- 1) two-sided gap confirmation ------------------------------
    def _gap_side_confirmed(self, walls):
        lo, hi = self._side_sector()
        ahead = self._nearest(walls, lo, hi, self.gap_front_range_m)
        tracked_ok = self.side_track_ticks >= self.tracked_side_ticks_min
        info = dict(side=self.wall_side, tracked_side_ticks=self.side_track_ticks,
                    ahead_range_m=(round(float(ahead['range_m']), 4)
                                   if ahead else None),
                    ahead_bearing_deg=(round(math.degrees(float(ahead['bearing_rad'])), 1)
                                       if ahead else None))
        if not self.two_sided_v2:
            return (ahead is not None) and tracked_ok, info
        # v2: a real doorway keeps a wall face on BOTH sides of the gap.  In
        # the robot frame with the wall on the right, the far jamb is in the
        # forward-right sector and the near segment behind-right.
        if self.wall_side == 'right':
            ahead_sector, behind_sector = (-80., -20.), (-160., -100.)
        else:
            ahead_sector, behind_sector = (20., 80.), (100., 160.)
        far = self._nearest(walls, *ahead_sector, GAP_FRONT_RANGE_M_V2)
        near = self._nearest(walls, *behind_sector, 1.6)
        ok = tracked_ok and far is not None and near is not None
        info.update(two_sided_v2=True,
                    far_range_m=(round(float(far['range_m']), 4)
                                 if far else None),
                    near_range_m=(round(float(near['range_m']), 4)
                                  if near else None))
        return ok, info

    def _follow(self, t, paint, walls, obstacles, target_mem=None,
                patch_ok=False, patch_xy=None):
        prev_stage = self.stage
        action = super()._follow(t, paint, walls, obstacles, target_mem,
                                 patch_ok, patch_xy)
        if prev_stage != 'gap_cross' and self.stage == 'gap_cross':
            self.gap_claims += 1
        if self.gap_twosided and self.stage == 'gap_cross':
            ok, info = self._gap_side_confirmed(walls)
            if not ok:
                self.gap_phase = 0
                self.gap_ticks = 0
                self.missing = 0
                self.gap_rejected += 1
                self._set_stage(t, 'follow_north' if self.wall_side == 'right'
                                else 'follow_south',
                                reason='gap_rejected_front_missing')
                self.event(t, 'gap_rejected_front_missing',
                           category='navigation', blocked_object='not_observed',
                           **{k: v for k, v in info.items() if v is not None})
                return self._result(.3, 0., 0.)
            self.gap_confirmed += 1
            self.event(t, 'gap_confirmed', category='navigation',
                       blocked_object='not_observed',
                       **{k: v for k, v in info.items() if v is not None})
        return action

    def _approach_wall(self, t, paint, walls, obstacles, target_mem=None,
                       patch_ok=False, patch_xy=None):
        self.approach_t += .1
        if (self.approach_escape_s > 0 and self.approach_t > self.approach_escape_s):
            self.approach_t = 0.
            self.approach_escapes += 1
            self.event(t, 'approach_wall_escape', category='navigation',
                       blocked_object='not_observed',
                       budget_sim_s=self.approach_escape_s)
            self._set_stage(t, 'seek_wall', reason='approach_wall_escape')
            return self._seek_wall(t, paint, walls, obstacles, target_mem,
                                   patch_ok, patch_xy)
        return super()._approach_wall(t, paint, walls, obstacles, target_mem,
                                      patch_ok, patch_xy)

    # ---- 3) own-RGB zone-edge check before the arrival declaration --
    def _paint_bottom_norm(self, paint):
        bbox = (paint or {}).get('bbox')
        if not bbox or len(bbox) != 4:
            return None
        bottom = float(bbox[1]) + float(bbox[3])
        return max(0.0, min(1.5, bottom / float(ZONE_EDGE_FRAME_H)))

    def _target(self, t, paint, walls, obstacles, target_mem=None,
                patch_ok=False, patch_xy=None):
        action = super()._target(t, paint, walls, obstacles, target_mem,
                                 patch_ok, patch_xy)
        if not self.zone_edge_check or not action.get('arrived'):
            return action
        bottom = self._paint_bottom_norm(paint)
        if bottom is not None and bottom >= ZONE_EDGE_BOTTOM_NORM:
            self.zone_edge_ok += 1
            self.event(t, 'zone_edge_ok', category='arrival',
                       blocked_object='not_observed',
                       paint_bottom_norm=round(bottom, 4))
            return action
        if self.zone_retracts >= ZONE_EDGE_MAX_RETRACT:
            self.zone_edge_forced += 1
            self.event(t, 'zone_edge_force_declare', category='arrival',
                       blocked_object='not_observed',
                       paint_bottom_norm=(round(bottom, 4)
                                          if bottom is not None else None))
            return action
        # retract the declaration and creep until the paint reaches the
        # bottom band (own RGB only; no world pose is used).
        self.arrived = False
        self.zone_retracts += 1
        self.event(t, 'zone_edge_retract', category='arrival',
                   blocked_object='not_observed',
                   paint_bottom_norm=(round(bottom, 4)
                                      if bottom is not None else None),
                   paint_pixels=int((paint or {}).get('pixels', 0)))
        return self._result(.06, 0., 0.)

    # ---- 2) door-center lateral alignment ---------------------------
    def _gap_forward(self, t, paint, walls, obstacles, target_mem=None,
                     patch_ok=False, patch_xy=None):
        if self.door_align and paint.get('pixels', 0) < MIN_COLOUR_PIXELS:
            left = self._nearest(walls, 25, 145, 1.0)
            right = self._nearest(walls, -145, -25, 1.0)
            if left is not None and right is not None:
                lat = (float(left['relative_xy_m'][1])
                       + float(right['relative_xy_m'][1])) / 2.0
                self.event(t, 'door_align_measure', category='navigation',
                           blocked_object='not_observed',
                           lateral_estimate_m=round(lat, 4))
                if abs(lat) > self.align_tolerance_m:
                    self.align_events += 1
                    sign = +1 if lat > 0 else -1
                    return self._result(0., 0., 0., exact_turn=sign)
            else:
                self.align_uncertain_ticks += 1
                if self.align_uncertain_ticks % 10 == 1:
                    self.event(t, 'door_align_uncertain', category='navigation',
                               blocked_object='not_observed',
                               left_seen=bool(left is not None),
                               right_seen=bool(right is not None))
        return super()._gap_forward(t, paint, walls, obstacles, target_mem,
                                    patch_ok, patch_xy)

    def fix_summary(self):
        return dict(gap_twosided=self.gap_twosided, door_align=self.door_align,
                    gap_claims=self.gap_claims, gap_confirmed=self.gap_confirmed,
                    gap_rejected=self.gap_rejected,
                    align_turns=self.align_events,
                    align_uncertain_ticks=self.align_uncertain_ticks,
                    two_sided_v2=self.two_sided_v2,
                    gap_v3=self.gap_v3,
                    zone_edge_check=self.zone_edge_check,
                    zone_retracts=self.zone_retracts,
                    zone_edge_ok=self.zone_edge_ok,
                    zone_edge_forced=self.zone_edge_forced,
                    approach_escapes=self.approach_escapes)
