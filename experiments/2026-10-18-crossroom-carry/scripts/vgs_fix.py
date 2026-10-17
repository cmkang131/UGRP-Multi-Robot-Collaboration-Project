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
TRACKED_SIDE_TICKS_MIN = 12
GAP_FRONT_RANGE_M = 1.6


class FixedVisualGoalSearch(VisualGoalSearch):
    def __init__(self, *, option, options=None, gap_twosided=False,
                 door_align=False,
                 tracked_side_ticks_min=TRACKED_SIDE_TICKS_MIN,
                 gap_front_range_m=GAP_FRONT_RANGE_M,
                 align_tolerance_m=ALIGN_TOLERANCE_M):
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
        return (ahead is not None) and tracked_ok, info

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
                    align_uncertain_ticks=self.align_uncertain_ticks)
