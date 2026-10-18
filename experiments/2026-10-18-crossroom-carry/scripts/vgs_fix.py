"""crossroom-stageA-fix and crossroom-loaded-wallline policy overrides (default off).

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

``LoadedWallLineSearch`` is the loaded, occlusion-aware follow
(``crossroom_loaded_wallline_v1``, default off, loaded stages only): it fits
the wall line from own-RGB wall points above the cargo band, steers to the
tangent/offset, never opens ``gap_cross`` from a side-foot loss, and accepts a
door only on positive above-band evidence. See
``outputs/reports/crossroom-stageB-fix.md`` section 2 and its own module
``loaded_wallline.py``.
"""
from __future__ import annotations

import math

import numpy as np

from sim.visual_goal_search import VisualGoalSearch, MIN_COLOUR_PIXELS


def _load_loaded_wallline():
    """Load the pure loaded-wallline module next to this file.

    ``scripts/`` is not a package (the runner registers modules by path), so
    the sibling module is loaded by path rather than by import name.
    """
    import importlib.util
    from pathlib import Path
    path = Path(__file__).with_name('loaded_wallline.py')
    spec = importlib.util.spec_from_file_location(
        'crossroom_loaded_wallline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loaded_wallline_mod = _load_loaded_wallline()
FOLLOW_STAGES = ('follow_north', 'follow_south', 'follow')

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


class LoadedWallLineSearch(FixedVisualGoalSearch):
    """``crossroom_loaded_wallline_v1``: occlusion-aware loaded wall follow.

    Default off and admitted only for the loaded stages (the runner rejects it
    elsewhere).  While the own-RGB carry band is available it

    * steers to the tangent/offset of the wall line fitted from wall points
      above the cargo band instead of the nearest side foot;
    * refuses a ``gap_cross`` claim opened by the loss of a side foot: the
      claim is deferred and the fitted line is followed instead; after
      ``LINE_HOLD_TICKS`` without a fit the robot stops
      (``STOPPED_BLIND_CARGO``);
    * accepts a real doorway only with all three positive-evidence pieces
      (empty front cone, far jamb 0.6-1.3 m, 0.40-0.60 m along-line hole).

    The base policy's search, paint filter, arrival and obstacle handling are
    untouched: the subclass only replaces the follow steering and vets the
    gap transition.  With ``loaded_wallline=False`` the instance behaves
    exactly like :class:`FixedVisualGoalSearch`.
    """

    def __init__(self, *, option, options=None, loaded_wallline=False, **kwargs):
        super().__init__(option=option, options=options, **kwargs)
        self.loaded_wallline = bool(loaded_wallline)
        self.loaded_wallline_option = loaded_wallline_mod.OPTION
        self.loaded_gate = loaded_wallline_mod.LoadedWallLineGate(
            enabled=self.loaded_wallline, wall_side=self.wall_side)
        self.cargo_held = False
        self.cargo_band_top = None
        self.loaded_follow_overrides = 0
        self.loaded_rows_missing = 0
        self.loaded_gap_confirmed = 0
        self.blind_cargo_stop_events = 0
        self._blind_stop_latched = False

    # ---- own-RGB cargo band (control input, audited by the runner) ----
    def control(self, t, *, paint=None, walls=(), obstacles=(), memories=(),
                patch_ok=False, patch_xy=None, cargo_held=False,
                cargo_band_top=None):
        self.cargo_held = bool(cargo_held)
        self.cargo_band_top = (None if cargo_band_top is None
                               else int(cargo_band_top))
        return super().control(t, paint=paint, walls=walls, obstacles=obstacles,
                               memories=memories, patch_ok=patch_ok,
                               patch_xy=patch_xy)

    def _loaded_active(self):
        return bool(self.loaded_wallline and self.cargo_band_top is not None
                    and self.stage in FOLLOW_STAGES)

    def _rows_missing(self, t, walls):
        if not walls or any(p.get('row') is not None for p in walls):
            return False
        self.loaded_rows_missing += 1
        if self.loaded_rows_missing == 1:
            self.event(t, 'loaded_wallline_rows_missing',
                       category='perception', blocked_object='not_observed',
                       walls=len(walls), cargo_band_top=self.cargo_band_top)
        return True

    def _event_after(self, index):
        return [e for e in self.events[index:]
                if e.get('reason') in ('obstacle_avoid', 'front_wall_block')]

    def _blind_stop(self, t, decision):
        if not self._blind_stop_latched:
            self._blind_stop_latched = True
            self.blind_cargo_stop_events += 1
            obs = decision.get('observation') or {}
            self.event(t, 'STOPPED_BLIND_CARGO', category='navigation',
                       blocked_object='cargo_blind_band',
                       cargo_band_top=self.cargo_band_top,
                       above_band_points=len(obs.get('above') or []),
                       side_points=len(obs.get('side') or []),
                       hold_ticks=obs.get('hold'))
        return self._result(0., 0., 0., stop=True)

    def _line_action(self, t, decision):
        command = decision.get('command')
        if command is not None:
            self.loaded_follow_overrides += 1
            return self._result(command['forward'], 0., 0.,
                                exact_turn=int(command['exact_turn']))
        obs = decision.get('observation') or {}
        if obs.get('blind'):
            return self._blind_stop(t, decision)
        # no fit yet but the hold window is open: creep without a gap claim
        return self._result(.3, 0., 0.)

    def _defer_gap(self, t, decision):
        # Mirror the v1/v3 rejection: clear the gap sequence, keep following.
        self.gap_phase = 0
        self.gap_ticks = 0
        self.gap_turn = 'right' if self.wall_side == 'right' else 'left'
        self.missing = 0
        self._set_stage(t, 'follow_north' if self.wall_side == 'right'
                        else 'follow_south',
                        reason='gap_deferred_cargo_blind')
        evidence = decision.get('evidence') or {}
        self.event(t, 'gap_deferred_cargo_blind', category='navigation',
                   blocked_object='cargo_blind_band',
                   cargo_band_top=self.cargo_band_top,
                   gap_claims=self.gap_claims, **evidence)

    def _follow(self, t, paint, walls, obstacles, target_mem=None,
                patch_ok=False, patch_xy=None):
        if not self._loaded_active():
            return super()._follow(t, paint, walls, obstacles, target_mem,
                                   patch_ok, patch_xy)
        # If the caller enabled the toggle but passed no rows, the fit cannot
        # run; the event is recorded and the gate still vets the gap (it then
        # behaves like a blind follow and stops after LINE_HOLD_TICKS) rather
        # than silently falling back to the nearest-foot gap trigger.
        self._rows_missing(t, walls)
        prev_stage = self.stage
        n_events = len(self.events)
        action = super()._follow(t, paint, walls, obstacles, target_mem,
                                 patch_ok, patch_xy)
        self.loaded_gate.set_side(self.wall_side)
        gap_claimed = (self.stage == 'gap_cross' and prev_stage != 'gap_cross')
        decision = self.loaded_gate.decide(walls, self.cargo_band_top,
                                           gap_claimed=gap_claimed)
        if gap_claimed:
            if decision['mode'] == 'allow_gap':
                self._blind_stop_latched = False
                self.loaded_gap_confirmed += 1
                evidence = decision.get('evidence') or {}
                self.event(t, 'gap_confirmed_above_band',
                           category='navigation', blocked_object='not_observed',
                           cargo_band_top=self.cargo_band_top, **evidence)
                return action
            self._defer_gap(t, decision)
            return self._line_action(t, decision)
        if self.stage != prev_stage:
            # the base handed over to another stage (paint/target, budget
            # exhaustion -> east search, front-wall turnaround): keep its
            # action, the line does not own this transition.
            return action
        if self._event_after(n_events):
            # obstacle avoidance / front-wall turnaround own this tick
            return action
        if action.get('arrived') or action.get('found'):
            return action
        mode = decision['mode']
        if mode == 'follow':
            self._blind_stop_latched = False
        if mode in ('follow', 'hold') and decision.get('command'):
            return self._line_action(t, decision)
        if mode == 'stop':
            return self._blind_stop(t, decision)
        return action

    def loaded_debug(self):
        """Compact per-tick view of the loaded gate for the trace."""
        decision = self.loaded_gate.last_decision or {}
        obs = decision.get('observation') or {}
        fit = obs.get('fit') or {}
        return dict(active=self._loaded_active(),
                    band_top=self.cargo_band_top,
                    cargo_held=self.cargo_held,
                    mode=decision.get('mode'),
                    above_band_points=len(obs.get('above') or []),
                    side_points=len(obs.get('side') or []),
                    fit_ok=bool(fit.get('ok')),
                    fit_inliers=fit.get('inliers'),
                    fit_reason=fit.get('reason'),
                    hold=obs.get('hold'),
                    tangent_deg=(round(float(fit['tangent_deg']), 2)
                                 if fit.get('tangent_deg') is not None else None),
                    offset_m=(round(float(fit['offset_m']), 4)
                              if fit.get('offset_m') is not None else None))

    def fix_summary(self):
        summary = super().fix_summary()
        summary.update(
            loaded_wallline=self.loaded_wallline,
            loaded_wallline_option=self.loaded_wallline_option,
            loaded_band_top_row=self.cargo_band_top,
            loaded_cargo_held=self.cargo_held,
            loaded_follow_overrides=self.loaded_follow_overrides,
            loaded_rows_missing=self.loaded_rows_missing,
            loaded_gap_confirmed=self.loaded_gap_confirmed,
            blind_cargo_stop_events=self.blind_cargo_stop_events,
            loaded_gate=self.loaded_gate.summary())
        return summary
